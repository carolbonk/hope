"""Profile REST routes. Mount with `app.include_router(router, prefix="/v1")`.

- Hackathon (H1): `/profile`, `/profile/ntee-codes`, `/profile/ntee-suggestions` on the configured
  tenant and agency; every save commits directly (no HITL-0).
- Enterprise (blueprint 7.4): `/agencies/{id}/profile...` with HITL-0. Override `get_repository`
  and `get_principal` to use them; unconfigured they fail closed.

Importing this module has no side effects."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from hope_core.auth import Principal as SessionPrincipal
from hope_core.auth import ProblemException
from hope_core.auth import get_principal as session_principal
from hope_core.db import connect
from hope_core.envelope import PillarEnvelope
from hope_core.model_gateway import MockProvider, ModelGateway, default_gateway
from hope_core.pillar import InMemoryPillar, PillarPort
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.hitl import Gate, HitlDecision
from hope_core.settings import get_settings
from pydantic import BaseModel, ValidationError
from starlette.responses import Response as StarletteResponse

from hope_profile import ntee
from hope_profile.contracts import CompletenessReport, FieldChange, ProfileChangeProposal
from hope_profile.ntee import (
    NteeSearchResponse,
    NteeSuggestionOut,
    NteeSuggestionRequest,
    NteeSuggestionResponse,
    RateLimiter,
)
from hope_profile.ntee_mock import ntee_responder
from hope_profile.onboarding import (
    FieldError,
    ProfileForm,
    ProfilePatchBody,
    ProfileView,
    form_completeness,
    form_to_profile,
    merge_sections,
    onboarding_complete,
    profile_error,
    profile_to_form,
    validation_errors,
)
from hope_profile.repository import (
    ApproverRoleError,
    ChangeResult,
    ProfileNotFoundError,
    ProfileRepository,
    ProfileValidationError,
    ProfileVersion,
    ProposalStateError,
    SeparationOfDutiesError,
    VersionConflictError,
)

router = APIRouter(tags=["profile"])


@dataclass(frozen=True)
class Principal:
    tenant_id: UUID
    user_id: str
    roles: tuple[str, ...] = ()


def get_principal(session: Annotated[SessionPrincipal, Depends(session_principal)]) -> Principal:
    return Principal(session.tenant_id, str(session.user_id))


def get_repository() -> ProfileRepository:
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "profile repository not configured")


Repo = Annotated[ProfileRepository, Depends(get_repository)]
Caller = Annotated[Principal, Depends(get_principal)]

_STATUS: dict[type[Exception], int] = {
    ProfileNotFoundError: status.HTTP_404_NOT_FOUND,
    VersionConflictError: status.HTTP_409_CONFLICT,
    ProposalStateError: status.HTTP_409_CONFLICT,
    SeparationOfDutiesError: status.HTTP_403_FORBIDDEN,
    ApproverRoleError: status.HTTP_403_FORBIDDEN,
    ProfileValidationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


@contextmanager
def _errors() -> Iterator[None]:
    try:
        yield
    except tuple(_STATUS) as exc:
        detail: Any = exc.errors if isinstance(exc, ProfileValidationError) else str(exc)
        raise HTTPException(_STATUS[type(exc)], detail) from exc


def _etag(version: int) -> str:
    return f'"{version}"'


def _if_match(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.removeprefix("W/").strip('"'))
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "If-Match must be a profile version"
        ) from exc


class DecisionBody(BaseModel):
    artifact_hash: str
    comment: str | None = None


@router.post("/agencies", status_code=status.HTTP_201_CREATED)
def create_agency(profile: AgencyProfile, repo: Repo, caller: Caller) -> ProfileVersion:
    with _errors():
        return repo.create_agency(caller.tenant_id, profile, caller.user_id)


@router.get("/agencies/{agency_id}/profile")
def get_profile(
    agency_id: UUID, response: Response, repo: Repo, caller: Caller, as_of: datetime | None = None
) -> ProfileVersion:
    with _errors():
        found = repo.as_of(caller.tenant_id, agency_id, as_of)
    response.headers["ETag"] = _etag(found.version)
    return found


@router.get("/agencies/{agency_id}/profile/history")
def get_history(agency_id: UUID, repo: Repo, caller: Caller) -> list[ProfileVersion]:
    with _errors():
        return repo.history(caller.tenant_id, agency_id)


@router.get("/agencies/{agency_id}/profile/diff")
def get_diff(
    agency_id: UUID, from_version: int, to_version: int, repo: Repo, caller: Caller
) -> list[FieldChange]:
    with _errors():
        return repo.diff(caller.tenant_id, agency_id, from_version, to_version)


@router.get("/agencies/{agency_id}/profile/completeness")
def get_completeness(agency_id: UUID, repo: Repo, caller: Caller) -> CompletenessReport:
    with _errors():
        return repo.completeness(caller.tenant_id, agency_id)


@router.patch("/agencies/{agency_id}/profile")
def patch_profile(
    agency_id: UUID,
    patch: Annotated[dict[str, Any], Body(description="RFC 7396 JSON merge patch")],
    response: Response,
    repo: Repo,
    caller: Caller,
    if_match: Annotated[str | None, Header()] = None,
) -> ChangeResult:
    """Unprotected changes commit (200). Protected ones return 202 pending_approval (HITL-0)."""
    with _errors():
        result = repo.propose(
            caller.tenant_id, agency_id, patch, caller.user_id, expected_version=_if_match(if_match)
        )
    if result.status == "pending_approval":
        response.status_code = status.HTTP_202_ACCEPTED
    response.headers["ETag"] = _etag(result.version)
    return result


@router.get("/agencies/{agency_id}/profile/proposals")
def list_proposals(
    agency_id: UUID,
    repo: Repo,
    caller: Caller,
    status: Literal["pending", "approved", "rejected"] | None = "pending",
) -> list[ProfileChangeProposal]:
    with _errors():
        return repo.proposals(caller.tenant_id, agency_id, status)


def _decide(
    repo: ProfileRepository,
    caller: Principal,
    agency_id: UUID,
    proposal_id: UUID,
    body: DecisionBody,
    decision: Literal["approve", "reject"],
) -> ChangeResult:
    with _errors():
        if not any(
            p.proposal_id == proposal_id for p in repo.proposals(caller.tenant_id, agency_id, None)
        ):
            raise ProfileNotFoundError(f"no proposal {proposal_id} for agency {agency_id}")
        return repo.decide(
            caller.tenant_id,
            HitlDecision(
                request_id=proposal_id,
                gate=Gate.PROFILE_COMMIT,
                decision=decision,
                artifact_hash=body.artifact_hash,
                decided_by=caller.user_id,
                decided_at=datetime.now(UTC),
                comment=body.comment,
            ),
            caller.roles,
        )


@router.post("/agencies/{agency_id}/profile/proposals/{proposal_id}/approve")
def approve_proposal(
    agency_id: UUID, proposal_id: UUID, body: DecisionBody, repo: Repo, caller: Caller
) -> ChangeResult:
    return _decide(repo, caller, agency_id, proposal_id, body, "approve")


@router.post("/agencies/{agency_id}/profile/proposals/{proposal_id}/reject")
def reject_proposal(
    agency_id: UUID, proposal_id: UUID, body: DecisionBody, repo: Repo, caller: Caller
) -> ChangeResult:
    return _decide(repo, caller, agency_id, proposal_id, body, "reject")


# --- Hackathon routes (H1) -------------------------------------------------------------------

log = logging.getLogger(__name__)


class Problem(ProblemException):
    """problem+json with extra top-level members (e.g. `current_version`)."""

    def __init__(
        self,
        status_code: int,
        code: str,
        title: str,
        errors: list[dict[str, str]] | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(status_code, code, title, errors)
        self.extra = extra

    def body(self) -> dict[str, Any]:
        return {**super().body(), **self.extra}


def _problem_json(exc: ProblemException) -> JSONResponse:
    return JSONResponse(
        exc.body(), status_code=exc.status_code, media_type="application/problem+json"
    )


def _invalid(errors: list[FieldError]) -> Problem:
    return Problem(422, "validation_error", "Validation failed", [e.model_dump() for e in errors])


class ProblemRoute(APIRoute):
    """Renders `ProblemException` and request validation as problem+json with form-path
    `errors[]`, whatever handlers the host app installs."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, StarletteResponse]]:
        handler = super().get_route_handler()

        async def route(request: Request) -> StarletteResponse:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return _problem_json(_invalid(validation_errors(list(exc.errors()))))
            except ProblemException as exc:
                return _problem_json(exc)

        return route


