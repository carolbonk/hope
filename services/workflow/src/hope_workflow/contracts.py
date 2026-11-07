"""Workflow-facing contracts that other services will need (candidates for hope_core.schemas).

Agent activity inputs/outputs, workflow signals and A12 notification models. Shared contracts
that already exist (GrantOpportunity, AgencyProfile, MatrixRow, ProposalFramework, HitlRequest,
HitlDecision, RouteReceipt) are reused, never redefined.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from hope_core.pillar import RouteReceipt
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.common import Contract, Evidence
from hope_core.schemas.grant_opportunity import GrantOpportunity
from hope_core.schemas.hitl import Gate, HitlDecision, HitlRequest
from hope_core.schemas.lifecycle import OpportunityState
from hope_core.schemas.opportunity_matrix import MatrixRow
from hope_core.schemas.proposal_framework import ProposalFramework
from hope_core.topics import EventType
from pydantic import Field


class LifecycleInput(Contract):
    tenant_id: UUID
    agency_id: UUID
    opportunity_id: UUID
    small_org_ack: bool = Field(False, description="waives HITL-2 separation of duties")


class LifecycleContext(Contract):
    profile: AgencyProfile
    opportunity: GrantOpportunity


class AgentContext(Contract):
    tenant_id: UUID
    agency_id: UUID
    workflow_id: str
    profile: AgencyProfile
    opportunity: GrantOpportunity
    feedback: list[str] = []


class EligibilityResult(Contract):
    status: Literal["eligible", "needs_review", "ineligible"]
    reasons: list[str] = []
    effort_hours: float | None = None


class AlignmentAssessment(Contract):
    score: float = Field(ge=0, le=100)
    rationale: str
    evidence: list[Evidence] = []


class RecommendRequest(Contract):
    ctx: AgentContext
    alignment: AlignmentAssessment


class BudgetRequest(Contract):
    ctx: AgentContext
    go: HitlDecision


class BudgetDraft(Contract):
    framework: ProposalFramework
    drafted_by: str = Field(description="user who owns the draft; cannot approve HITL-2")


class NarrativeDraft(Contract):
    draft_id: str
    framework_hash: str
    sections: dict[str, str]
    content_hash: str


class VerifyRequest(Contract):
    ctx: AgentContext
    subject: Literal["framework", "narrative"]
    framework: ProposalFramework
    draft: NarrativeDraft | None = None


class VerificationReport(Contract):
    passed: bool
    issues: list[str] = []


class NarrativeRequest(Contract):
    ctx: AgentContext
    framework: ProposalFramework


class ComplianceRequest(Contract):
    ctx: AgentContext
    framework: ProposalFramework
    draft: NarrativeDraft


class ComplianceReport(Contract):
    passed: bool
    deficiencies: list[str] = []


class PackageRequest(Contract):
    ctx: AgentContext
    framework: ProposalFramework
    draft: NarrativeDraft


class SubmissionPackage(Contract):
    manifest_hash: str
    channel: str
    payload_ref: str
    valid: bool
    errors: list[str] = []


class SubmitRequest(Contract):
    ctx: AgentContext
    package: SubmissionPackage
    authorized_by: str


class ProfileArea(StrEnum):
    ELIGIBILITY = "eligibility"
    BUDGET = "budget"
    REQUIRED_SECTIONS = "required_sections"
    APPROVALS = "approvals"
    DEADLINE = "deadline"


class RevalidateSignal(Contract):
    """Protected profile change (legal, financials, approval_hierarchy) after HITL-0."""

    profile_version: int
    changed_paths: list[str]


class AmendmentSignal(Contract):
    """`opportunity.amended` after re-parse and diff."""

    amendment_seq: int
    affected: list[ProfileArea]


class Milestone(Contract):
    name: str
    due_at: datetime
    owner_role: str
    gate: Gate | None = None


class DeadlinePlanRequest(Contract):
    opportunity: GrantOpportunity
    now: datetime


class DeadlinePlan(Contract):
    internal_deadline: datetime | None
    funder_timezone: str | None = None
    buffer_hours: int = 0
    milestones: list[Milestone] = []


NotificationKind = Literal[
    "hitl_requested",
    "hitl_rejected",
    "escalation",
    "milestone",
    "deadline_warning",
    "expired",
    "revalidation",
]
Channel = Literal["in_app", "email", "slack", "sms"]


class NotificationRequest(Contract):
    notification_id: UUID
    tenant_id: UUID
    workflow_id: str
    subject_id: str
    kind: NotificationKind
    recipient_roles: list[str]
    title: str
    body: str = ""
    channels: list[Channel] = ["in_app", "email"]
    gate: Gate | None = None


class EventRequest(Contract):
    """A pillar event built by the workflow. The activity wraps it in a PillarEnvelope."""

    event_id: UUID
    event_type: EventType
    tenant_id: UUID
    subject_id: str
    workflow_id: str
    payload: dict[str, Any]


class ApprovalRecord(Contract):
    """One row of the append-only approvals table (decisions and invalidations)."""

    approval_id: UUID
    tenant_id: UUID
    workflow_id: str
    gate: Gate
    decision: str
    artifact_hash: str
    decided_by: str
    decided_at: datetime
    comment: str | None = None


class ProjectionRow(Contract):
    tenant_id: UUID
    opportunity_id: UUID
    agency_id: UUID
    state: OpportunityState
    workflow_id: str
    composite_score: float | None = None
    recommendation: str | None = None
    internal_deadline: datetime | None = None


class LifecycleStatus(Contract):
    state: OpportunityState
    pending: HitlRequest | None = None
    approvals: dict[Gate, HitlDecision] = {}
    plan: DeadlinePlan | None = None


class LifecycleOutcome(Contract):
    state: OpportunityState
    receipt: RouteReceipt | None = None
    matrix_row: MatrixRow | None = None
