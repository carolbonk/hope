"""Grant candidate routes (H3): list, detail, and save / pass / reset of `grant_candidates`.

No model or web calls and no SQL here: every read and write goes through `hope_core.store`, and
every derived value (`days_left`, `urgency`, `fit_band`, `unverified`, sort, counts) is code.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Coroutine, Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from hope_core import store
from hope_core.auth import Principal, ProblemException, get_principal
from hope_core.db import connect, tenant_tx
from hope_core.money import Money
from hope_core.schemas.common import Contract
from hope_core.schemas.hackathon import CandidateStatus, Citation, GrantCandidate
from pydantic import BaseModel, Field, model_validator

Urgency = Literal["past", "urgent", "soon", "later", "rolling", "unknown"]
FitBand = Literal["strong", "good", "weak"]
GrantSort = Literal["fit", "deadline", "amount", "newest"]
PassReason = Literal["not_a_fit", "too_small", "deadline_too_soon", "not_eligible", "other"]

LIST_ITEMS = 3
MAX_CANDIDATES = 500
_TRAILING_MARKER = re.compile(r"\s*\[(c\d+)\](?=\s*(\[c\d+\]\s*)*$)")
_ANY_MARKER = re.compile(r"\s*\[(c\d+)\]")
_ROLLING = re.compile(r"rolling|ongoing|open until", re.IGNORECASE)
_WORD = re.compile(r"\w+")


# --- errors ------------------------------------------------------------------------------------


class InvalidQuery(ProblemException):
    """422 `invalid_query`; `detail` names the offending query parameter."""

    def __init__(self, parameter: str) -> None:
        super().__init__(422, "invalid_query", "Invalid query")
        self.parameter = parameter

    def body(self) -> dict[str, Any]:
        return super().body() | {"detail": self.parameter}


def grant_not_found() -> ProblemException:
    return ProblemException(404, "grant_not_found", "Grant not found")


def invalid_reason() -> ProblemException:
    return ProblemException(422, "invalid_reason", "Invalid reason")


class _GrantsRoute(APIRoute):
    """Maps FastAPI's request validation errors onto this router's problem codes."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def route(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                raise _problem_for(exc) from exc

        return route


def _problem_for(exc: RequestValidationError) -> ProblemException:
    locations = [tuple(err.get("loc", ())) for err in exc.errors()]
    for loc in locations:
        if loc and loc[0] == "query":
            return InvalidQuery(str(loc[1]) if len(loc) > 1 else "query")
    if any(loc and loc[0] == "path" for loc in locations):
        return grant_not_found()
    return invalid_reason()


router = APIRouter(prefix="/v1", tags=["grants"], route_class=_GrantsRoute)


# --- endpoint models ---------------------------------------------------------------------------


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
    status: CandidateStatus
    discovered_at: datetime


class GrantDetail(GrantCard):
    eligibility_summary: str | None
    summary_citation_ids: list[str]
    amount_citation_id: str | None
    deadline_citation_id: str | None
    found_by_job_id: UUID | None
    view_original_url: str


class StatusCounts(BaseModel):
    new: int
    saved: int
    passed: int


class GrantListPage(BaseModel):
    items: list[GrantCard]
    total: int
    limit: int
    offset: int
    counts: StatusCounts
    hidden_past: int


class StatusChange(BaseModel):
    grant_id: UUID
    status: CandidateStatus
    previous_status: CandidateStatus
    changed: bool


class PassBody(Contract):
    reason: PassReason | None = None
    reason_text: str | None = Field(None, max_length=300)

    @model_validator(mode="after")
    def _text_only_with_other(self) -> PassBody:
        if self.reason_text is not None and self.reason != "other":
            raise ValueError("reason_text is allowed only with reason 'other'")
        return self


# --- derived fields (code only) ------------------------------------------------------------------


def _today() -> date:
    return datetime.now(UTC).date()


def days_left(deadline: date | None, today: date) -> int | None:
    return None if deadline is None else (deadline - today).days


