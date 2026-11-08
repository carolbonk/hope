"""Profile REST routes (blueprint 7.4). Mount with `app.include_router(router, prefix="/v1")` and
override `get_repository` and `get_principal`; importing this module has no side effects."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from hope_core.auth import Principal as SessionPrincipal
from hope_core.auth import ProblemException
from hope_core.auth import get_principal as session_principal
from hope_core.db import connect
from hope_core.model_gateway import MockProvider, ModelGateway, default_gateway
from hope_core.pillar import InMemoryPillar
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.hitl import Gate, HitlDecision
from hope_core.settings import get_settings
from pydantic import BaseModel, ValidationError

from hope_profile import ntee
from hope_profile.contracts import CompletenessReport, FieldChange, ProfileChangeProposal
from hope_profile.ntee_mock import ntee_responder
from hope_profile.onboarding import (
    FieldError,
    ProfileForm,
    ProfilePatch,
    ProfileView,
    field_errors,
    form_completeness,
    form_json,
    form_to_profile,
    onboarding_complete,
    profile_error_fields,
    profile_to_form,
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


# --- H1 hackathon routes: one tenant, one agency, direct saves (no HITL-0) --------------------

_PILLAR = InMemoryPillar()
_SUGGEST_LIMIT = ntee.RateLimiter()
Session = Annotated[SessionPrincipal, Depends(session_principal)]


class ProfileProblem(ProblemException):
    def __init__(self, status_code: int, code: str, title: str, **extra: Any) -> None:
        errors = extra.pop("errors", None)
        super().__init__(status_code, code, title, errors)
        self.extra = extra

    def body(self) -> dict[str, Any]:
        return {**super().body(), **self.extra}


def get_profile_repository() -> Iterator[ProfileRepository]:
    with connect() as conn:
        yield ProfileRepository(conn, _PILLAR)


def get_gateway() -> ModelGateway:
    gateway = default_gateway()
    for provider in gateway.providers:
        if isinstance(provider, MockProvider) and "NteeSuggestionOut" not in provider.responders:
            provider.register(ntee.NteeSuggestionOut, ntee_responder)
    return gateway


def get_rate_limiter() -> ntee.RateLimiter:
    return _SUGGEST_LIMIT


HackRepo = Annotated[ProfileRepository, Depends(get_profile_repository)]


def _view(saved: ProfileVersion) -> ProfileView:
    form = profile_to_form(saved.profile)
    return ProfileView(
        version=saved.version,
        updated_at=saved.valid_from,
        updated_by=saved.recorded_by,
        onboarding_complete=onboarding_complete(saved.profile),
        form=form,
        ntee_labels={c: ntee.label(c) or c for c in form.ntee_codes},
        completeness=form_completeness(form),
    )


def _view_response(saved: ProfileVersion, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        _view(saved).model_dump(mode="json", warnings=False),
        status_code=status_code,
        headers={"ETag": _etag(saved.version)},
    )


def _current(repo: ProfileRepository, tenant_id: UUID) -> ProfileVersion | None:
    try:
        return repo.current(tenant_id, get_settings().agency_id)
    except ProfileNotFoundError:
        return None


def _invalid(errors: list[FieldError]) -> ProfileProblem:
    return ProfileProblem(
        422, "validation_error", "Validation failed", errors=[e.model_dump() for e in errors]
    )


def _parse_version(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    try:
        return int(if_match.removeprefix("W/").strip().strip('"'))
    except ValueError:
        raise ProfileProblem(
            422,
            "validation_error",
            "Validation failed",
            errors=[{"field": "If-Match", "code": "invalid_format", "message": "Bad If-Match."}],
        ) from None


def _save(
    repo: ProfileRepository,
    principal: SessionPrincipal,
    current: ProfileVersion | None,
    form: ProfileForm,
) -> ProfileVersion:
    settings = get_settings()
    data = form_to_profile(form, current.profile if current else None, settings)
    try:
        return repo.save_direct(
            principal.tenant_id,
            settings.agency_id,
            data,
            principal.email,
            current.version if current else 0,
        )
    except ProfileValidationError as exc:
        raise _invalid(profile_error_fields(exc.errors)) from exc
    except VersionConflictError as exc:
        raise _conflict(repo, principal.tenant_id) from exc


def _conflict(repo: ProfileRepository, tenant_id: UUID) -> ProfileProblem:
    latest = _current(repo, tenant_id)
    return ProfileProblem(
        409, "version_conflict", "Profile changed", current_version=latest.version if latest else 0
    )


def _checked_base(
    repo: ProfileRepository, principal: SessionPrincipal, if_match: str | None
) -> ProfileVersion | None:
    current = _current(repo, principal.tenant_id)
    expected = _parse_version(if_match)
    if current is None:
        if expected not in (None, 0):
            raise _conflict(repo, principal.tenant_id)
        return None
    if expected is None:
        raise ProfileProblem(428, "if_match_required", "If-Match required")
    if expected != current.version:
        raise _conflict(repo, principal.tenant_id)
    return current


_VIEW_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {"model": ProfileView, "description": "The profile form view; `ETag` is its version"}
}


@router.get("/profile", responses=_VIEW_RESPONSES, response_class=JSONResponse)
def get_hackathon_profile(principal: Session, repo: HackRepo) -> JSONResponse:
    current = _current(repo, principal.tenant_id)
    if current is None:
        raise ProfileProblem(404, "profile_not_found", "No profile yet")
    return _view_response(current)


@router.put("/profile", responses=_VIEW_RESPONSES, response_class=JSONResponse)
def put_hackathon_profile(
    body: Annotated[dict[str, Any], Body(description="A full `ProfileForm`")],
    principal: Session,
    repo: HackRepo,
    if_match: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Create (201) or replace (200) the profile from SC11's form. No HITL-0 in the hackathon."""
    try:
        form = ProfileForm.model_validate(body)
    except ValidationError as exc:
        raise _invalid(field_errors(exc)) from exc
    current = _checked_base(repo, principal, if_match)
    saved = _save(repo, principal, current, form)
    return _view_response(saved, 201 if current is None else 200)


