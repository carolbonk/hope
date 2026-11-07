"""Projects pillar events into the read tables behind GET /v1/workflows (blueprint 7.3)."""

from __future__ import annotations

from hope_core.db import connect
from hope_core.envelope import PillarEnvelope
from hope_core.schemas.hitl import HitlDecision, HitlRequest
from hope_core.topics import EventType
from psycopg.types.json import Jsonb

from hope_pillar.outbox import Cursor

GROUP = "pillar-projector"


def project(cur: Cursor, envelope: PillarEnvelope) -> None:
    workflow_id = envelope.trace.correlation_id
    if envelope.tenant_id is not None and workflow_id:
        cur.execute(
            "INSERT INTO pillar_workflow_timeline"
            " (event_id, tenant_id, workflow_id, event_type, occurred_at, summary)"
            " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (
                envelope.event_id,
                envelope.tenant_id,
                workflow_id,
                envelope.event_type.value,
                envelope.occurred_at,
                Jsonb({"schema_ref": envelope.schema_ref, "producer": envelope.producer.service}),
            ),
        )
    if envelope.payload is None:
        return
    if envelope.event_type == EventType.HITL_REQUESTED:
        request = HitlRequest.model_validate(envelope.payload)
        cur.execute(
            "UPDATE pillar_gate_requests SET status = 'superseded'"
            " WHERE tenant_id = %s AND workflow_id = %s AND gate = %s AND status = 'open'"
            " AND request_id <> %s",
            (request.tenant_id, request.workflow_id, request.gate.value, request.request_id),
        )
        cur.execute(
            "INSERT INTO pillar_gate_requests (request_id, tenant_id, workflow_id, subject_id,"
            " gate, artifact_hash, approver_roles, due_at, summary, payload_ref)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (
                request.request_id,
                request.tenant_id,
                request.workflow_id,
                envelope.subject_id,
                request.gate.value,
                request.artifact_hash,
                request.approver_roles,
                request.due_at,
                request.summary,
                request.payload_ref,
            ),
        )
    elif envelope.event_type == EventType.HITL_DECIDED:
        decision = HitlDecision.model_validate(envelope.payload)
        cur.execute(
            "UPDATE pillar_gate_requests SET status = 'decided', decision = %s,"
            " decided_by = %s, decided_at = %s WHERE request_id = %s AND status = 'open'",
            (decision.decision, decision.decided_by, decision.decided_at, decision.request_id),
        )


class Projector:
    """Cross-tenant worker (hope_system); run it with `pillar.consume(EVENT_TYPES, GROUP, ...)`."""

    EVENT_TYPES: list[str] = [t.value for t in EventType]

    def __init__(self, system_url: str) -> None:
        self.system_url = system_url

    def __call__(self, envelope: PillarEnvelope) -> None:
        with connect(self.system_url) as conn, conn.transaction(), conn.cursor() as cur:
            project(cur, envelope)