class LogPillar(InMemoryPillar):
    """Hackathon event sink: nothing consumes `profile.updated`, so it is logged, not kept."""

    def publish(self, envelope: PillarEnvelope) -> None:
        log.info("event %s %s", envelope.event_type, envelope.subject_id)


_log_pillar = LogPillar()


def get_pillar() -> PillarPort:
    return _log_pillar


def get_profile_repository(
    pillar: Annotated[PillarPort, Depends(get_pillar)],
) -> Iterator[ProfileRepository]:
    with connect() as conn:
        yield ProfileRepository(conn, pillar)


def get_gateway() -> ModelGateway:
    """`default_gateway()`; a `MockProvider` without an NTEE responder gets `ntee_responder`."""
    gateway = default_gateway()
    for provider in gateway.providers:
        if isinstance(provider, MockProvider) and "NteeSuggestionOut" not in provider.responders:
            provider.register(NteeSuggestionOut, ntee_responder)
    return gateway


suggestion_limiter = RateLimiter()

HackRepo = Annotated[ProfileRepository, Depends(get_profile_repository)]
Session = Annotated[SessionPrincipal, Depends(session_principal)]
Gateway = Annotated[ModelGateway, Depends(get_gateway)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]

hackathon = APIRouter(route_class=ProblemRoute, tags=["profile"])

