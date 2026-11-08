"""Application routes (H6, step 1): the server-side application record, its stage gates,
eligibility evidence, simulated approvals, comments and activity. All code, no model calls."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from hope_core.auth import Principal, ProblemException, get_principal
from hope_core.db import connect, tenant_tx
from hope_core.money import Money
from hope_core.store import Tx
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/v1", tags=["applications"])

Stage = Literal["saved", "eligibility", "approval", "drafting", "ready"]
Step = Literal["program", "director"]
EvidenceStatus = Literal["yes", "no", "unknown"]
QuestionsStatus = Literal["unread", "reading", "found", "not_found"]
EventKind = Literal[
    "created",
    "stage",
    "comment",
    "evidence",
    "approval",
    "send_back",
    "requirements",
    "draft",
    "edit",
]

EVENTS_SHOWN = 50
# Stage moves a caller may ask for; approval -> drafting happens only via director approval.
MOVES: dict[tuple[str, str], str | None] = {
    ("saved", "eligibility"): None,
    ("eligibility", "approval"): "Resolve unknown or failed requirements first.",
    ("drafting", "ready"): "Both reviews must approve first.",
    ("ready", "drafting"): None,
}


class Approval(BaseModel):
    by: UUID
    at: datetime
    comment: str | None = None


class Evidence(BaseModel):
    status: EvidenceStatus
    note: str | None = None
    by: UUID
    at: datetime


class EventView(BaseModel):
    kind: EventKind
    actor: UUID | None
    payload: dict[str, Any]
    at: datetime


class ApplicationSummary(BaseModel):
    application_id: UUID
    grant_id: UUID
    title: str
    funder: str
    url: str
    deadline: date | None
    deadline_text: str | None
    stage: Stage
    questions_status: QuestionsStatus
    updated_at: datetime


class ApplicationView(ApplicationSummary):
    version: int
    ask: Money | None
    approvals: dict[Step, Approval]
    evidence: dict[str, Evidence]
    events: list[EventView]
    created_at: datetime


class ApplicationList(BaseModel):
    items: list[ApplicationSummary]
    total: int


class StageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: Stage


class EvidenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: str = Field(min_length=1, max_length=80)
    status: EvidenceStatus
    note: str | None = Field(None, max_length=500)


class ApprovalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: Step
    decision: Literal["approve", "send_back"]
    comment: str | None = Field(None, max_length=1000)


class CommentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)


# --- store ------------------------------------------------------------------------------------

_SELECT = (
    "SELECT a.*, g.title, g.funder, g.url, g.deadline, g.deadline_text"
    " FROM applications a JOIN grant_candidates g USING (grant_id)"
)


def add_event(
    tx: Tx, application_id: UUID, kind: EventKind, actor: UUID | None, **payload: Any
) -> None:
    tx.execute(
        "INSERT INTO application_events (application_id, tenant_id, kind, actor, payload)"
        " VALUES (%s, current_tenant(), %s, %s, %s)",
        (application_id, kind, actor, Jsonb(payload)),
    )


def ensure_application(tx: Tx, grant_id: UUID, actor: UUID | None) -> UUID:
    """The one application for a grant; saving again (after pass or reset) reuses it."""
    tx.execute(
        "INSERT INTO applications (tenant_id, grant_id, created_by)"
        " VALUES (current_tenant(), %s, %s)"
        " ON CONFLICT (tenant_id, grant_id) DO NOTHING RETURNING application_id",
        (grant_id, actor),
    )
    row = tx.fetchone()
    if row is not None:
        add_event(tx, row["application_id"], "created", actor)
        return UUID(str(row["application_id"]))
    tx.execute("SELECT application_id FROM applications WHERE grant_id = %s", (grant_id,))
    found = tx.fetchone()
    assert found is not None
    return UUID(str(found["application_id"]))


def _row(tx: Tx, application_id: UUID) -> dict[str, Any]:
    tx.execute(f"{_SELECT} WHERE a.application_id = %s", (application_id,))
    row = tx.fetchone()
    if row is None:
        _not_found()
    return row


def _view(tx: Tx, row: dict[str, Any]) -> ApplicationView:
    tx.execute(
        "SELECT kind, actor, payload, at FROM application_events"
        " WHERE application_id = %s ORDER BY at DESC LIMIT %s",
        (row["application_id"], EVENTS_SHOWN),
    )
    events = [EventView.model_validate(e) for e in tx.fetchall()]
    ask = (
        Money(amount_minor=row["ask_minor"], currency=row["currency"]) if row["ask_minor"] else None
    )
    return ApplicationView.model_validate(row | {"ask": ask, "events": events})


def _update(tx: Tx, application_id: UUID, version: int, **fields: Any) -> None:
    """Optimistic write: bumps `version`, or 412 when the caller's copy is stale."""
    sets = ", ".join(f"{k} = %s" for k in fields)
    values = [Jsonb(v) if isinstance(v, dict) else v for v in fields.values()]
    tx.execute(
        f"UPDATE applications SET {sets}{', ' if sets else ''}version = version + 1,"
        " updated_at = clock_timestamp() WHERE application_id = %s AND version = %s",
        (*values, application_id, version),
    )
    if tx.rowcount == 0:
        raise ProblemException(412, "version_mismatch", "This application changed; reload it")


# --- rules (code decides) ---------------------------------------------------------------------