def urgency(days: int | None, deadline_text: str | None) -> Urgency:
    if days is None:
        return "rolling" if deadline_text and _ROLLING.search(deadline_text) else "unknown"
    if days < 0:
        return "past"
    if days <= 7:
        return "urgent"
    if days <= 21:
        return "soon"
    return "later"


def fit_band(score: int) -> FitBand:
    if score >= 75:
        return "strong"
    if score >= 55:
        return "good"
    return "weak"


def domain(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.")


def parse_cited(raw: str, known: set[str]) -> CitedItem:
    """Strip trailing `[cN]` markers; unknown or missing markers make the item unverified."""
    markers = [m.group(1) for m in _TRAILING_MARKER.finditer(raw)]
    text = _TRAILING_MARKER.sub("", raw).rstrip()
    ids = _unique(m for m in markers if m in known)
    unverified = not markers or len(ids) < len(set(markers))
    return CitedItem(text=text, citation_ids=ids, unverified=unverified)


def summary_markers(summary: str, known: set[str]) -> tuple[str, list[str]]:
    ids = _unique(m.group(1) for m in _ANY_MARKER.finditer(summary) if m.group(1) in known)
    return _ANY_MARKER.sub("", summary).strip(), ids


def first_quoting(citations: list[Citation], text: str | None) -> str | None:
    """The first citation whose quote contains `text`, or failing that every word of it."""
    if not text or not text.strip():
        return None
    needle = " ".join(text.lower().split())
    for c in citations:
        if needle in " ".join(c.quote.lower().split()):
            return c.citation_id
    words = set(_WORD.findall(needle))
    for c in citations:
        if words <= set(_WORD.findall(c.quote.lower())):
            return c.citation_id
    return None


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def to_detail(candidate: GrantCandidate, today: date) -> GrantDetail:
    known = {c.citation_id for c in candidate.citations}
    reasons = [parse_cited(r, known) for r in candidate.fit_reasons]
    concerns = [parse_cited(c, known) for c in candidate.concerns]
    summary, summary_ids = summary_markers(candidate.summary, known)
    days = days_left(candidate.deadline, today)
    return GrantDetail(
        grant_id=candidate.grant_id,
        title=candidate.title,
        funder=candidate.funder,
        url=candidate.url,
        domain=domain(candidate.url),
        summary=summary,
        amount_text=candidate.amount_text,
        amount_max=candidate.amount_max,
        deadline_text=candidate.deadline_text,
        deadline=candidate.deadline,
        days_left=days,
        urgency=urgency(days, candidate.deadline_text),
        fit_score=candidate.fit_score,
        fit_band=fit_band(candidate.fit_score),
        reasons=reasons,
        concerns=concerns,
        citations=list(candidate.citations),
        status=candidate.status,
        discovered_at=_utc(candidate.discovered_at),
        eligibility_summary=candidate.eligibility_summary,
        summary_citation_ids=summary_ids,
        amount_citation_id=first_quoting(candidate.citations, candidate.amount_text),
        deadline_citation_id=first_quoting(candidate.citations, candidate.deadline_text),
        found_by_job_id=candidate.found_by_job_id,
        view_original_url=candidate.url,
    )


def to_card(detail: GrantDetail) -> GrantCard:
    reasons, concerns = detail.reasons[:LIST_ITEMS], detail.concerns[:LIST_ITEMS]
    used = {i for item in (*reasons, *concerns) for i in item.citation_ids}
    used |= set(detail.summary_citation_ids)
    card = {k: getattr(detail, k) for k in GrantCard.model_fields}
    card |= {
        "reasons": reasons,
        "concerns": concerns,
        "citations": [c for c in detail.citations if c.citation_id in used],
    }
    return GrantCard(**card)


# --- sorting and filtering -----------------------------------------------------------------------


def _sort_key(sort: GrantSort) -> Callable[[GrantDetail], tuple[Any, ...]]:
    def fit(g: GrantDetail) -> tuple[Any, ...]:
        return (-g.fit_score, g.deadline is None, g.deadline or date.max, str(g.grant_id))

    def deadline(g: GrantDetail) -> tuple[Any, ...]:
        rank = 0 if g.deadline else (1 if g.urgency == "rolling" else 2)
        return (rank, g.deadline or date.max, -g.fit_score, str(g.grant_id))

    def amount(g: GrantDetail) -> tuple[Any, ...]:
        usd = g.amount_max is not None and g.amount_max.currency == "USD"
        minor = g.amount_max.amount_minor if g.amount_max and usd else 0
        return (not usd, -minor, -g.fit_score, str(g.grant_id))

    def newest(g: GrantDetail) -> tuple[Any, ...]:
        return (-g.discovered_at.timestamp(), str(g.grant_id))

    keys: dict[str, Callable[[GrantDetail], tuple[Any, ...]]] = {
        "fit": fit,
        "deadline": deadline,
        "amount": amount,
        "newest": newest,
    }
    return keys[sort]


def _matches(g: GrantDetail, q: str) -> bool:
    needle = q.casefold()
    return any(needle in field.casefold() for field in (g.title, g.funder, g.summary, g.domain))


# --- routes --------------------------------------------------------------------------------------

PrincipalDep = Annotated[Principal, Depends(get_principal)]


@contextmanager
def _tx(principal: Principal) -> Iterator[store.Tx]:
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        yield tx


@router.get("/grants")
def list_grants(
    principal: PrincipalDep,
    status: CandidateStatus = "new",
    sort: GrantSort = "fit",
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    deadline_within_days: Annotated[int | None, Query(ge=1, le=365)] = None,
    include_past: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GrantListPage:
    with _tx(principal) as tx:
        rows = store.list_candidates(tx, status, "fit", limit=MAX_CANDIDATES, offset=0)
        counts = store.count_candidates(tx)
    today = _today()
    grants = [to_detail(c, today) for c in rows]
    if q is not None:
        grants = [g for g in grants if _matches(g, q)]
    hidden_past = 0
    if status != "passed" and not include_past:
        hidden_past = sum(g.urgency == "past" for g in grants)
        grants = [g for g in grants if g.urgency != "past"]
    if deadline_within_days is not None:
        grants = [
            g
            for g in grants
            if g.days_left is not None and 0 <= g.days_left <= deadline_within_days
        ]
    grants.sort(key=_sort_key(sort))
    return GrantListPage(
        items=[to_card(g) for g in grants[offset : offset + limit]],
        total=len(grants),
        limit=limit,
        offset=offset,
        counts=StatusCounts(**counts),
        hidden_past=hidden_past,
    )


@router.get("/grants/{grant_id}")
def get_grant(grant_id: UUID, principal: PrincipalDep) -> GrantDetail:
    with _tx(principal) as tx:
        candidate = store.get_candidate(tx, grant_id)
    if candidate is None:
        raise grant_not_found()
    return to_detail(candidate, _today())


def _set_status(
    principal: Principal,
    grant_id: UUID,
    status: CandidateStatus,
    body: PassBody | None = None,
) -> StatusChange:
    with _tx(principal) as tx:
        current = store.get_candidate(tx, grant_id)
        if current is None:
            raise grant_not_found()
        changed = current.status != status
        if changed:
            store.set_candidate_status(
                tx,
                grant_id,
                status,
                reason=body.reason if body else None,
                reason_text=body.reason_text if body else None,
                actor=principal.user_id,
            )
    return StatusChange(
        grant_id=grant_id, status=status, previous_status=current.status, changed=changed
    )


@router.post("/grants/{grant_id}/save")
def save_grant(grant_id: UUID, principal: PrincipalDep) -> StatusChange:
    return _set_status(principal, grant_id, "saved")


@router.post("/grants/{grant_id}/pass")
def pass_grant(
    grant_id: UUID, principal: PrincipalDep, body: Annotated[PassBody | None, Body()] = None
) -> StatusChange:
    return _set_status(principal, grant_id, "passed", body)


@router.post("/grants/{grant_id}/reset")
def reset_grant(grant_id: UUID, principal: PrincipalDep) -> StatusChange:
    return _set_status(principal, grant_id, "new")
