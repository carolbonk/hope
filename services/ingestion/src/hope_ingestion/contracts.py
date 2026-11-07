"""Ingestion event payloads and checks that other services consume. Candidates for promotion
to hope_core.schemas (see the PR's "Requests for orchestrator")."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from hope_core.schemas.common import Contract, Evidence
from hope_core.schemas.grant_opportunity import GrantOpportunity, SourceSystem

SCHEMA_VERSION = "1.0.0"
EXPIRY_WARNING_DAYS = (60, 30, 7)


def schema_ref(name: str) -> str:
    return f"{name}/{SCHEMA_VERSION}"


class ArtifactSummary(Contract):
    artifact_id: str
    sha256: str
    media_type: str
    filename: str | None = None


class QuarantineNotice(Contract):
    sha256: str
    reason: str
    filename: str | None = None


class RawIngested(Contract):
    source_system: SourceSystem
    source_id: str
    revision: int = 0
    url: str | None = None
    artifacts: list[ArtifactSummary] = []
    quarantined: list[QuarantineNotice] = []


class Candidate(Contract):
    value: str
    evidence: list[Evidence] = []


BlockingReason = Literal["missing", "conflict", "corrupt", "unreadable"]


class BlockingIssue(Contract):
    field: str
    reason: BlockingReason
    candidates: list[Candidate] = []


class ParseIncomplete(Contract):
    """`opportunity.parse_incomplete`: a human fills or picks fields in NeedsParseReview."""

    opportunity: GrantOpportunity
    version: int
    blocking: list[BlockingIssue]
    questions_to_funder: list[str] = []


class FieldChange(Contract):
    path: str
    before: Any = None
    after: Any = None


class OpportunityAmended(Contract):
    opportunity_id: UUID
    from_version: int
    to_version: int
    amendment_seq: int
    changes: list[FieldChange]


class EntityRegistrationCheck(Contract):
    uei: str
    found: bool
    active: bool
    blocks_federal: bool
    legal_business_name: str | None = None
    registration_status: str | None = None
    registration_expiration_date: date | None = None
    days_until_expiry: int | None = None
    expiry_warning_days: int | None = None
    exclusion_flagged: bool = False
    checked_at: datetime | None = None
