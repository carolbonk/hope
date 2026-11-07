from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from hope_core.envelope import PillarEnvelope, Producer
from hope_core.pillar import InMemoryPillar
from hope_core.schemas.hitl import Gate, HitlDecision
from hope_core.testing.factories import TENANT_A
from hope_core.testing.pillar_contract import make_event
from hope_core.topics import EventType
from hope_pillar.contracts import PACKAGING_AGENT
from hope_pillar.dlq import InMemoryDeadLetterSink, RetryPolicy, run_with_retry
from hope_pillar.router import PillarRouter, RouteRejected


def envelope(
    event_type: EventType = EventType.HITL_DECIDED,
    schema_ref: str = "hitl-decision/1.0.0",
    payload: dict[str, Any] | None = None,
    agent_id: str | None = None,
) -> PillarEnvelope:
    if payload is None:
        payload = HitlDecision(
            request_id=uuid4(),
            gate=Gate.GO_NO_GO,
            decision="go",
            artifact_hash="sha256:x",
            decided_by="u1",
            decided_at=datetime.now(UTC),
        ).model_dump(mode="json")
    return PillarEnvelope(
        event_type=event_type,
        schema_ref=schema_ref,
        tenant_id=TENANT_A,
        subject_id="s1",
        producer=Producer(service="test", agent_id=agent_id),
        payload=payload,
    )


@pytest.fixture
def setup() -> tuple[PillarRouter, InMemoryPillar, InMemoryDeadLetterSink]:
    pillar, sink = InMemoryPillar(), InMemoryDeadLetterSink()
    return PillarRouter(pillar, sink), pillar, sink


def test_valid_envelope_is_published(setup: Any) -> None:
    router, pillar, sink = setup
    env = envelope()
    router.route(env)
    assert pillar.log == [env]
    assert sink.letters == []


@pytest.mark.parametrize(
    ("env", "reason"),
    [
        (envelope(payload={"decision": "go"}), "payload does not match hitl-decision/1.0.0"),
        (envelope(schema_ref="nope/1.0.0"), "unknown schema_ref"),
        (envelope(schema_ref="hitl-decision/2.0.0"), "unsupported version"),
        (envelope(payload={"blob": "x" * 300_000}), "payload exceeds 256 KB"),
        (
            envelope(EventType.APPLICATION_SUBMITTED, agent_id="A7"),
            "agent 'A7' may not produce to gop.outbound.packages",
        ),
    ],
)
def test_bad_envelopes_go_to_dlq(setup: Any, env: PillarEnvelope, reason: str) -> None:
    router, pillar, sink = setup
    with pytest.raises(RouteRejected, match=reason.replace(".", r"\.")):
        router.route(env)
    assert pillar.log == []
    [letter] = sink.letters
    assert letter.dlq_topic == env.topic.dlq
    assert (letter.consumer, letter.attempts, letter.envelope) == ("router", 1, env)


def test_only_packaging_agent_produces_outbound(setup: Any) -> None:
    router, pillar, _ = setup
    router.route(envelope(EventType.APPLICATION_SUBMITTED, agent_id=PACKAGING_AGENT))
    assert len(pillar.log) == 1


def test_retry_backs_off_then_succeeds() -> None:
    sink = InMemoryDeadLetterSink()
    delays: list[float] = []
    calls: list[int] = []

    def flaky(_: PillarEnvelope) -> None:
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("transient")

    policy = RetryPolicy(max_attempts=5, base_delay=0.1, factor=3, sleep=delays.append)
    assert run_with_retry(flaky, make_event(), consumer="c", sink=sink, policy=policy)
    assert delays == pytest.approx([0.1, 0.3])
    assert sink.letters == []


def test_retry_exhaustion_dead_letters() -> None:
    sink = InMemoryDeadLetterSink()
    event = make_event()

    def broken(_: PillarEnvelope) -> None:
        raise KeyError("missing")

    policy = RetryPolicy(max_attempts=2, max_delay=0.5, sleep=lambda _: None)
    assert not run_with_retry(broken, event, consumer="c", sink=sink, policy=policy)
    [letter] = sink.letters
    assert (letter.attempts, letter.error_type, letter.envelope) == (2, "KeyError", event)
    assert RetryPolicy(base_delay=1, max_delay=5).delay(10) == 5
