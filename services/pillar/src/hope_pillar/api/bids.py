"""My bids: preparing one saved grant's application for submission.

Each requirement on the application's checklist gets an owner, an internal due date, a status,
an evidence reference and a review. Code decides what blocks the final review; Hope never
submits anything: staff submit through the funder and record the receipt here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, Response
from hope_core.auth import ProblemException
from hope_core.db import connect, tenant_tx
from hope_core.hashing import content_hash
from hope_core.store import Tx
from hope_discovery.answers import ChecklistItem
from hope_discovery.requirements import Limit
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from hope_pillar.api.applications import (
    ApplicationView,
    IfMatch,
    PrincipalDep,
    _row,
    _update,
    _version,
    _view,
    add_event,
    ready_problem,
)
from hope_pillar.api.grants import save_grant

router = APIRouter(prefix="/v1", tags=["bids"])

ItemStatus = Literal["missing", "working", "ready"]
Phase = Literal["preparing", "final_reviewed", "submitted"]
Decision = Literal["approved", "changes_requested"]
BlockerCode = Literal[
    "no_requirements",
    "checklist_incomplete",
    "no_owner",
    "not_ready",
    "not_reviewed",
    "stale_review",
    "deadline_passed",
]
MilestoneKey = Literal["owners", "drafts", "reviews", "final_review"]

# Checklist kinds that only inform (the deadline itself, how to submit) aren't work to assign.
INFO_KINDS = {"deadline", "submission"}
# Days before the deadline each step should be done by.
PLAN: tuple[tuple[MilestoneKey, int], ...] = (
    ("owners", 14),
    ("drafts", 7),
    ("reviews", 3),
    ("final_review", 1),
)


# --- models -----------------------------------------------------------------------------------


class Review(BaseModel):
    by: UUID
    at: datetime
    decision: Decision
    comment: str
    stale: bool = Field(False, description="The funder's requirement changed after this review")


class BidItem(BaseModel):
    key: str
    kind: str
    label: str
    checklist_status: str = Field(description="The application checklist's own status")
    quote: str | None
    url: str | None
    limit: Limit | None
    owner: UUID | None
    due: date | None
    status: ItemStatus
    note: str
    evidence_ref: str
    review: Review | None


class Blocker(BaseModel):
    code: BlockerCode
    key: str | None = None
    detail: str | None = None


class Milestone(BaseModel):
    key: MilestoneKey
    due: date
    done: bool


class FinalReview(BaseModel):
    by: UUID
    at: datetime
    comment: str


class Submission(BaseModel):
    receipt: str
    portal: str
    submitted_at: datetime
    recorded_by: UUID
    recorded_at: datetime
    sent_by_hope: Literal[False] = False


class BidSummary(BaseModel):
    application_id: UUID
    grant_id: UUID
    title: str
    funder: str
    deadline: date | None
    phase: Phase
    ready: int
    total: int
    blockers: int
    updated_at: datetime


class BidView(BidSummary):
    url: str
    version: int
    items: list[BidItem]
    blocker_list: list[Blocker] = Field(description="What must be done before the final review")
    plan: list[Milestone] = Field(description="Steps counted back from the deadline")
    final_review: FinalReview | None
    submission: Submission | None
    created_at: datetime


class BidList(BaseModel):
    items: list[BidSummary]
    total: int


class Member(BaseModel):
    """Display names only: anyone signed in can list the team, so emails stay private."""

    user_id: UUID
    display_name: str


class MemberList(BaseModel):
    items: list[Member]


class StartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grant_id: UUID


class ItemBody(BaseModel):
    """Only the fields sent change; send `owner: null` or `due: null` to clear them."""

    model_config = ConfigDict(extra="forbid")
    owner: UUID | None = None
    due: date | None = None
    status: ItemStatus | None = None
    note: str | None = Field(None, max_length=2000)
    evidence_ref: str | None = Field(None, max_length=500)


class ReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Decision
    comment: str = Field("", max_length=2000)


class FinalReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str = Field("", max_length=2000)


class SubmissionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt: str = Field(min_length=1, max_length=200)
    portal: str = Field(min_length=1, max_length=200)
    submitted_at: datetime


# --- rules (code decides) ---------------------------------------------------------------------


def item_hash(item: ChecklistItem) -> str:
    """What a review approved: the funder's wording, not the item's moving status."""
    return content_hash(item.model_dump(mode="json", include={"label", "quote", "url", "limit"}))


def bid_deadline(app: ApplicationView) -> date | None:
    read = app.requirements.submission.deadline_date if app.requirements else None
    return read or app.deadline


def blockers_for(app: ApplicationView, items: list[BidItem], today: date) -> list[Blocker]:
    out: list[Blocker] = []
    if app.requirements_revision is None:
        out.append(Blocker(code="no_requirements"))
    open_checklist = ready_problem(app.checklist)
    if open_checklist:
        out.append(Blocker(code="checklist_incomplete", detail=open_checklist))
    for i in items:
        if i.owner is None:
            out.append(Blocker(code="no_owner", key=i.key))
        if i.status != "ready":
            out.append(Blocker(code="not_ready", key=i.key))
        elif i.review is None or i.review.decision != "approved":
            out.append(Blocker(code="not_reviewed", key=i.key))
        elif i.review.stale:
            out.append(Blocker(code="stale_review", key=i.key))
    deadline = bid_deadline(app)
    if deadline is not None and deadline < today:
        out.append(Blocker(code="deadline_passed", detail=deadline.isoformat()))
    return out


def plan_for(deadline: date | None, items: list[BidItem], final: bool) -> list[Milestone]:
    if deadline is None:
        return []
    done = {
        "owners": all(i.owner for i in items),
        "drafts": all(i.status == "ready" for i in items),
        "reviews": all(
            i.review and i.review.decision == "approved" and not i.review.stale for i in items
        ),
        "final_review": final,
    }
    return [
        Milestone(key=k, due=deadline - timedelta(days=d), done=bool(items) and done[k])
        for k, d in PLAN
    ]


def _item(c: ChecklistItem, row: dict[str, Any] | None) -> BidItem:
    row = row or {}
    review = row.get("review")
    return BidItem(
        key=c.key,
        kind=c.kind,
        label=c.label,
        checklist_status=c.status,
        quote=c.quote,
        url=c.url,
        limit=c.limit,
        owner=row.get("owner"),
        due=row.get("due"),
        status=row.get("status", "missing"),
        note=row.get("note", ""),
        evidence_ref=row.get("evidence_ref", ""),
        review=Review.model_validate(review | {"stale": review["hash"] != item_hash(c)})
        if review
        else None,
    )


# --- store ------------------------------------------------------------------------------------


def _today() -> date:
    return datetime.now().astimezone().date()


def _not_found() -> NoReturn:
    raise ProblemException(404, "bid_not_found", "Bid not found")


def _refuse(code: str, message: str, errors: list[dict[str, Any]] | None = None) -> NoReturn:
    raise ProblemException(409, code, message, errors)


def _bid_id(tx: Tx, grant_id: str) -> UUID:
    try:
        gid = UUID(grant_id)
    except ValueError:
        _not_found()
    tx.execute(
        "SELECT b.application_id FROM bids b JOIN applications a USING (application_id)"
        " WHERE a.grant_id = %s",
        (gid,),
    )
    row = tx.fetchone()
    if row is None:
        _not_found()
    return UUID(str(row["application_id"]))


def _load(tx: Tx, aid: UUID) -> tuple[BidView, ApplicationView, dict[str, ChecklistItem]]:
    app = _view(tx, _row(tx, aid))
    tx.execute("SELECT * FROM bids WHERE application_id = %s", (aid,))
    bid = tx.fetchone()
    if bid is None:
        _not_found()
    tx.execute("SELECT * FROM bid_items WHERE application_id = %s", (aid,))
    stored = {r["item_key"]: r for r in tx.fetchall()}
    checklist = {c.key: c for c in app.checklist.items if c.kind not in INFO_KINDS}
    items = [_item(c, stored.get(k)) for k, c in checklist.items()]
    blockers = blockers_for(app, items, _today()) if bid["submission"] is None else []
    phase: Phase = (
        "submitted"
        if bid["submission"]
        else "final_reviewed"
        if bid["final_review"]
        else "preparing"
    )
    view = BidView(
        application_id=aid,
        grant_id=app.grant_id,
        title=app.title,
        funder=app.funder,
        url=app.url,
        deadline=bid_deadline(app),
        phase=phase,
        ready=sum(i.status == "ready" for i in items),
        total=len(items),
        blockers=len(blockers),
        updated_at=bid["updated_at"],
        version=bid["version"],
        items=items,
        blocker_list=blockers,
        plan=plan_for(bid_deadline(app), items, bid["final_review"] is not None),
        final_review=bid["final_review"],
        submission=bid["submission"],
        created_at=bid["created_at"],
    )
    return view, app, checklist


def _bump(tx: Tx, aid: UUID, version: int, **fields: Any) -> None:
    """Optimistic write on the bid: bumps `version`, or 412 when the caller's copy is stale."""
    sets = "".join(f"{k} = %s, " for k in fields)
    values = [Jsonb(v) if isinstance(v, dict) else v for v in fields.values()]
    tx.execute(
        f"UPDATE bids SET {sets}version = version + 1, updated_at = clock_timestamp()"
        " WHERE application_id = %s AND version = %s",
        (*values, aid, version),
    )
    if tx.rowcount == 0:
        raise ProblemException(412, "version_mismatch", "This bid changed; reload it")


