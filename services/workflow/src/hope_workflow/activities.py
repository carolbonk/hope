"""Platform activities: context loading, pillar events, approvals, projection, A12 notify."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from hope_core.envelope import PillarEnvelope, Producer, Trace
from hope_core.pillar import InMemoryPillar, PillarPort
from hope_core.topics import EventType
from temporalio import activity

from hope_workflow.contracts import (
    ApprovalRecord,
    DeadlinePlan,
    DeadlinePlanRequest,
    EventRequest,
    LifecycleContext,
    LifecycleInput,
    NotificationRequest,
    ProjectionRow,
)
from hope_workflow.deadlines import plan_deadlines
from hope_workflow.ports import (
    ApprovalStore,
    ContextSource,
    InMemoryApprovalStore,
    InMemoryContextSource,
    InMemoryProjectionStore,
    NotificationChannel,
    ProjectionStore,
    StubChannel,
)

PRODUCER = Producer(service="workflow", agent_id="A0")
A12 = Producer(service="workflow", agent_id="A12")


def envelope(req: EventRequest, producer: Producer = PRODUCER) -> PillarEnvelope:
    return PillarEnvelope(
        event_id=req.event_id,
        event_type=req.event_type,
        schema_ref=f"hope://{req.event_type.value}/v1",
        tenant_id=req.tenant_id,
        subject_id=req.subject_id,
        producer=producer,
        trace=Trace(
            trace_id=uuid5(NAMESPACE_URL, req.workflow_id).hex, correlation_id=req.workflow_id
        ),
        data_classification="confidential",
        payload=req.payload,
    )


@dataclass
class PlatformActivities:
    pillar: PillarPort = field(default_factory=InMemoryPillar)
    contexts: ContextSource = field(default_factory=InMemoryContextSource)
    approvals: ApprovalStore = field(default_factory=InMemoryApprovalStore)
    projection: ProjectionStore = field(default_factory=InMemoryProjectionStore)
    channels: Sequence[NotificationChannel] = field(
        default_factory=lambda: [StubChannel("in_app"), StubChannel("email")]
    )

    @activity.defn(name="platform.load_context")
    async def load_context(self, inp: LifecycleInput) -> LifecycleContext:
        return await asyncio.to_thread(
            self.contexts.load, inp.tenant_id, inp.agency_id, inp.opportunity_id
        )

    @activity.defn(name="platform.publish")
    async def publish(self, req: EventRequest) -> None:
        await asyncio.to_thread(self.pillar.publish, envelope(req))

    @activity.defn(name="platform.record_approval")
    async def record_approval(self, record: ApprovalRecord) -> None:
        await asyncio.to_thread(self.approvals.append, record)

    @activity.defn(name="platform.mirror_state")
    async def mirror_state(self, row: ProjectionRow) -> None:
        await asyncio.to_thread(self.projection.upsert, row)

    @activity.defn(name="a12.plan_deadlines")
    async def plan_deadlines(self, req: DeadlinePlanRequest) -> DeadlinePlan:
        return plan_deadlines(req.opportunity, req.now)

    @activity.defn(name="a12.notify")
    async def notify(self, req: NotificationRequest) -> None:
        event = EventRequest(
            event_id=req.notification_id,
            event_type=EventType.NOTIFICATION_REQUESTED,
            tenant_id=req.tenant_id,
            subject_id=req.subject_id,
            workflow_id=req.workflow_id,
            payload=req.model_dump(mode="json"),
        )
        await asyncio.to_thread(self.pillar.publish, envelope(event, A12))
        for channel in self.channels:
            await asyncio.to_thread(channel.send, req)

    def workflow_queue(self) -> list[Callable[..., Any]]:
        return [self.load_context, self.publish, self.record_approval, self.mirror_state]

    def notify_queue(self) -> list[Callable[..., Any]]:
        return [self.plan_deadlines, self.notify]
