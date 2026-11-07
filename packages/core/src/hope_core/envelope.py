"""PillarEnvelope: the only message shape on the pillar (blueprint 5.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from hope_core.schemas.common import Contract
from hope_core.topics import EVENT_TOPIC, EventType, Topic

CLAIM_CHECK_BYTES = 256 * 1024

DataClassification = Literal["public", "internal", "confidential", "restricted"]


class Producer(Contract):
    service: str
    agent_id: str | None = None
    version: str = "0.1.0"
    model_ids: list[str] = []
    prompt_version: str | None = None


class Trace(Contract):
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    causation_id: str | None = None
    correlation_id: str | None = Field(None, description="workflow id")


class PillarEnvelope(Contract):
    event_id: UUID = Field(default_factory=uuid4, description="idempotency key")
    event_type: EventType
    schema_ref: str
    tenant_id: UUID | None = Field(None, description="None only for public, cross-tenant data")
    subject_id: str = Field(description="partition key, usually opportunity_id")
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    producer: Producer
    trace: Trace = Field(default_factory=Trace)
    data_classification: DataClassification = "internal"
    payload: dict[str, Any] | None = None
    payload_ref: str | None = Field(None, description="S3 URI when payload > 256 KB")

    @model_validator(mode="after")
    def _payload_xor_ref(self) -> PillarEnvelope:
        if (self.payload is None) == (self.payload_ref is None):
            raise ValueError("exactly one of payload or payload_ref must be set")
        if self.tenant_id is None and self.data_classification not in ("public", "internal"):
            raise ValueError("tenant_id is required for confidential or restricted data")
        return self

    @property
    def topic(self) -> Topic:
        return EVENT_TOPIC[self.event_type]

    def caused(self, **changes: Any) -> PillarEnvelope:
        """Build a follow-up event that keeps this event's trace lineage."""
        trace = Trace(
            trace_id=self.trace.trace_id,
            causation_id=str(self.event_id),
            correlation_id=self.trace.correlation_id,
        )
        base: dict[str, Any] = {
            "tenant_id": self.tenant_id,
            "subject_id": self.subject_id,
            "data_classification": self.data_classification,
            "trace": trace,
        }
        return PillarEnvelope(**(base | changes))