def _open(view: BidView) -> None:
    if view.submission is not None:
        _refuse("bid_submitted", "This bid was submitted; it can't change.")


def _reopen(tx: Tx, view: BidView, actor: UUID) -> dict[str, Any]:
    """Any change to the work after the final review undoes that review."""
    if view.final_review is None:
        return {}
    add_event(tx, view.application_id, "bid", actor, action="final_review_undone")
    return {"final_review": None}


def _respond(tx: Tx, aid: UUID, response: Response) -> BidView:
    view = _load(tx, aid)[0]
    response.headers["ETag"] = f'"{view.version}"'
    return view


# --- routes -----------------------------------------------------------------------------------


@router.get("/bids")
def list_bids(principal: PrincipalDep) -> BidList:
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        tx.execute("SELECT application_id FROM bids ORDER BY created_at")
        ids = [UUID(str(r["application_id"])) for r in tx.fetchall()]
        views = [_load(tx, aid)[0] for aid in ids]
    items = [BidSummary.model_validate(v.model_dump()) for v in views]
    items.sort(key=lambda b: (b.phase == "submitted", b.deadline or date.max))
    return BidList(items=items, total=len(items))


@router.post("/bids", status_code=201)
def start_bid(body: StartBody, principal: PrincipalDep, response: Response) -> BidView:
    """Start preparing a grant: saves it (which creates the application and starts reading the
    funder's requirements), then opens its bid. Starting again returns the same bid (200)."""
    save_grant(str(body.grant_id), principal)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        tx.execute("SELECT application_id FROM applications WHERE grant_id = %s", (body.grant_id,))
        found = tx.fetchone()
        assert found is not None
        aid = UUID(str(found["application_id"]))
        tx.execute(
            "INSERT INTO bids (application_id, tenant_id, created_by)"
            " VALUES (%s, current_tenant(), %s) ON CONFLICT DO NOTHING",
            (aid, principal.user_id),
        )
        if tx.rowcount:
            add_event(tx, aid, "bid", principal.user_id, action="started")
        else:
            response.status_code = 200
        return _respond(tx, aid, response)


