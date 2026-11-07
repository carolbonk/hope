"""Ports the platform activities depend on, with in-memory adapters for tests and local runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from hope_core.testing import factories

from hope_workflow.contracts import (
    ApprovalRecord,
    Channel,
    LifecycleContext,
    NotificationRequest,
    ProjectionRow,
)


class ContextSource(Protocol):
    def load(self, tenant_id: UUID, agency_id: UUID, opportunity_id: UUID) -> LifecycleContext: ...


class ApprovalStore(Protocol):
    def append(self, record: ApprovalRecord) -> None: ...


class ProjectionStore(Protocol):
    def upsert(self, row: ProjectionRow) -> None: ...


class NotificationChannel(Protocol):
    def send(self, request: NotificationRequest) -> None: ...


@dataclass
class InMemoryContextSource:
    """Serves stored contexts; unknown keys get factory samples (stub until profile/ingestion)."""

    contexts: dict[tuple[UUID, UUID, UUID], LifecycleContext] = field(default_factory=dict)

    def put(self, ctx: LifecycleContext) -> None:
        key = (ctx.profile.tenant_id, ctx.profile.agency_id, ctx.opportunity.opportunity_id)
        self.contexts[key] = ctx

    def load(self, tenant_id: UUID, agency_id: UUID, opportunity_id: UUID) -> LifecycleContext:
        key = (tenant_id, agency_id, opportunity_id)
        if key not in self.contexts:
            profile = factories.agency_profile(tenant_id, agency_id=agency_id)
            opportunity = factories.grant_opportunity(opportunity_id=opportunity_id)
            self.contexts[key] = LifecycleContext(profile=profile, opportunity=opportunity)
        return self.contexts[key]


@dataclass
class InMemoryApprovalStore:
    records: list[ApprovalRecord] = field(default_factory=list)

    def append(self, record: ApprovalRecord) -> None:
        if all(r.approval_id != record.approval_id for r in self.records):
            self.records.append(record)


@dataclass
class InMemoryProjectionStore:
    rows: dict[tuple[UUID, UUID, UUID], ProjectionRow] = field(default_factory=dict)
    history: list[ProjectionRow] = field(default_factory=list)

    def upsert(self, row: ProjectionRow) -> None:
        self.rows[(row.tenant_id, row.opportunity_id, row.agency_id)] = row
        self.history.append(row)


@dataclass
class StubChannel:
    """Channel adapter stub (SES/SendGrid, Slack/Teams, Twilio come later)."""

    channel: Channel
    sent: list[NotificationRequest] = field(default_factory=list)

    def send(self, request: NotificationRequest) -> None:
        self.sent.append(request)
