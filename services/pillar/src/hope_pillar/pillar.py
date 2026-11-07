"""KafkaPostgresPillar: the production PillarPort (blueprint 7.3, 7.5)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from confluent_kafka import Message
from hope_core.db import connect, tenant_tx
from hope_core.envelope import PillarEnvelope, Producer
from hope_core.pillar import ConcurrencyError, OutboundPackage, RouteReceipt
from hope_core.schemas.hitl import Gate
from hope_core.settings import get_settings
from hope_core.topics import EVENT_TOPIC, EventType, Topic
from psycopg.types.json import Jsonb
from pydantic import ValidationError
from pydantic_core import to_jsonable_python

from hope_pillar.contracts import DeadLetter
from hope_pillar.dlq import (
    DEFAULT_RETRY,
    DeadLetterSink,
    Handler,
    KafkaDeadLetterSink,
    RetryPolicy,
    run_with_retry,
)
from hope_pillar.kafka import KafkaConfig
from hope_pillar.outbox import Cursor, write_outbox

SERVICE = "pillar"
OUTBOUND_SCHEMA = "outbound-package/1.0.0"

_bound: ContextVar[Cursor | None] = ContextVar("hope_pillar_bound_cursor", default=None)


class KafkaPostgresPillar:
    """Outbox-backed publish, Kafka consumer groups, versioned state in Postgres.

    `publish`/`put_state`/`route_outbound` join the caller's transaction when one is bound
    with `using(cur)` (or `transaction(tenant_id)`); otherwise each call commits on its own.
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        system_url: str | None = None,
        kafka: KafkaConfig | None = None,
        dead_letters: DeadLetterSink | None = None,
        idle_timeout: float | None = None,
        poll_timeout: float = 0.5,
    ) -> None:
        settings = get_settings()
        self.url = url or settings.database_url
        self.system_url = system_url or settings.database_system_url
        self.kafka = kafka or KafkaConfig(settings.kafka_bootstrap)
        self.dead_letters = dead_letters or KafkaDeadLetterSink(self.kafka)
        self.idle_timeout = idle_timeout
        self.poll_timeout = poll_timeout

    @contextmanager
    def using(self, cur: Cursor) -> Iterator[Cursor]:
        token = _bound.set(cur)
        try:
            yield cur
        finally:
            _bound.reset(token)

    @contextmanager
    def transaction(self, tenant_id: UUID | None) -> Iterator[Cursor]:
        with self._tx(tenant_id) as cur, self.using(cur):
            yield cur

    @contextmanager
    def _tx(self, tenant_id: UUID | None, *, system: bool = False) -> Iterator[Cursor]:
        bound = _bound.get()
        if bound is not None:
            with bound.connection.transaction():
                yield bound
            return
        with connect(self.system_url if system else self.url) as conn:
            if tenant_id is None:
                with conn.transaction(), conn.cursor() as cur:
                    yield cur
            else:
                with tenant_tx(conn, tenant_id) as cur:
                    yield cur

    def publish(self, envelope: PillarEnvelope) -> None:
        # Tenant-less (public) events can only be written by the RLS-exempt system role.
        with self._tx(envelope.tenant_id, system=envelope.tenant_id is None) as cur:
            write_outbox(cur, envelope)

    def subscribe(
        self, event_types: list[str], group: str, *, max_events: int | None = None
    ) -> Iterator[PillarEnvelope]:
        """Consumer group with idempotency via processed_events.

        An event is marked processed (and its offset committed) when the caller asks for
        the next one, so an exception in the caller's handler leads to redelivery.
        """
        wanted = {EventType(t) for t in event_types}
        topics = sorted({EVENT_TOPIC[t].value for t in wanted})
        consumer_name = self.kafka.group_id(group)
        delivered = 0
        with _autocommit(self.url) as conn:
            for consumer, msg in self.kafka.consume(
                topics, group, poll_timeout=self.poll_timeout, idle_timeout=self.idle_timeout
            ):
                envelope = self._decode(msg, group)
                if (
                    envelope is not None
                    and envelope.event_type in wanted
                    and not _is_processed(conn, consumer_name, envelope.event_id)
                ):
                    yield envelope
                    _mark_processed(conn, consumer_name, envelope.event_id)
                    delivered += 1
                consumer.commit(message=msg, asynchronous=False)
                if max_events is not None and delivered >= max_events:
                    return

    def consume(
        self,
        event_types: list[str],
        group: str,
        handler: Handler,
        *,
        policy: RetryPolicy = DEFAULT_RETRY,
        max_events: int | None = None,
    ) -> int:
        """Run `handler` per event with retry/backoff; exhausted events go to the DLQ."""
        handled = 0
        for envelope in self.subscribe(event_types, group, max_events=max_events):
            run_with_retry(handler, envelope, consumer=group, sink=self.dead_letters, policy=policy)
            handled += 1
        return handled

    def replay_dead_letters(self, topic: Topic, *, max_messages: int | None = None) -> int:
        """Re-deliver dead letters of `topic` to the consumer group that gave up on them."""
        replayed = 0
        for consumer, msg in self.kafka.consume(
            [topic.dlq],
            "hope-dlq-replay",
            poll_timeout=self.poll_timeout,
            idle_timeout=self.idle_timeout,
        ):
            letter = DeadLetter.model_validate_json(_value(msg))
            if letter.envelope is not None:
                with _autocommit(self.url) as conn:
                    conn.execute(
                        "DELETE FROM processed_events WHERE consumer = %s AND event_id = %s",
                        (self.kafka.group_id(letter.consumer), letter.envelope.event_id),
                    )
                self.kafka.produce(
                    [(topic.value, letter.key, letter.envelope.model_dump_json().encode())]
                )
                replayed += 1
            consumer.commit(message=msg, asynchronous=False)
            if max_messages is not None and replayed >= max_messages:
                break
        return replayed

    def get_state(
        self, entity: str, entity_id: str, as_of: datetime | None = None
    ) -> dict[str, Any] | None:
        with self._tx(None) as cur:
            cur.execute(
                "SELECT state FROM pillar_state WHERE entity = %s AND entity_id = %s"
                " AND (%s::timestamptz IS NULL OR recorded_at <= %s)"
                " ORDER BY version DESC LIMIT 1",
                (entity, entity_id, as_of, as_of),
            )
            row = cur.fetchone()
        return dict(row["state"]) if row else None  # type: ignore[call-overload]

    def put_state(
        self, entity: str, entity_id: str, state: dict[str, Any], expected_version: int
    ) -> int:
        with self._tx(None) as cur:
            cur.execute(
                "SELECT coalesce(max(version), 0) AS v FROM pillar_state"
                " WHERE entity = %s AND entity_id = %s",
                (entity, entity_id),
            )
            row = cur.fetchone()
            current = int(row["v"]) if row else 0  # type: ignore[call-overload]
            if current != expected_version:
                raise ConcurrencyError(f"expected v{expected_version}, current v{current}")
            try:
                with cur.connection.transaction():
                    cur.execute(
                        "INSERT INTO pillar_state (entity, entity_id, version, state)"
                        " VALUES (%s, %s, %s, %s)",
                        (entity, entity_id, current + 1, Jsonb(to_jsonable_python(state))),
                    )
            except psycopg.errors.UniqueViolation as exc:
                raise ConcurrencyError(f"v{current + 1} was written concurrently") from exc
        return current + 1

    def route_outbound(self, package: OutboundPackage) -> RouteReceipt:
        """Only packages with a recorded HITL-5 approval of this manifest hash leave the pillar."""
        if not package.authorized_by:
            return RouteReceipt(accepted=False, reason="HITL-5 authorization missing")
        with self._tx(package.tenant_id) as cur:
            cur.execute(
                "SELECT 1 FROM approvals WHERE tenant_id = %s AND gate = %s"
                " AND artifact_hash = %s AND decided_by = %s AND decision = 'approve' LIMIT 1",
                (
                    package.tenant_id,
                    Gate.SUBMISSION_AUTHORIZATION.value,
                    package.manifest_hash,
                    package.authorized_by,
                ),
            )
            if cur.fetchone() is None:
                return RouteReceipt(
                    accepted=False, reason="no recorded HITL-5 approval for this manifest hash"
                )
            envelope = PillarEnvelope(
                event_type=EventType.SUBMISSION_AUTHORIZED,
                schema_ref=OUTBOUND_SCHEMA,
                tenant_id=package.tenant_id,
                subject_id=str(package.opportunity_id),
                producer=Producer(service=SERVICE),
                data_classification="confidential",
                payload=package.model_dump(mode="json"),
            )
            write_outbox(cur, envelope)
        return RouteReceipt(accepted=True, tracking_id=str(envelope.event_id))

    def _decode(self, msg: Message, group: str) -> PillarEnvelope | None:
        try:
            return PillarEnvelope.model_validate_json(_value(msg))
        except ValidationError as exc:
            key = msg.key()
            self.dead_letters.send(
                DeadLetter(
                    source_topic=Topic(self.kafka.logical(msg.topic() or "")),
                    key=key.decode() if isinstance(key, bytes) else str(key or ""),
                    consumer=group,
                    attempts=1,
                    error_type="InvalidEnvelope",
                    error=str(exc.errors(include_input=False))[:2000],
                    raw=_value(msg).decode(errors="replace"),
                )
            )
            return None


@contextmanager
def _autocommit(url: str) -> Iterator[psycopg.Connection[Any]]:
    with connect(url) as conn:
        conn.autocommit = True
        yield conn


def _value(msg: Message) -> bytes:
    value = msg.value()
    return value if isinstance(value, bytes) else (value or "").encode()


def _is_processed(conn: psycopg.Connection[Any], consumer: str, event_id: UUID) -> bool:
    row = conn.execute(
        "SELECT 1 FROM processed_events WHERE consumer = %s AND event_id = %s",
        (consumer, event_id),
    ).fetchone()
    return row is not None


def _mark_processed(conn: psycopg.Connection[Any], consumer: str, event_id: UUID) -> None:
    conn.execute(
        "INSERT INTO processed_events (consumer, event_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (consumer, event_id),
    )
