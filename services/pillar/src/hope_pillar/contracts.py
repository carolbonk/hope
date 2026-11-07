"""Pillar models other services consume. Candidates for promotion to hope_core.schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from hope_core.envelope import PillarEnvelope
from hope_core.schemas.common import Contract
from hope_core.topics import Topic
from pydantic import Field, HttpUrl, model_validator

PACKAGING_AGENT = "A10"
"""Producer.agent_id of the Packaging & Submission agent (blueprint 2.2 A10)."""


class IngestSource(Contract):
    kind: Literal["url", "file", "structured"]
    url: HttpUrl | None = None
    artifact_id: UUID | None = None
    opportunity: dict[str, Any] | None = Field(None, description="partial GrantOpportunity")
    source_system: str | None = None
    source_id: str | None = None

    @model_validator(mode="after")
    def _kind_has_content(self) -> IngestSource:
        required = {"url": self.url, "file": self.artifact_id, "structured": self.opportunity}
        if required[self.kind] is None:
            field = {"url": "url", "file": "artifact_id", "structured": "opportunity"}[self.kind]
            raise ValueError(f"kind={self.kind} requires {field}")
        return self

    @property
    def partition_key(self) -> str | None:
        if self.source_system and self.source_id:
            return f"{self.source_system}:{self.source_id}"
        return None


class IngestRequest(IngestSource):
    """Payload of opportunity.raw_ingested produced by POST /v1/ingest/opportunities."""

    ingest_id: UUID
    tenant_id: UUID
    submitted_by: str
    received_at: datetime


class ProfileChangeProposal(Contract):
    """Payload of profile.change_proposed produced by PATCH /v1/agencies/{id}/profile."""

    proposal_id: UUID
    tenant_id: UUID
    agency_id: UUID
    base_version: int = Field(ge=1)
    changes: dict[str, Any] = Field(min_length=1, description="dotted path -> new value")
    protected_paths: list[str] = Field(description="changed paths that need HITL-0")
    proposed_by: str
    reason: str | None = None


class DeadLetter(Contract):
    """Message on gop.dlq.<topic>: the original event plus why and how often it failed."""

    source_topic: Topic
    key: str
    consumer: str = Field(description="consumer group (or 'router') that gave up")
    attempts: int = Field(ge=1)
    error_type: str
    error: str
    failed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    envelope: PillarEnvelope | None = None
    raw: str | None = Field(None, description="original bytes when they were not an envelope")

    @property
    def dlq_topic(self) -> str:
        return self.source_topic.dlq
