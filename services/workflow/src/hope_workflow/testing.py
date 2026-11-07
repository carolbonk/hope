"""Test harness for the lifecycle workflow on a time-skipping Temporal server (reusable by the
integration step with real agent registries)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from hope_core.pillar import InMemoryPillar
from hope_core.schemas.hitl import Decision, Gate, HitlDecision, HitlRequest
from hope_core.testing import factories
from hope_core.topics import EventType
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment

from hope_workflow.activities import PlatformActivities
from hope_workflow.client import LifecycleHandle, start_lifecycle
from hope_workflow.contracts import LifecycleContext, LifecycleInput, LifecycleStatus
from hope_workflow.ports import (
    InMemoryApprovalStore,
    InMemoryContextSource,
    InMemoryProjectionStore,
    StubChannel,
)
from hope_workflow.stubs import StubAgents
from hope_workflow.worker import build_workers
from hope_workflow.workflow import OpportunityLifecycleWorkflow

POLL_SECONDS = 0.05
POLL_LIMIT = 400


@dataclass
class LifecycleHarness:
    env: WorkflowEnvironment
    agents: StubAgents
    pillar: InMemoryPillar = field(default_factory=InMemoryPillar)
    contexts: InMemoryContextSource = field(default_factory=InMemoryContextSource)
    approvals: InMemoryApprovalStore = field(default_factory=InMemoryApprovalStore)
    projection: InMemoryProjectionStore = field(default_factory=InMemoryProjectionStore)
    channel: StubChannel = field(default_factory=lambda: StubChannel("in_app"))
    handle: LifecycleHandle | None = None
    _seen: set[UUID] = field(default_factory=set)

    @property
    def platform(self) -> PlatformActivities:
        return PlatformActivities(
            pillar=self.pillar,
            contexts=self.contexts,
            approvals=self.approvals,
            projection=self.projection,
            channels=[self.channel],
        )

    async def start(self, ctx: LifecycleContext, **inp: Any) -> LifecycleHandle:
        self.contexts.put(ctx)
        self.handle = await start_lifecycle(
            self.env.client,
            LifecycleInput(
                tenant_id=ctx.profile.tenant_id,
                agency_id=ctx.profile.agency_id,
                opportunity_id=ctx.opportunity.opportunity_id,
                **inp,
            ),
        )
        return self.handle

    async def status(self) -> LifecycleStatus:
        assert self.handle is not None
        return await self.handle.query(OpportunityLifecycleWorkflow.status)

    async def wait_for_gate(self, gate: Gate) -> HitlRequest:
        """Wait for a gate request this harness has not decided yet."""
        for _ in range(POLL_LIMIT):
            pending = (await self.status()).pending
            if pending and pending.gate is gate and pending.request_id not in self._seen:
                return pending
            await asyncio.sleep(POLL_SECONDS)
        raise AssertionError(f"{gate} was never requested; status={await self.status()}")

    async def decide(
        self,
        gate: Gate,
        decision: Decision = "approve",
        *,
        by: str | None = None,
        role: str | None = None,
        artifact_hash: str | None = None,
        **details: Any,
    ) -> HitlRequest:
        assert self.handle is not None
        request = await self.wait_for_gate(gate)
        self._seen.add(request.request_id)
        role = role or request.approver_roles[0]
        await self.handle.signal(
            OpportunityLifecycleWorkflow.submit_decision,
            HitlDecision(
                request_id=request.request_id,
                gate=gate,
                decision=decision,
                artifact_hash=artifact_hash or request.artifact_hash,
                decided_by=by or f"user:{role}",
                decided_at=datetime.now(UTC),
                details={"role": role, **details},
            ),
        )
        return request

    async def wait_for_notification(self, text: str) -> None:
        for _ in range(POLL_LIMIT):
            if any(text in n.title for n in self.channel.sent):
                return
            await asyncio.sleep(POLL_SECONDS)
        raise AssertionError(f"no notification containing {text!r}")

    def forget(self, request: HitlRequest) -> None:
        """Allow deciding a request again (it is still pending after a rejected decision)."""
        self._seen.discard(request.request_id)

    async def approve_all(self, *gates: Gate) -> None:
        for gate in gates:
            await self.decide(gate, "go" if gate is Gate.GO_NO_GO else "approve")

    def events(self, event_type: EventType) -> list[dict[str, Any]]:
        return [
            cast(dict[str, Any], e.payload) for e in self.pillar.log if e.event_type is event_type
        ]

    def notifications(self, kind: str) -> list[str]:
        return [n.title for n in self.channel.sent if n.kind == kind]


def sample_context(**opportunity: Any) -> LifecycleContext:
    return LifecycleContext(
        profile=factories.agency_profile(), opportunity=factories.grant_opportunity(**opportunity)
    )


@asynccontextmanager
async def lifecycle_harness(agents: StubAgents | None = None) -> AsyncIterator[LifecycleHarness]:
    env = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    async with env, AsyncExitStack() as stack:
        pillar = InMemoryPillar()
        harness = LifecycleHarness(
            env=env, agents=agents or StubAgents(pillar=pillar), pillar=pillar
        )
        for worker in build_workers(env.client, harness.agents.registry(), harness.platform):
            await stack.enter_async_context(worker)
        yield harness
