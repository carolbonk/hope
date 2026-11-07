"""Client helpers: idempotent start, and pillar events mapped to workflow signals."""

from __future__ import annotations

from hope_core.envelope import PillarEnvelope
from hope_core.schemas.agency_profile import PROTECTED_PROFILE_PATHS
from hope_core.settings import HopeSettings, get_settings
from hope_core.topics import EventType
from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDConflictPolicy
from temporalio.contrib.pydantic import pydantic_data_converter

from hope_workflow.contracts import (
    AmendmentSignal,
    LifecycleInput,
    LifecycleOutcome,
    RevalidateSignal,
)
from hope_workflow.queues import TaskQueue
from hope_workflow.workflow import OpportunityLifecycleWorkflow, lifecycle_workflow_id

LifecycleHandle = WorkflowHandle[OpportunityLifecycleWorkflow, LifecycleOutcome]


async def connect(settings: HopeSettings | None = None) -> Client:
    s = settings or get_settings()
    return await Client.connect(
        s.temporal_address, namespace=s.temporal_namespace, data_converter=pydantic_data_converter
    )


async def start_lifecycle(client: Client, inp: LifecycleInput) -> LifecycleHandle:
    """Duplicate starts for the same tenant/agency/opportunity return the running workflow."""
    return await client.start_workflow(
        OpportunityLifecycleWorkflow.run,
        inp,
        id=lifecycle_workflow_id(inp.tenant_id, inp.agency_id, inp.opportunity_id),
        task_queue=TaskQueue.WORKFLOW,
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
    )


def revalidate_signal(env: PillarEnvelope) -> RevalidateSignal | None:
    """`profile.updated` with a protected change -> revalidate. Payload: version, changed_paths."""
    if env.event_type is not EventType.PROFILE_UPDATED or env.payload is None:
        return None
    paths = [
        p
        for p in env.payload.get("changed_paths", [])
        if p.split(".")[0] in PROTECTED_PROFILE_PATHS
    ]
    if not paths:
        return None
    return RevalidateSignal(profile_version=env.payload["version"], changed_paths=paths)


def amendment_signal(env: PillarEnvelope) -> AmendmentSignal | None:
    """`opportunity.amended` -> amendment. Payload: amendment_seq, affected."""
    if env.event_type is not EventType.OPPORTUNITY_AMENDED or env.payload is None:
        return None
    return AmendmentSignal.model_validate(
        {k: env.payload[k] for k in ("amendment_seq", "affected") if k in env.payload}
    )
