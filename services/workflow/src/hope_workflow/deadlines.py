"""A12 Deadline agent: deterministic back-scheduling from the funder deadline (blueprint 2.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from hope_core.schemas.grant_opportunity import GrantOpportunity
from hope_core.schemas.hitl import Gate

from hope_workflow.contracts import DeadlinePlan, Milestone

GRANTS_GOV_BUFFER_HOURS = 72
WARNING_OFFSETS = (timedelta(hours=72), timedelta(hours=24))
"""Escalations before the internal deadline (blueprint 4.3 global guard)."""

MILESTONES: tuple[tuple[str, int, str, Gate | None], ...] = (
    ("go_no_go", 21, "development_director", Gate.GO_NO_GO),
    ("budget_signoff", 14, "finance_director", Gate.BUDGET_SIGNOFF),
    ("narrative_complete", 9, "development_director", None),
    ("compliance_attestation", 6, "compliance_officer", Gate.COMPLIANCE_ATTESTATION),
    ("executive_approval", 4, "executive_director", Gate.EXECUTIVE_APPROVAL),
    ("package_ready", 2, "development_director", None),
    ("submission_authorization", 0, "aor", Gate.SUBMISSION_AUTHORIZATION),
)
"""(name, calendar days before the internal deadline, owner role, gate)."""


def submission_buffer_hours(opportunity: GrantOpportunity) -> int:
    via_grants_gov = (
        opportunity.source.system == "grants_gov"
        or opportunity.requirements.submission_channel == "grants_gov"
    )
    return GRANTS_GOV_BUFFER_HOURS if via_grants_gov else 0


def plan_deadlines(opportunity: GrantOpportunity, now: datetime) -> DeadlinePlan:
    due = opportunity.deadlines.application_due
    if due is None:
        return DeadlinePlan(internal_deadline=None)
    tz = ZoneInfo(due.timezone)
    local_due = due.value.replace(tzinfo=tz) if due.value.tzinfo is None else due.value
    buffer = submission_buffer_hours(opportunity)
    internal_local = (local_due - timedelta(hours=buffer)).astimezone(tz)
    milestones = [
        Milestone(name=name, due_at=at, owner_role=role, gate=gate)
        for name, days, role, gate in MILESTONES
        if (at := (internal_local - timedelta(days=days)).astimezone(UTC)) > now
    ]
    return DeadlinePlan(
        internal_deadline=internal_local.astimezone(UTC),
        funder_timezone=due.timezone,
        buffer_hours=buffer,
        milestones=milestones,
    )
