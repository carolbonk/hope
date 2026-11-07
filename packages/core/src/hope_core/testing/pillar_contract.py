"""Contract tests every PillarPort implementation must pass.

Usage in a service test module:

    from hope_core.testing.pillar_contract import PillarContract

    class TestKafkaPillar(PillarContract):
        @pytest.fixture
        def pillar(self): return KafkaPostgresPillar(...)
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from hope_core.envelope import PillarEnvelope, Producer
from hope_core.pillar import ConcurrencyError, OutboundPackage, PillarPort
from hope_core.testing.factories import TENANT_A
from hope_core.topics import EventType


def make_event(event_type: EventType = EventType.OPPORTUNITY_NORMALIZED) -> PillarEnvelope:
    return PillarEnvelope(
        event_type=event_type,
        schema_ref="grant-opportunity/1.0.0",
        tenant_id=TENANT_A,
        subject_id=str(uuid4()),
        producer=Producer(service="contract-test"),
        payload={"ok": True},
    )


class PillarContract:
    @pytest.fixture
    def pillar(self) -> PillarPort:
        raise NotImplementedError

    def test_publish_then_subscribe(self, pillar: PillarPort) -> None:
        event = make_event()
        pillar.publish(event)
        got = list(pillar.subscribe([event.event_type], group="g1", max_events=1))
        assert [e.event_id for e in got] == [event.event_id]

    def test_duplicate_delivery_is_skipped(self, pillar: PillarPort) -> None:
        event = make_event()
        pillar.publish(event)
        pillar.publish(event)
        got = list(pillar.subscribe([event.event_type], group="g2"))
        assert [e.event_id for e in got] == [event.event_id]

    def test_groups_are_independent(self, pillar: PillarPort) -> None:
        event = make_event()
        pillar.publish(event)
        assert len(list(pillar.subscribe([event.event_type], group="a"))) == 1
        assert len(list(pillar.subscribe([event.event_type], group="b"))) == 1

    def test_optimistic_state(self, pillar: PillarPort) -> None:
        key = str(uuid4())
        state: dict[str, Any] = {"state": "Ingested"}
        assert pillar.put_state("tenant_opportunity", key, state, expected_version=0) == 1
        with pytest.raises(ConcurrencyError):
            pillar.put_state("tenant_opportunity", key, state, expected_version=0)
        assert pillar.get_state("tenant_opportunity", key) == state

    def test_outbound_requires_authorization(self, pillar: PillarPort) -> None:
        package = OutboundPackage(
            tenant_id=TENANT_A,
            opportunity_id=uuid4(),
            channel="grants_gov",
            manifest_hash="sha256:abc",
            payload_ref="s3://bucket/pkg.zip",
        )
        assert not pillar.route_outbound(package).accepted
        authorized = package.model_copy(update={"authorized_by": "aor-1"})
        assert pillar.route_outbound(authorized).accepted