_PROBLEM: dict[str, Any] = {"content": {"application/problem+json": {}}}


def _expected(if_match: str | None, current: int) -> int:
    try:
        return int(if_match.removeprefix("W/").strip().strip('"')) if if_match else -1
    except ValueError:
        return -1


def _conflict(current: int | None) -> Problem:
    return Problem(409, "version_conflict", "Profile changed", current_version=current)


def _view(saved: ProfileVersion, extras: dict[str, Any] | None = None) -> ProfileView:
    form = profile_to_form(saved.profile, extras)
    return ProfileView(
        version=saved.version,
        updated_at=saved.recorded_at,
        updated_by=saved.recorded_by,
        onboarding_complete=onboarding_complete(form),
        form=form,
        ntee_labels={code: ntee.label(code) for code in form.ntee_codes},
        completeness=form_completeness(form),
    )


def _save(
    repo: ProfileRepository,
    who: SessionPrincipal,
    form: ProfileForm,
    base: ProfileVersion | None,
) -> ProfileVersion:
    settings = get_settings()
    data = form_to_profile(
        form,
        base.profile if base else None,
        tenant_id=settings.tenant_id,
        agency_id=settings.agency_id,
        now=datetime.now(UTC),
    )
    try:
        return repo.save_direct(
            settings.tenant_id,
            settings.agency_id,
            data,
            who.email,
            base.version if base else None,
        )
    except VersionConflictError as exc:
        latest = repo.latest(settings.tenant_id, settings.agency_id)
        raise _conflict(latest.version if latest else None) from exc
    except ProfileValidationError as exc:
        raise _invalid([profile_error(m) for m in exc.errors]) from exc


