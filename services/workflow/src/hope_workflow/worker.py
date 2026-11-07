"""Worker entrypoint: `python -m hope_workflow.worker [--queue q.budget ...] [--postgres]`."""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Iterable

from temporalio.client import Client
from temporalio.worker import Worker

from hope_workflow.activities import PlatformActivities
from hope_workflow.agents import AgentActivities, AgentRegistry
from hope_workflow.client import connect
from hope_workflow.queues import TaskQueue
from hope_workflow.stubs import StubAgents
from hope_workflow.workflow import OpportunityLifecycleWorkflow

log = logging.getLogger("hope_workflow.worker")


def build_workers(
    client: Client,
    agents: AgentRegistry,
    platform: PlatformActivities,
    queues: Iterable[TaskQueue] = tuple(TaskQueue),
) -> list[Worker]:
    by_queue = AgentActivities(agents).by_queue()
    workers = []
    for queue in queues:
        if queue is TaskQueue.WORKFLOW:
            workers.append(
                Worker(
                    client,
                    task_queue=queue,
                    workflows=[OpportunityLifecycleWorkflow],
                    activities=platform.workflow_queue(),
                )
            )
        elif queue is TaskQueue.NOTIFY:
            workers.append(Worker(client, task_queue=queue, activities=platform.notify_queue()))
        else:
            workers.append(Worker(client, task_queue=queue, activities=[by_queue[queue]]))
    return workers


def platform_activities(postgres: bool) -> PlatformActivities:
    if not postgres:
        return PlatformActivities()
    from hope_workflow.postgres import PostgresApprovalStore, PostgresProjectionStore

    return PlatformActivities(
        approvals=PostgresApprovalStore(), projection=PostgresProjectionStore()
    )


async def serve(queues: list[TaskQueue], postgres: bool) -> None:
    client = await connect()
    platform = platform_activities(postgres)
    workers = build_workers(client, StubAgents(pillar=platform.pillar).registry(), platform, queues)
    log.info("polling %s", ", ".join(queues))
    await asyncio.gather(*(w.run() for w in workers))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queue",
        action="append",
        choices=[q.value for q in TaskQueue],
        help="task queue to poll (repeatable, default: all)",
    )
    parser.add_argument(
        "--postgres", action="store_true", help="write approvals and projection to Postgres"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    queues = [TaskQueue(q) for q in args.queue] if args.queue else list(TaskQueue)
    asyncio.run(serve(queues, args.postgres))


if __name__ == "__main__":
    main()
