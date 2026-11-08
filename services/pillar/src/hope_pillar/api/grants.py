"""Grant candidate routes (H3): list, detail, and save / pass / reset. All code, no model calls."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal, NoReturn, cast, get_args
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from hope_core import store
from hope_core.auth import Principal, ProblemException, get_principal
from hope_core.db import connect, tenant_tx
from hope_core.money import Money
from hope_core.schemas import Citation, GrantCandidate
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from hope_pillar.api.applications import ensure_application
from hope_pillar.api.requirements_autostart import start_requirements_once

router = APIRouter(prefix="/v1", tags=["grants"])

Status = Literal["new", "saved", "passed"]
Urgency = Literal["past", "urgent", "soon", "later", "rolling", "unknown"]
FitBand = Literal["strong", "good", "weak"]
PassReason = Literal["not_a_fit", "too_small", "deadline_too_soon", "not_eligible", "other"]

LIST_ITEMS = 3
SCAN_LIMIT = 500
_TRAILING_MARKER = re.compile(r"\s*\[(c\d+)\](?=\s*(\[c\d+\]\s*)*$)")
_ANY_MARKER = re.compile(r"\s*\[(c\d+)\]")
_ROLLING = re.compile(r"rolling|ongoing|open until", re.IGNORECASE)


class CitedItem(BaseModel):
    text: str
    citation_ids: list[str]
    unverified: bool


class GrantCard(BaseModel):
    grant_id: UUID
    title: str
    funder: str
    url: str
    domain: str
    summary: str
    amount_text: str | None
    amount_max: Money | None
    deadline_text: str | None
    deadline: date | None
    days_left: int | None
    urgency: Urgency
    fit_score: int
    fit_band: FitBand
    reasons: list[CitedItem]
    concerns: list[CitedItem]
    citations: list[Citation]
    status: Status
    discovered_at: datetime


class GrantDetail(GrantCard):
    eligibility_summary: str | None
    summary_citation_ids: list[str]
    amount_citation_id: str | None
    deadline_citation_id: str | None
    found_by_job_id: UUID | None
    view_original_url: str


class Counts(BaseModel):
    new: int
    saved: int
    passed: int


class GrantListPage(BaseModel):
    items: list[GrantCard]
    total: int
    limit: int
    offset: int
    counts: Counts
    hidden_past: int


class StatusChange(BaseModel):
    grant_id: UUID
    status: Status
    previous_status: Status
    changed: bool


class PassBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: PassReason | None = None
    reason_text: str | None = Field(None, max_length=300)

    @model_validator(mode="after")
    def _text_only_with_other(self) -> PassBody:
        if self.reason_text is not None and self.reason != "other":
            raise ValueError("reason_text is allowed only with reason 'other'")
        return self


class _QueryProblem(ProblemException):
    def __init__(self, param: str) -> None:
        super().__init__(422, "invalid_query", "Invalid query")
        self.param = param

    def body(self) -> dict[str, Any]:
        return super().body() | {"detail": self.param}


def _today() -> date:
    return datetime.now(UTC).date()


# --- derived fields (code decides) ------------------------------------------------------------


def days_left(deadline: date | None, today: date) -> int | None:
    return None if deadline is None else (deadline - today).days


def urgency(deadline: date | None, deadline_text: str | None, today: date) -> Urgency:
    days = days_left(deadline, today)
    if days is None:
        return "rolling" if deadline_text and _ROLLING.search(deadline_text) else "unknown"
    if days < 0:
        return "past"
    if days <= 7:
        return "urgent"
    return "soon" if days <= 21 else "later"


def fit_band(score: int) -> FitBand:
    return "strong" if score >= 75 else "good" if score >= 55 else "weak"


def domain(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.")


def cited_item(raw: str, known: set[str]) -> CitedItem:
    """Parse trailing `[cN]` markers; unknown ones are dropped and mark the item unverified."""
    markers = [m.group(1) for m in _TRAILING_MARKER.finditer(raw)]
    ids = list(dict.fromkeys(m for m in markers if m in known))
    text = _TRAILING_MARKER.sub("", raw).strip()
    unverified = not markers or len(ids) < len(set(markers))
    return CitedItem(text=text, citation_ids=ids, unverified=unverified)


def _summary(raw: str, known: set[str]) -> tuple[str, list[str]]:
    ids = [m.group(1) for m in _ANY_MARKER.finditer(raw) if m.group(1) in known]
    return _ANY_MARKER.sub("", raw).strip(), list(dict.fromkeys(ids))


def _quoting(citations: list[Citation], text: str | None) -> str | None:
    if not text:
        return None
    needle = text.casefold()
    return next((c.citation_id for c in citations if needle in c.quote.casefold()), None)


def _card_fields(g: GrantCandidate, today: date, items: int | None) -> dict[str, Any]:
    known = {c.citation_id for c in g.citations}
    reasons = [cited_item(r, known) for r in g.fit_reasons[:items]]
    concerns = [cited_item(c, known) for c in g.concerns[:items]]
    summary, summary_ids = _summary(g.summary, known)
    return {
        "grant_id": g.grant_id,
        "title": g.title,
        "funder": g.funder,
        "url": g.url,
        "domain": domain(g.url),
        "summary": summary,
        "amount_text": g.amount_text,
        "amount_max": g.amount_max,
        "deadline_text": g.deadline_text,
        "deadline": g.deadline,
        "days_left": days_left(g.deadline, today),
        "urgency": urgency(g.deadline, g.deadline_text, today),
        "fit_score": g.fit_score,
        "fit_band": fit_band(g.fit_score),
        "reasons": reasons,
        "concerns": concerns,
        "citations": g.citations,
        "status": g.status,
        "discovered_at": g.discovered_at,
        "summary_citation_ids": summary_ids,
    }


def to_card(g: GrantCandidate, today: date) -> GrantCard:
    fields = _card_fields(g, today, LIST_ITEMS)
    used = set(fields.pop("summary_citation_ids"))
    for item in (*fields["reasons"], *fields["concerns"]):
        used.update(item.citation_ids)
    fields["citations"] = [c for c in g.citations if c.citation_id in used]
    return GrantCard(**fields)


def to_detail(g: GrantCandidate, today: date) -> GrantDetail:
    return GrantDetail(
        **_card_fields(g, today, None),
        eligibility_summary=g.eligibility_summary,
        amount_citation_id=_quoting(g.citations, g.amount_text),
        deadline_citation_id=_quoting(g.citations, g.deadline_text),
        found_by_job_id=g.found_by_job_id,
        view_original_url=g.url,
    )


# --- listing ----------------------------------------------------------------------------------

Sort = Literal["fit", "deadline", "amount", "newest"]
_DEADLINE_RANK = {"rolling": 1, "unknown": 2}


def _sort_key(sort: Sort) -> Any:
    def by_deadline(c: GrantCard) -> tuple[int, int]:
        return (c.days_left, 0) if c.days_left is not None else (10**6, 1)

    def amount(c: GrantCard) -> int | None:
        usd = c.amount_max is not None and c.amount_max.currency == "USD"
        return c.amount_max.amount_minor if usd and c.amount_max else None

    if sort == "fit":
        return lambda c: (-c.fit_score, *by_deadline(c), str(c.grant_id))
    if sort == "deadline":
        return lambda c: (
            0 if c.days_left is not None else _DEADLINE_RANK.get(c.urgency, 2),
            c.days_left or 0,
            -c.fit_score,
            str(c.grant_id),
        )
    if sort == "amount":
        return lambda c: (amount(c) is None, -(amount(c) or 0), -c.fit_score, str(c.grant_id))
    return lambda c: (-c.discovered_at.timestamp(), -c.fit_score, str(c.grant_id))


def _choice(params: dict[str, str], name: str, options: tuple[str, ...], default: str) -> str:
    value = params.get(name, default)
    if value not in options:
        raise _QueryProblem(name)
    return value


def _int(params: dict[str, str], name: str, low: int, high: int | None) -> int | None:
    raw = params.get(name)
    if raw is None:
        return None
    if (
        not re.fullmatch(r"[0-9]{1,9}", raw)
        or int(raw) < low
        or (high is not None and int(raw) > high)
    ):
        raise _QueryProblem(name)
    return int(raw)


def _bool(params: dict[str, str], name: str) -> bool:
    raw = params.get(name, "false").lower()
    if raw not in ("true", "false", "1", "0"):
        raise _QueryProblem(name)
    return raw in ("true", "1")


def _matches(card: GrantCard, q: str) -> bool:
    haystack = (card.title, card.funder, card.summary, card.domain)
    return any(q in field.casefold() for field in haystack)


QueryParam = Annotated[str | None, Query()]


@router.get("/grants")
def list_grants(
    principal: Annotated[Principal, Depends(get_principal)],
    status: QueryParam = None,
    sort: QueryParam = None,
    q: QueryParam = None,
    deadline_within_days: QueryParam = None,
    include_past: QueryParam = None,
    limit: QueryParam = None,
    offset: QueryParam = None,
) -> GrantListPage:
    """Grant cards. Values are checked here, so a bad one returns 422 `invalid_query` naming it."""
    raw = {
        "status": status,
        "sort": sort,
        "deadline_within_days": deadline_within_days,
        "include_past": include_past,
        "limit": limit,
        "offset": offset,
    }
    params = {k: v for k, v in raw.items() if v is not None}
    want = cast(Status, _choice(params, "status", get_args(Status), "new"))
    order = cast(Sort, _choice(params, "sort", get_args(Sort), "fit"))
    if q is not None and not 1 <= len(q.strip()) <= 100:
        raise _QueryProblem("q")
    within = _int(params, "deadline_within_days", 1, 365)
    past = _bool(params, "include_past")
    page_size = _int(params, "limit", 1, 100) or 20
    start = _int(params, "offset", 0, None) or 0

    today = _today()
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        rows = store.list_candidates(tx, want, "fit", limit=SCAN_LIMIT, offset=0)
        counts = store.count_candidates(tx)

    cards = [to_card(g, today) for g in rows]
    if q is not None:
        needle = q.strip().casefold()
        cards = [c for c in cards if _matches(c, needle)]
    hidden_past = 0
    if want != "passed" and not past:
        hidden_past = sum(c.urgency == "past" for c in cards)
        cards = [c for c in cards if c.urgency != "past"]
    if within is not None:
        cards = [c for c in cards if c.days_left is not None and 0 <= c.days_left <= within]
    cards.sort(key=_sort_key(order))
    return GrantListPage(
        items=cards[start : start + page_size],
        total=len(cards),
        limit=page_size,
        offset=start,
        counts=Counts(**counts),
        hidden_past=hidden_past,
    )


# --- detail and status ------------------------------------------------------------------------


def _not_found() -> NoReturn:
    raise ProblemException(404, "grant_not_found", "Grant not found")


def _grant_uuid(grant_id: str) -> UUID:
    try:
        return UUID(grant_id)
    except ValueError:
        _not_found()


@router.get("/grants/{grant_id}")
def get_grant(
    grant_id: str, principal: Annotated[Principal, Depends(get_principal)]
) -> GrantDetail:
    gid = _grant_uuid(grant_id)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        grant = store.get_candidate(tx, gid)
    if grant is None:
        _not_found()
    return to_detail(grant, _today())


def _set_status(
    principal: Principal, grant_id: str, status: Status, body: PassBody | None = None
) -> StatusChange:
    gid = _grant_uuid(grant_id)
    application_id = None
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        grant = store.get_candidate(tx, gid)
        if grant is None:
            _not_found()
        previous = grant.status
        if previous != status:
            store.set_candidate_status(
                tx,
                gid,
                status,
                reason=body.reason if body else None,
                reason_text=body.reason_text if body else None,
                actor=principal.user_id,
            )
        if status == "saved":
            application_id = ensure_application(tx, gid, principal.user_id)
    if application_id is not None:
        start_requirements_once(principal.tenant_id, application_id, principal.user_id)
    return StatusChange(
        grant_id=gid, status=status, previous_status=previous, changed=previous != status
    )


async def _pass_body(request: Request) -> PassBody | None:
    """Optional JSON body; anything but a valid `PassBody` is 422 `invalid_reason`."""
    raw = await request.body()
    if not raw.strip():
        return None
    try:
        return PassBody.model_validate(json.loads(raw))
    except (ValueError, ValidationError):
        raise ProblemException(422, "invalid_reason", "Invalid reason") from None


_PASS_BODY_DOC: dict[str, Any] = {
    "requestBody": {
        "required": False,
        "content": {"application/json": {"schema": PassBody.model_json_schema()}},
    }
}


@router.post("/grants/{grant_id}/save")
def save_grant(
    grant_id: str, principal: Annotated[Principal, Depends(get_principal)]
) -> StatusChange:
    return _set_status(principal, grant_id, "saved")


@router.post("/grants/{grant_id}/pass", openapi_extra=_PASS_BODY_DOC)
def pass_grant(
    grant_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    body: Annotated[PassBody | None, Depends(_pass_body)],
) -> StatusChange:
    return _set_status(principal, grant_id, "passed", body)


@router.post("/grants/{grant_id}/reset")
def reset_grant(
    grant_id: str, principal: Annotated[Principal, Depends(get_principal)]
) -> StatusChange:
    return _set_status(principal, grant_id, "new")
