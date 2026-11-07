"""PillarPort: the workflow depends only on this interface (blueprint 7.5).

`InMemoryPillar` is the reference implementation for tests and local runs. The production
`KafkaPostgresPillar` lives in services/pillar and must pass the same contract tests
(hope_core.testing.pillar_contract).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from pydantic import Field

from hope_core.envelope import PillarEnvelope
from hope_core.schemas.common import Contract


class ConcurrencyError(RuntimeError):
    """put_state was called with a stale expected_version."""


class OutboundPackage(Contract):
    tenant_id: UUID
    opportunity_id: UUID
    channel: str
    manifest_hash: str
    authorized_by: str | None = Field(None, description="AOR user id from HITL-5")
    payload_ref: str


class RouteReceipt(Contract):
    accepted: bool
    reason: str | None = None
    tracking_id: str | None = None


@runtime_checkable
class PillarPort(Protocol):
    def publish(self, envelope: PillarEnvelope) -> None: ...

    def subscribe(
        self, event_types: list[str], group: str, *, max_events: int | None = None
    ) -> Iterator[PillarEnvelope]: ...

    def get_state(
        self, entity: str, entity_id: str, as_of: datetime | None = None
    ) -> dict[str, Any] | None: ...

    def put_state(
        self, entity: str, entity_id: str, state: dict[str, Any], expected_version: int
    ) -> int: ...

    def route_outbound(self, package: OutboundPackage) -> RouteReceipt: ...


class InMemoryPillar:
    def __init__(self) -> None:
        self.log: list[PillarEnvelope] = []
        self._offsets: dict[str, int] = defaultdict(int)
        self._processed: dict[str, set[UUID]] = defaultdict(set)
        self._state: dict[tuple[str, str], list[tuple[datetime | None, dict[str, Any]]]] = {}
        self.outbound: list[OutboundPackage] = []

    def publish(self, envelope: PillarEnvelope) -> None:
        self.log.append(envelope)

    def subscribe(
        self, event_types: list[str], group: str, *, max_events: int | None = None
    ) -> Iterator[PillarEnvelope]:
        delivered = 0
        while self._offsets[group] < len(self.log):
            env = self.log[self._offsets[group]]
            self._offsets[group] += 1
            if env.event_type not in event_types or env.event_id in self._processed[group]:
                continue
            self._processed[group].add(env.event_id)
            yield env
            delivered += 1
            if max_events is not None and delivered >= max_events:
                return

    def get_state(
        self, entity: str, entity_id: str, as_of: datetime | None = None
    ) -> dict[str, Any] | None:
        versions = self._state.get((entity, entity_id), [])
        if as_of is not None:
            versions = [v for v in versions if v[0] is not None and v[0] <= as_of]
        return dict(versions[-1][1]) if versions else None

    def put_state(
        self, entity: str, entity_id: str, state: dict[str, Any], expected_version: int
    ) -> int:
        versions = self._state.setdefault((entity, entity_id), [])
        if len(versions) != expected_version:
            raise ConcurrencyError(f"expected v{expected_version}, current v{len(versions)}")
        recorded_at = state.get("_recorded_at")
        versions.append((recorded_at if isinstance(recorded_at, datetime) else None, state))
        return len(versions)

    def route_outbound(self, package: OutboundPackage) -> RouteReceipt:
        if not package.authorized_by:
            return RouteReceipt(accepted=False, reason="HITL-5 authorization missing")
        self.outbound.append(package)
        return RouteReceipt(accepted=True, tracking_id=package.manifest_hash)
