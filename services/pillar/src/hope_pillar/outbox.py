"""Transactional outbox: write in the caller's transaction, relay to Kafka (blueprint 7.3)."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

import psycopg
from hope_core.db import connect
from hope_core.envelope import PillarEnvelope
from psycopg.types.json import Jsonb

from hope_pillar.kafka import KafkaConfig

log = logging.getLogger(__name__)

Cursor = psycopg.Cursor[dict[str, object]]


def write_outbox(cur: Cursor, envelope: PillarEnvelope) -> None:
    """Idempotent on event_id: republishing the same event is a no-op."""
    cur.execute(
        "INSERT INTO outbox (event_id, tenant_id, topic, partition_key, envelope)"
        " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (event_id) DO NOTHING",
        (
            envelope.event_id,
            envelope.tenant_id,
            envelope.topic.value,
            envelope.subject_id,
            Jsonb(envelope.model_dump(mode="json")),
        ),
    )


class OutboxRelay:
    """Publishes unpublished outbox rows to Kafka (topic = envelope.topic, key = subject_id).

    Runs as `hope_system` (cross-tenant). Rows are marked published only after broker acks,
    so delivery is at-least-once; consumers dedupe via processed_events. Run one relay per
    deployment to keep per-key ordering.
    """

    def __init__(
        self,
        kafka: KafkaConfig,
        system_url: str,
        *,
        batch_size: int = 100,
        min_outbox_id: int = 0,
    ) -> None:
        self.kafka = kafka
        self.system_url = system_url
        self.batch_size = batch_size
        self.min_outbox_id = min_outbox_id

    def run_once(self) -> int:
        with connect(self.system_url) as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute(
                "SELECT outbox_id, topic, partition_key, envelope FROM outbox"
                " WHERE published_at IS NULL AND outbox_id > %s"
                " ORDER BY outbox_id LIMIT %s FOR UPDATE SKIP LOCKED",
                (self.min_outbox_id, self.batch_size),
            )
            rows: list[dict[str, Any]] = cur.fetchall()
            if not rows:
                return 0
            self.kafka.ensure_topics({str(r["topic"]) for r in rows})
            self.kafka.produce(
                (str(r["topic"]), str(r["partition_key"]), json.dumps(r["envelope"]).encode())
                for r in rows
            )
            cur.execute(
                "UPDATE outbox SET published_at = now() WHERE outbox_id = ANY(%s)",
                ([r["outbox_id"] for r in rows],),
            )
            return len(rows)

    def run_forever(self, stop: threading.Event, interval: float = 0.2) -> None:
        while not stop.is_set():
            try:
                if self.run_once() == self.batch_size:
                    continue
            except Exception:
                log.exception("outbox relay batch failed; retrying")
            stop.wait(interval)
