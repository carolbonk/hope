"""Request/response bodies of the /v1 API (service-local, not shared contracts)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from hope_core.schemas.common import Contract
from hope_core.schemas.hitl import Decision, Gate
from pydantic import BaseModel, Field


class IngestAccepted(BaseModel):
    ingest_id: UUID
    replayed: bool = False


class ArtifactUploadRequest(Contract):
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\]+$")
    media_type: str = Field(min_length=3, max_length=127)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(gt=0)


class ArtifactUpload(BaseModel):
    artifact_id: UUID
    upload_url: str
    storage_uri: str
    expires_in: int


class ProfileView(BaseModel):
    agency_id: UUID
    version: int
    profile: dict[str, Any]
    valid_from: datetime
    recorded_at: datetime


class ProfilePatch(Contract):
    changes: dict[str, Any] = Field(min_length=1, description="dotted path -> new value")
    reason: str | None = Field(None, max_length=2000)


class ProposalAccepted(BaseModel):
    proposal_id: UUID
    status: Literal["pending_approval", "accepted"]
    protected_paths: list[str]


class MatrixItem(BaseModel):
    opportunity_id: UUID
    title: str
    state: str
    composite_score: float | None
    recommendation: str | None
    internal_deadline: datetime | None
    application_due: datetime | None
    workflow_id: str | None


class MatrixPage(BaseModel):
    items: list[MatrixItem]
    next_cursor: str | None


class OpportunityProvenance(BaseModel):
    source_system: str
    source_id: str
    version: int
    amendment_seq: int
    content_hash: str
    recorded_at: datetime


class OpportunityView(BaseModel):
    opportunity_id: UUID
    title: str
    application_due: datetime | None
    normalized: dict[str, Any]
    provenance: OpportunityProvenance


class GateView(BaseModel):
    request_id: UUID
    gate: Gate
    status: Literal["open", "decided", "superseded"]
    artifact_hash: str
    approver_roles: list[str]
    due_at: datetime | None
    summary: str
    decision: str | None
    decided_by: str | None
    requested_at: datetime
    decided_at: datetime | None


class TimelineEntry(BaseModel):
    event_id: UUID
    event_type: str
    occurred_at: datetime


class WorkflowView(BaseModel):
    workflow_id: str
    opportunity_id: UUID | None
    agency_id: UUID | None
    state: str | None
    updated_at: datetime | None
    gates: list[GateView]
    timeline: list[TimelineEntry]


class SignalBody(Contract):
    decision: Decision
    artifact_hash: str
    comment: str | None = Field(None, max_length=4000)


class DecisionAccepted(BaseModel):
    request_id: UUID
    event_id: UUID
    decision: Decision


class AuthorizeBody(Contract):
    manifest_hash: str
    channel: str = Field(min_length=1)
    comment: str | None = Field(None, max_length=4000)


class PackageAuthorized(DecisionAccepted):
    tracking_id: str


class LedgerView(BaseModel):
    ledger_id: str
    engine_version: str
    ledger: dict[str, Any]
    content_hash: str
    created_at: datetime


class FrameworkView(BaseModel):
    framework_id: UUID
    opportunity_id: UUID
    agency_id: UUID
    version: int
    status: str
    framework: dict[str, Any]
    content_hash: str
    ledgers: list[LedgerView]