@router.patch("/profile", responses=_VIEW_RESPONSES, response_class=JSONResponse)
def patch_hackathon_profile(
    body: Annotated[dict[str, Any], Body(description="Whole `ProfileForm` sections")],
    principal: Session,
    repo: HackRepo,
    if_match: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Replace the given top-level sections (used by the web sync adapter)."""
    try:
        patch = ProfilePatch.model_validate(body)
    except ValidationError as exc:
        raise _invalid(field_errors(exc)) from exc
    sections = patch.model_dump(exclude_none=True, mode="json", warnings=False)
    if not sections:
        raise _invalid(
            [FieldError(field="body", code="required", message="Send at least one section.")]
        )
    current = _current(repo, principal.tenant_id)
    if current is None:
        raise ProfileProblem(404, "profile_not_found", "No profile yet")
    current = _checked_base(repo, principal, if_match)
    assert current is not None
    merged = {**form_json(profile_to_form(current.profile)), **sections}
    try:
        form = ProfileForm.model_validate(merged)
    except ValidationError as exc:
        raise _invalid(field_errors(exc)) from exc
    return _view_response(_save(repo, principal, current, form))


@router.get("/profile/ntee-codes")
def search_ntee_codes(
    _principal: Session,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ntee.NteeSearchResult:
    return ntee.NteeSearchResult(items=ntee.search(q, limit))


@router.post("/profile/ntee-suggestions")
def suggest_ntee_codes(
    body: ntee.NteeSuggestionRequest,
    principal: Session,
    gateway: Annotated[ModelGateway, Depends(get_gateway)],
    limiter: Annotated[ntee.RateLimiter, Depends(get_rate_limiter)],
) -> ntee.NteeSuggestionResponse:
    """The one model call in H1. It never writes the profile; the user picks codes in SC11."""
    if not limiter.allow(str(principal.user_id)):
        raise ProfileProblem(429, "rate_limited", "Too many requests")
    return ntee.suggest_ntee(gateway, body)
