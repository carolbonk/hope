"""Profile REST routes (blueprint 7.4). Mount with `app.include_router(router, prefix="/v1")` and
override `get_repository` and `get_principal`; importing this module has no side effects."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, Response, status
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.hitl import Gate, HitlDecision
from pydantic import BaseModel

from hope_profile.contracts import CompletenessReport, FieldChange, ProfileChangeProposal
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


def get_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    return principal


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
