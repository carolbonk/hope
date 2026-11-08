"""Discovery routes (H2): start a run, poll its steps, list past runs."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from hope_core import jobs, store
from hope_core.auth import Principal, ProblemException, get_principal
from hope_core.db import connect, tenant_tx
from hope_core.money import Money
from hope_core.schemas import AgencyProfile
from hope_core.schemas.hackathon import CandidateStatus, DiscoveryJob, JobStatus
from hope_core.store import Tx
from hope_discovery import repo
from hope_discovery.agent import empty_counts
from hope_discovery.runner import run_discovery
from hope_discovery.settings import get_discovery_settings
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer


class _DiscoveryRoute(APIRoute):
    """Bad input is 422 `validation_error` on these routes (spec H2 section A)."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def route(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                errors = [
                    {
                        "field": ".".join(str(p) for p in e["loc"] if p != "body") or "body",
                        "code": str(e["type"]),
                        "message": str(e["msg"]),
                    }
                    for e in exc.errors()
                ]
                raise ProblemException(
                    422, "validation_error", "Check the highlighted fields", errors
                ) from None

        return route


router = APIRouter(prefix="/v1", tags=["discovery"], route_class=_DiscoveryRoute)


class _Problem(ProblemException):
    def __init__(self, status: int, code: str, title: str, **extra: Any) -> None:
        super().__init__(status, code, title)
        self.extra = extra

    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = super().body() | jsonable_encoder(self.extra)
        return body


# --- view models (shapes: contracts/mocks/w3) -----------------------------------------------------


class StartDiscoveryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus_keywords: list[str] = Field(default_factory=list, max_length=5)
    location: str | None = None

    @field_validator("focus_keywords")
    @classmethod
    def _keywords(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for raw in value:
            word = " ".join(raw.split())
            if not 2 <= len(word) <= 40:
                raise ValueError("each keyword must be 2-40 characters")
            if word.lower() not in {w.lower() for w in out}:
                out.append(word)
        return out

    @field_validator("location")
    @classmethod
    def _location(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        if not 2 <= len(value) <= 80:
            raise ValueError("location must be 2-80 characters")
        return value


class DiscoveryRequest(BaseModel):
    focus_keywords: list[str]
    location: str | None


class DiscoveryCounts(BaseModel):
    urls_found: int = 0
    pages_read: int = 0
    candidates_new: int = 0
    candidates_updated: int = 0
    skipped_expired: int = 0
    skipped_not_grant: int = 0
    skipped_known: int = 0
    failed_pages: int = 0
    queries_failed: int = 0


StepKind = Literal["info", "query", "page", "skip", "candidate", "warning", "error"]


class DiscoveryStep(BaseModel):
    """Optional fields (`query`, `result_count`, `url`, `grant_id`, `is_new`) appear when set."""

    seq: int
    at: datetime
    kind: StepKind
    text: str
    query: str | None = None
    url: str | None = None
    grant_id: UUID | None = None
    is_new: bool | None = None
    result_count: int | None = None

    @model_serializer(mode="wrap")
    def _drop_unset(self, handler: Any) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        return {k: v for k, v in data.items() if v is not None}


class JobCandidate(BaseModel):
    grant_id: UUID
    title: str
    funder: str
    url: str
    fit_score: int
    amount_text: str | None
    amount_max: Money | None
    deadline_text: str | None
    deadline: date | None
    summary: str
    is_new: bool
    status: CandidateStatus


class DiscoveryLimits(BaseModel):
    max_queries: int
    max_pages: int
    timeout_s: int


class DiscoveryJobView(BaseModel):
    job: DiscoveryJob
    request: DiscoveryRequest
    counts: DiscoveryCounts
    steps: list[DiscoveryStep]
    last_seq: int
    candidates: list[JobCandidate]
    elapsed_s: int
    limits: DiscoveryLimits


class DiscoveryRunSummary(BaseModel):
    job_id: UUID
    status: JobStatus
    started_at: datetime
    finished_at: datetime | None
    request: DiscoveryRequest
    queries_total: int
    pages_read: int
    candidates_found: int
    candidates_new: int
    error: str | None


class DiscoveryRunList(BaseModel):
    items: list[DiscoveryRunSummary]
    running_job_id: UUID | None


# --- helpers ---------------------------------------------------------------------------------


def missing_profile_fields(profile: AgencyProfile | None) -> list[str]:
    missing = []
    if profile is None or not profile.mission.mission_statement.strip():
        missing.append("mission.mission_statement")
    if profile is None or not profile.programs:
        missing.append("programs")
    return missing


def day_window(now: datetime, tz: str) -> tuple[datetime, datetime]:
    """(local midnight today, next local midnight), both in UTC."""
    local = now.astimezone(ZoneInfo(tz))
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)  # wall-clock arithmetic: the next local midnight
    return start.astimezone(UTC), end.astimezone(UTC)


def _counts(raw: dict[str, Any] | None) -> DiscoveryCounts:
    return DiscoveryCounts.model_validate(empty_counts() | (raw or {}))


def _request(run: dict[str, Any]) -> DiscoveryRequest:
    return DiscoveryRequest(
        focus_keywords=list(run["focus_keywords"] or []), location=run["location"]
    )


def build_view(tx: Tx, job_id: UUID, since_seq: int = 0) -> DiscoveryJobView | None:
    job = store.get_job(tx, job_id)
    run = repo.get_run(tx, job_id)
    if job is None or job.kind != repo.KIND or run is None:
        return None
    s = get_discovery_settings()
    end = job.finished_at or datetime.now(UTC)
    candidates = [
        JobCandidate(
            grant_id=c.grant_id,
            title=c.title,
            funder=c.funder,
            url=c.url,
            fit_score=c.fit_score,
            amount_text=c.amount_text,
            amount_max=c.amount_max,
            deadline_text=c.deadline_text,
            deadline=c.deadline,
            summary=c.summary,
            is_new=is_new,
            status=c.status,
        )
        for c, is_new in repo.job_candidates(tx, job_id)
    ]
    return DiscoveryJobView(
        job=job.as_discovery_job(list(run["queries"] or [])),
        request=_request(run),
        counts=_counts(run["counts"]),
        steps=[DiscoveryStep.model_validate(e) for e in repo.list_events(tx, job_id, since_seq)],
        last_seq=repo.last_seq(tx, job_id),
        candidates=candidates,
        elapsed_s=max(0, int((end - job.started_at).total_seconds())),
        limits=DiscoveryLimits(
            max_queries=s.max_queries, max_pages=s.max_candidate_urls, timeout_s=s.job_timeout_s
        ),
    )


# --- routes ----------------------------------------------------------------------------------


@router.post("/discovery/jobs", status_code=202)
def start_discovery(
    principal: Annotated[Principal, Depends(get_principal)],
    body: StartDiscoveryBody | None = None,
) -> DiscoveryJobView:
    body = body or StartDiscoveryBody()
    s = get_discovery_settings()
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        profile = store.get_profile(tx)
        if missing := missing_profile_fields(profile):
            raise _Problem(422, "profile_incomplete", "Finish your profile first", missing=missing)
        repo.lock(tx)
        if (running := repo.active_job_id(tx)) is not None:
            raise _Problem(409, "job_running", "A run is already going", job_id=running)
        start, resets_at = day_window(datetime.now(UTC), s.tz)
        if repo.jobs_since(tx, start) >= s.daily_limit:
            raise _Problem(
                429,
                "daily_limit",
                "Daily limit reached",
                limit=s.daily_limit,
                resets_at=resets_at.isoformat().replace("+00:00", "Z"),
            )
        job = store.create_job(tx, repo.KIND, created_by=principal.user_id)
        repo.insert_run(
            tx,
            job.job_id,
            body.focus_keywords,
            body.location,
            profile.version if profile else None,
            principal.user_id,
        )
        view = build_view(tx, job.job_id)
    assert view is not None
    jobs.start_job(
        repo.KIND, run_discovery, job.job_id, job_id=job.job_id, created_by=principal.user_id
    )
    return view


@router.get("/discovery/jobs/{job_id}")
def get_discovery_job(
    job_id: UUID,
    principal: Annotated[Principal, Depends(get_principal)],
    since_seq: Annotated[int, Query(ge=0)] = 0,
) -> DiscoveryJobView:
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        view = build_view(tx, job_id, since_seq)
    if view is None:
        raise ProblemException(404, "not_found", "Job not found")
    return view


@router.get("/discovery/jobs")
def list_discovery_jobs(
    principal: Annotated[Principal, Depends(get_principal)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> DiscoveryRunList:
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        rows = repo.list_runs(tx, limit)
        running = repo.active_job_id(tx)
    items = []
    for row in rows:
        progress = row["progress"] or {}
        items.append(
            DiscoveryRunSummary(
                job_id=row["job_id"],
                status=row["status"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                request=_request(row),
                queries_total=int(progress.get("queries_total", 0)),
                pages_read=int(progress.get("pages_read", 0)),
                candidates_found=int(progress.get("candidates_found", 0)),
                candidates_new=_counts(row["run_counts"]).candidates_new,
                error=row["error"],
            )
        )
    return DiscoveryRunList(items=items, running_job_id=running)
