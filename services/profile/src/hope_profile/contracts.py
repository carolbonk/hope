"""Profile event payloads other services consume. Candidates for promotion to hope_core.schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from hope_core.schemas.common import Contract, Provenance
from pydantic import Field

SCHEMA_VERSION = "1.0.0"

ProposalStatus = Literal["pending", "approved", "rejected"]
StaleReason = Literal[
    "sam_expiring", "sam_expired", "nicra_expiring", "nicra_expired", "audit_outdated"
]


class FieldChange(Contract):
    path: str = Field(description="dotted path, e.g. financials.indirect_rate.rate_bps")
    old: Any = None
    new: Any = None
    protected: bool


class ProfileUpdated(Contract):
    """Payload of `profile.updated`."""

    agency_id: UUID
    version: int
    previous_version: int | None
    changes: list[FieldChange]
    protected_changed: bool
    committed_by: str
    proposal_id: UUID | None = None
    approved_by: str | None = None


class ProfileChangeProposal(Contract):
    """Payload of `profile.change_proposed`; the HITL-0 artifact."""

    proposal_id: UUID
    tenant_id: UUID
    agency_id: UUID
    base_version: int
    patch: dict[str, Any] = Field(description="RFC 7396 JSON merge patch")
    changes: list[FieldChange]
    provenance: Provenance | None = None
    content_hash: str
    status: ProposalStatus = "pending"
    proposed_by: str
    proposed_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_comment: str | None = None
    committed_version: int | None = None


class StaleFieldAlert(Contract):
    """Payload of `profile.stale_field`."""

    agency_id: UUID
    field: str
    reason: StaleReason
    threshold: Literal["60d", "30d", "7d", "expired", "18m"]
    ref_date: date = Field(description="expiry date, or the audited fiscal-year end")
    days_remaining: int | None = None


class NarrativeHit(Contract):
    """One semantic-memory search result, used by matching and drafting."""

    chunk_id: UUID
    agency_id: UUID
    asset_id: str
    asset_kind: str
    chunk_index: int
    content: str
    score: float = Field(description="cosine similarity, higher is closer")
    approved_for_reuse: bool
    provenance: Provenance | None = None


class CompletenessReport(Contract):
    score: int = Field(ge=0, le=100)
    missing: list[str] = Field(description="dotted paths that are empty")