def move_problem(row: dict[str, Any], to: str) -> str | None:
    """Why `row` can't move to stage `to`, or None when it can."""
    key = (row["stage"], to)
    if key not in MOVES:
        return f"Can't move from {row['stage']} to {to}."
    if to == "approval" and any(e["status"] != "yes" for e in row["evidence"].values()):
        return MOVES[key]
    if to == "ready" and set(row["approvals"]) != {"program", "director"}:
        return MOVES[key]
    return None


# --- helpers ----------------------------------------------------------------------------------


def _not_found() -> NoReturn:
    raise ProblemException(404, "application_not_found", "Application not found")


def _blocked(reason: str) -> NoReturn:
    raise ProblemException(
        409,
        "stage_blocked",
        "Stage blocked",
        [{"field": "stage", "code": "blocked", "message": reason}],
    )


def _app_uuid(application_id: str) -> UUID:
    try:
        return UUID(application_id)
    except ValueError:
        _not_found()


def _version(if_match: str | None) -> int:
    if if_match is None:
        raise ProblemException(428, "if_match_required", "If-Match required")
    try:
        return int(if_match.removeprefix("W/").strip().strip('"'))
    except ValueError:
        raise ProblemException(400, "invalid_if_match", "If-Match must be a version") from None


def _respond(tx: Tx, application_id: UUID, response: Response) -> ApplicationView:
    view = _view(tx, _row(tx, application_id))
    response.headers["ETag"] = f'"{view.version}"'
    return view


PrincipalDep = Annotated[Principal, Depends(get_principal)]
IfMatch = Annotated[str | None, Header()]


# --- routes -----------------------------------------------------------------------------------


@router.get("/applications")
def list_applications(principal: PrincipalDep) -> ApplicationList:
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        tx.execute(f"{_SELECT} ORDER BY g.deadline NULLS LAST, a.updated_at DESC")
        items = [ApplicationSummary.model_validate(r) for r in tx.fetchall()]
    return ApplicationList(items=items, total=len(items))


@router.get("/applications/{application_id}")
def get_application(
    application_id: str, principal: PrincipalDep, response: Response
) -> ApplicationView:
    aid = _app_uuid(application_id)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        return _respond(tx, aid, response)


@router.post("/applications/{application_id}/stage")
def move_stage(
    application_id: str,
    body: StageBody,
    principal: PrincipalDep,
    response: Response,
    if_match: IfMatch = None,
) -> ApplicationView:
    aid, version = _app_uuid(application_id), _version(if_match)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        row = _row(tx, aid)
        if reason := move_problem(row, body.to):
            _blocked(reason)
        _update(tx, aid, version, stage=body.to)
        add_event(tx, aid, "stage", principal.user_id, **{"from": row["stage"], "to": body.to})
        return _respond(tx, aid, response)


@router.post("/applications/{application_id}/evidence")
def record_evidence(
    application_id: str,
    body: EvidenceBody,
    principal: PrincipalDep,
    response: Response,
    if_match: IfMatch = None,
) -> ApplicationView:
    aid, version = _app_uuid(application_id), _version(if_match)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        row = _row(tx, aid)
        if row["stage"] not in ("saved", "eligibility"):
            _blocked("Eligibility is locked once the application is in review.")
        item = Evidence(
            status=body.status, note=body.note, by=principal.user_id, at=datetime.now().astimezone()
        )
        evidence = row["evidence"] | {body.requirement_id: item.model_dump(mode="json")}
        _update(tx, aid, version, evidence=evidence)
        add_event(
            tx,
            aid,
            "evidence",
            principal.user_id,
            requirement_id=body.requirement_id,
            status=body.status,
        )
        return _respond(tx, aid, response)


@router.post("/applications/{application_id}/approvals")
def review(
    application_id: str,
    body: ApprovalBody,
    principal: PrincipalDep,
    response: Response,
    if_match: IfMatch = None,
) -> ApplicationView:
    """Simulated internal review: program, then director. Never a funder decision."""
    aid, version = _app_uuid(application_id), _version(if_match)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        row = _row(tx, aid)
        if row["stage"] != "approval":
            _blocked("Send the application to internal approval first.")
        if body.decision == "send_back":
            if not (body.comment or "").strip():
                raise ProblemException(
                    422, "comment_required", "Add a comment explaining what to change."
                )
            _update(tx, aid, version, stage="eligibility", approvals={})
            add_event(tx, aid, "send_back", principal.user_id, step=body.step, comment=body.comment)
            return _respond(tx, aid, response)
        if body.step == "director" and "program" not in row["approvals"]:
            _blocked("Program review must approve first.")
        item = Approval(by=principal.user_id, at=datetime.now().astimezone(), comment=body.comment)
        approvals = row["approvals"] | {body.step: item.model_dump(mode="json")}
        stage = "drafting" if body.step == "director" else row["stage"]
        _update(tx, aid, version, approvals=approvals, stage=stage)
        add_event(tx, aid, "approval", principal.user_id, step=body.step)
        return _respond(tx, aid, response)


@router.post("/applications/{application_id}/comments")
def comment(
    application_id: str, body: CommentBody, principal: PrincipalDep, response: Response
) -> ApplicationView:
    """Comments append to the activity log and don't change the version."""
    aid = _app_uuid(application_id)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        _row(tx, aid)
        add_event(tx, aid, "comment", principal.user_id, text=body.text)
        return _respond(tx, aid, response)