@router.get("/bids/{grant_id}")
def get_bid(grant_id: str, principal: PrincipalDep, response: Response) -> BidView:
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        return _respond(tx, _bid_id(tx, grant_id), response)


@router.put("/bids/{grant_id}/items/{key}")
def update_item(
    grant_id: str,
    key: str,
    body: ItemBody,
    principal: PrincipalDep,
    response: Response,
    if_match: IfMatch = None,
) -> BidView:
    """Assign, date and track one requirement. Changing its status, note or evidence undoes
    its review, since the reviewer approved the previous version."""
    version = _version(if_match)
    changes = body.model_dump(exclude_unset=True)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        aid = _bid_id(tx, grant_id)
        view, _, checklist = _load(tx, aid)
        _open(view)
        if key not in checklist:
            raise ProblemException(404, "item_not_found", "Requirement not found")
        if changes.get("owner") is not None:
            tx.execute("SELECT 1 FROM users WHERE user_id = %s", (changes["owner"],))
            if tx.fetchone() is None:
                raise ProblemException(
                    422,
                    "unknown_member",
                    "Unknown team member",
                    [{"field": "owner", "code": "unknown", "message": "Not on this team."}],
                )
        current = next(i for i in view.items if i.key == key)
        merged = current.model_dump(include={"owner", "due", "status", "note", "evidence_ref"})
        merged |= changes
        work_changed = any(
            merged[f] != getattr(current, f) for f in ("status", "note", "evidence_ref")
        )
        keep_review = current.review is not None and not work_changed
        _bump(tx, aid, version, **_reopen(tx, view, principal.user_id))
        tx.execute(
            "INSERT INTO bid_items (application_id, tenant_id, item_key, owner, due, status, note,"
            " evidence_ref, review, updated_by) VALUES (%s, current_tenant(), %s, %s, %s, %s, %s,"
            " %s, NULL, %s) ON CONFLICT (application_id, item_key) DO UPDATE SET"
            " owner = EXCLUDED.owner, due = EXCLUDED.due, status = EXCLUDED.status,"
            " note = EXCLUDED.note, evidence_ref = EXCLUDED.evidence_ref,"
            " review = CASE WHEN %s THEN bid_items.review END,"
            " updated_by = EXCLUDED.updated_by, updated_at = clock_timestamp()",
            (
                aid,
                key,
                merged["owner"],
                merged["due"],
                merged["status"],
                merged["note"],
                merged["evidence_ref"],
                principal.user_id,
                keep_review,
            ),
        )
        add_event(tx, aid, "bid", principal.user_id, action="item", key=key, fields=sorted(changes))
        return _respond(tx, aid, response)