def _respond(response: Response, saved: ProfileVersion) -> ProfileView:
    response.headers["ETag"] = _etag(saved.version)
    return _view(saved)


@hackathon.get(
    "/profile",
    responses={401: _PROBLEM, 404: _PROBLEM},
    summary="Current profile (form shape) with version and completeness",
)
def get_hackathon_profile(response: Response, repo: HackRepo, who: Session) -> ProfileView:
    settings = get_settings()
    found = repo.latest(settings.tenant_id, settings.agency_id)
    if found is None:
        raise Problem(404, "profile_not_found", "No profile yet")
    response.headers["ETag"] = _etag(found.version)
    return _view(found, repo.extras(settings.tenant_id, settings.agency_id))


@hackathon.put(
    "/profile",
    responses={
        201: {"model": ProfileView, "description": "Created"},
        401: _PROBLEM,
        409: _PROBLEM,
        422: _PROBLEM,
        428: _PROBLEM,
    },
    summary="Create or replace the whole profile (onboarding finish)",
)
def put_hackathon_profile(
    form: ProfileForm, response: Response, repo: HackRepo, who: Session, if_match: IfMatch = None
) -> ProfileView:
    settings = get_settings()
    base = repo.latest(settings.tenant_id, settings.agency_id)
    if base is not None:
        if if_match is None:
            raise Problem(428, "if_match_required", "If-Match required")
        if _expected(if_match, base.version) != base.version:
            raise _conflict(base.version)
    elif if_match is not None and if_match.strip() not in ("*", '"0"', "0"):
        raise _conflict(None)
    saved = _save(repo, who, form, base)
    if base is None:
        response.status_code = status.HTTP_201_CREATED
    return _respond(response, saved)


@hackathon.patch(
    "/profile",
    responses={401: _PROBLEM, 404: _PROBLEM, 409: _PROBLEM, 422: _PROBLEM, 428: _PROBLEM},
    summary="Replace whole top-level sections (If-Match required)",
)
def patch_hackathon_profile(
    body: ProfilePatchBody,
    response: Response,
    repo: HackRepo,
    who: Session,
    if_match: IfMatch = None,
) -> ProfileView:
    if not body.model_fields_set - {k for k, v in body if v is None}:
        raise _invalid(
            [FieldError(field="body", code="required", message="Send at least one section.")]
        )
    settings = get_settings()
    base = repo.latest(settings.tenant_id, settings.agency_id)
    if base is None:
        raise Problem(404, "profile_not_found", "No profile yet")
    if if_match is None:
        raise Problem(428, "if_match_required", "If-Match required")
    if _expected(if_match, base.version) != base.version:
        raise _conflict(base.version)
    current = profile_to_form(base.profile, repo.extras(settings.tenant_id, settings.agency_id))
    try:
        form = merge_sections(current, body)
    except ValidationError as exc:
        raise _invalid(validation_errors(exc)) from exc
    return _respond(response, _save(repo, who, form, base))


@hackathon.get(
    "/profile/ntee-codes",
    responses={401: _PROBLEM, 422: _PROBLEM},
    summary="Search NTEE codes; an empty q returns the 26 major groups",
)
def search_ntee_codes(
    who: Session,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=ntee.SEARCH_LIMIT_MAX)] = 20,
) -> NteeSearchResponse:
    return NteeSearchResponse(items=ntee.search(q, limit))


@hackathon.post(
    "/profile/ntee-suggestions",
    responses={401: _PROBLEM, 422: _PROBLEM, 429: _PROBLEM},
    summary="Suggest NTEE codes from the mission and programs (one model call)",
)
def suggest_ntee_codes(
    body: NteeSuggestionRequest, who: Session, gateway: Gateway
) -> NteeSuggestionResponse:
    if not suggestion_limiter.allow(str(who.user_id)):
        raise Problem(429, "rate_limited", "Too many requests")
    return ntee.suggest_ntee(gateway, body)


router.include_router(hackathon)
