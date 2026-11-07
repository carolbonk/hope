from __future__ import annotations

from typing import Any

import psycopg
import pytest
from hope_core.pillar import PillarPort
from hope_core.testing.factories import TENANT_A
from hope_core.testing.pillar_contract import PillarContract, make_event
from hope_pillar.dlq import InMemoryDeadLetterSink, RetryPolicy
from hope_pillar.pillar import KafkaPostgresPillar

pytestmark = pytest.mark.db

Fixture = tuple[KafkaPostgresPillar, InMemoryDeadLetterSink]


def record_hitl5_approval(admin_url: str, manifest_hash: str, aor: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO approvals (tenant_id, workflow_id, gate, decision, artifact_hash,"
            " decided_by) VALUES (%s, 'wf-contract', 'HITL-5', 'approve', %s, %s)",
            (TENANT_A, manifest_hash, aor),
        )


class TestKafkaPostgresPillarContract(PillarContract):
    @pytest.fixture
    def pillar(self, kafka_pillar: Fixture, migrated_db: str) -> PillarPort:
        record_hitl5_approval(migrated_db, "sha256:abc", "aor-1")
        return kafka_pillar[0]


def test_publish_joins_caller_transaction(kafka_pillar: Fixture) -> None:
    pillar, _ = kafka_pillar
    rolled_back, committed = make_event(), make_event()
    with pytest.raises(RuntimeError), pillar.transaction(TENANT_A):
        pillar.publish(rolled_back)
        raise RuntimeError("abort")
    with pillar.transaction(TENANT_A):
        pillar.publish(committed)
    got = list(pillar.subscribe([committed.event_type], group="tx"))
    assert [e.event_id for e in got] == [committed.event_id]


def test_kafka_redelivery_is_deduplicated(kafka_pillar: Fixture) -> None:
    pillar, _ = kafka_pillar
    event = make_event()
    raw = event.model_dump_json().encode()
    pillar.kafka.produce([(event.topic.value, event.subject_id, raw)] * 2)
    assert [e.event_id for e in pillar.subscribe([event.event_type], group="dup")] == [
        event.event_id
    ]


def test_failing_handler_dead_letters_then_replays(kafka_pillar: Fixture) -> None:
    pillar, sink = kafka_pillar
    event = make_event()
    pillar.publish(event)
    calls: list[Any] = []

    def broken(_: Any) -> None:
        calls.append(1)
        raise ValueError("boom")

    policy = RetryPolicy(max_attempts=3, sleep=lambda _: None)
    assert pillar.consume([event.event_type], "worker", broken, policy=policy) == 1
    assert len(calls) == 3
    [letter] = sink.letters
    assert (letter.attempts, letter.error, letter.consumer) == (3, "boom", "worker")
    assert letter.dlq_topic == "gop.dlq.opportunity.events"

    pillar.kafka.produce([(letter.dlq_topic, letter.key, letter.model_dump_json().encode())])
    assert pillar.replay_dead_letters(event.topic) == 1
    seen: list[Any] = []
    pillar.consume([event.event_type], "worker", seen.append, policy=policy)
    assert [e.event_id for e in seen] == [event.event_id]


def test_poison_message_goes_to_dlq(kafka_pillar: Fixture) -> None:
    pillar, sink = kafka_pillar
    event = make_event()
    pillar.kafka.produce([(event.topic.value, "k", b"not an envelope")])
    pillar.publish(event)
    got = list(pillar.subscribe([event.event_type], group="poison"))
    assert [e.event_id for e in got] == [event.event_id]
    assert [letter.error_type for letter in sink.letters] == ["InvalidEnvelope"]
    assert sink.letters[0].raw == "not an envelope"


def test_outbound_requires_recorded_approval(kafka_pillar: Fixture) -> None:
    from uuid import uuid4

    from hope_core.pillar import OutboundPackage

    pillar, _ = kafka_pillar
    package = OutboundPackage(
        tenant_id=TENANT_A,
        opportunity_id=uuid4(),
        channel="grants_gov",
        manifest_hash=f"sha256:{uuid4().hex}",
        authorized_by="aor-unrecorded",
        payload_ref="s3://bucket/pkg.zip",
    )
    receipt = pillar.route_outbound(package)
    assert not receipt.accepted
    assert receipt.reason == "no recorded HITL-5 approval for this manifest hash"
