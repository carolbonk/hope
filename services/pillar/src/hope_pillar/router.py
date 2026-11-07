"""Pillar Router: schema validation and producer policy at the single choke point (7.1)."""

from __future__ import annotations

from collections.abc import Mapping

from hope_core.envelope import CLAIM_CHECK_BYTES, PillarEnvelope
from hope_core.hashing import canonical_json
from hope_core.pillar import OutboundPackage, PillarPort
from hope_core.schemas.export import CONTRACTS, VERSION
from hope_core.topics import Topic
from pydantic import BaseModel, ValidationError

from hope_pillar.contracts import (
    PACKAGING_AGENT,
    DeadLetter,
    IngestRequest,
    ProfileChangeProposal,
)
from hope_pillar.dlq import DeadLetterSink

SCHEMAS: Mapping[str, type[BaseModel]] = {
    **CONTRACTS,
    "outbound-package": OutboundPackage,
    "ingest-request": IngestRequest,
    "profile-change-proposal": ProfileChangeProposal,
}
"""schema_ref subject -> contract model. Every subject is at version hope_core VERSION."""

ALLOWED_PRODUCERS: Mapping[Topic, frozenset[str]] = {
    Topic.OUTBOUND_PACKAGES: frozenset({PACKAGING_AGENT}),
}
"""Topics restricted to specific Producer.agent_id values; other topics are open."""


class RouteRejected(ValueError):
    pass


class PillarRouter:
    def __init__(
        self,
        pillar: PillarPort,
        dead_letters: DeadLetterSink,
        *,
        schemas: Mapping[str, type[BaseModel]] = SCHEMAS,
        allowed_producers: Mapping[Topic, frozenset[str]] = ALLOWED_PRODUCERS,
    ) -> None:
        self.pillar = pillar
        self.dead_letters = dead_letters
        self.schemas = schemas
        self.allowed_producers = allowed_producers

    def violation(self, envelope: PillarEnvelope) -> str | None:
        allowed = self.allowed_producers.get(envelope.topic)
        if allowed is not None and envelope.producer.agent_id not in allowed:
            return f"agent {envelope.producer.agent_id!r} may not produce to {envelope.topic}"
        subject, _, version = envelope.schema_ref.partition("/")
        model = self.schemas.get(subject)
        if model is None:
            return f"unknown schema_ref {envelope.schema_ref!r}"
        if version != VERSION:
            return f"unsupported version {envelope.schema_ref!r} (registry has {VERSION})"
        if envelope.payload is None:
            return None
        if len(canonical_json(envelope.payload).encode()) > CLAIM_CHECK_BYTES:
            return "payload exceeds 256 KB; store it in S3 and send payload_ref"
        try:
            model.model_validate(envelope.payload)
        except ValidationError as exc:
            errors = exc.errors(include_input=False, include_url=False)
            where = ", ".join(".".join(map(str, e["loc"])) or "<root>" for e in errors[:5])
            return f"payload does not match {envelope.schema_ref} ({len(errors)} errors at {where})"
        return None

    def route(self, envelope: PillarEnvelope) -> None:
        """Publish a conforming envelope, or dead-letter it and raise RouteRejected."""
        reason = self.violation(envelope)
        if reason is not None:
            self.dead_letters.send(
                DeadLetter(
                    source_topic=envelope.topic,
                    key=envelope.subject_id,
                    consumer="router",
                    attempts=1,
                    error_type="RouteRejected",
                    error=reason,
                    envelope=envelope,
                )
            )
            raise RouteRejected(reason)
        self.pillar.publish(envelope)