@router.post("/bids/{grant_id}/items/{key}/review")
def review_item(
    grant_id: str,
    key: str,
    body: ReviewBody,
    principal: PrincipalDep,
    response: Response,
    if_match: IfMatch = None,
) -> BidView:
    """Simulated internal review (anyone signed in). Asking for changes needs a comment and
    moves the requirement back to in progress."""
    version = _version(if_match)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        aid = _bid_id(tx, grant_id)
        view, _, checklist = _load(tx, aid)
        _open(view)
        if key not in checklist:
            raise ProblemException(404, "item_not_found", "Requirement not found")
        current = next(i for i in view.items if i.key == key)
        if current.status != "ready":
            _refuse("bid_blocked", "Mark this requirement ready before reviewing it.")
        comment = body.comment.strip()
        if body.decision == "changes_requested" and not comment:
            raise ProblemException(
                422, "comment_required", "Add a comment explaining what to change."
            )
        review = {
            "by": str(principal.user_id),
            "at": datetime.now().astimezone().isoformat(),
            "decision": body.decision,
            "comment": comment,
            "hash": item_hash(checklist[key]),
        }
        status = "working" if body.decision == "changes_requested" else "ready"
        _bump(tx, aid, version, **_reopen(tx, view, principal.user_id))
        tx.execute(
            "UPDATE bid_items SET review = %s, status = %s, updated_by = %s,"
            " updated_at = clock_timestamp() WHERE application_id = %s AND item_key = %s",
            (Jsonb(review), status, principal.user_id, aid, key),
        )
        add_event(
            tx,
            aid,
            "bid",
            principal.user_id,
            action="review",
            key=key,
            decision=body.decision,
            comment=comment,
        )
        return _respond(tx, aid, response)


@router.post("/bids/{grant_id}/final-review")
def final_review(
    grant_id: str,
    body: FinalReviewBody,
    principal: PrincipalDep,
    response: Response,
    if_match: IfMatch = None,
) -> BidView:
    """The last internal sign-off, allowed only when nothing blocks the bid."""
    version = _version(if_match)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        aid = _bid_id(tx, grant_id)
        view = _load(tx, aid)[0]
        _open(view)
        if view.blocker_list:
            _refuse(
                "bid_blocked",
                "Clear every blocker first.",
                [b.model_dump(exclude_none=True) for b in view.blocker_list],
            )
        item = FinalReview(
            by=principal.user_id, at=datetime.now().astimezone(), comment=body.comment.strip()
        )
        _bump(tx, aid, version, final_review=item.model_dump(mode="json"))
        add_event(tx, aid, "bid", principal.user_id, action="final_review", comment=item.comment)
        return _respond(tx, aid, response)


@router.post("/bids/{grant_id}/submission")
def record_submission(
    grant_id: str,
    body: SubmissionBody,
    principal: PrincipalDep,
    response: Response,
    if_match: IfMatch = None,
) -> BidView:
    """Record the receipt from the funder's portal after staff submitted there. Hope never
    submits; once recorded, the bid is read-only and the application moves to `submitted`."""
    version = _version(if_match)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        aid = _bid_id(tx, grant_id)
        view = _load(tx, aid)[0]
        _open(view)
        if view.final_review is None:
            _refuse("bid_blocked", "Finish the final review first.")
        item = Submission(
            receipt=body.receipt.strip(),
            portal=body.portal.strip(),
            submitted_at=body.submitted_at,
            recorded_by=principal.user_id,
            recorded_at=datetime.now().astimezone(),
        )
        _bump(tx, aid, version, submission=item.model_dump(mode="json"))
        add_event(tx, aid, "bid", principal.user_id, action="submission", receipt=item.receipt)
        app = _row(tx, aid)
        _update(tx, aid, app["version"], stage="submitted")
        stage = {"from": app["stage"], "to": "submitted", "via": "bid_receipt"}
        add_event(tx, aid, "stage", principal.user_id, **stage)
        return _respond(tx, aid, response)


@router.get("/members")
def list_members(principal: PrincipalDep) -> MemberList:
    """The team, for assigning requirements."""
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        tx.execute("SELECT user_id, display_name FROM users ORDER BY display_name, user_id")
        return MemberList(items=[Member.model_validate(r) for r in tx.fetchall()])
