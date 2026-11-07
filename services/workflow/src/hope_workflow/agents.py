"""Typed activity interfaces for the agent steps. Implementations come from an AgentRegistry,
so the integration step swaps stubs for the real services without touching the workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from hope_core.pillar import RouteReceipt
from hope_core.schemas.opportunity_matrix import MatrixRow
from temporalio import activity

from hope_workflow.contracts import (
    AgentContext,
    AlignmentAssessment,
    BudgetDraft,
    BudgetRequest,
    ComplianceReport,
    ComplianceRequest,
    EligibilityResult,
    NarrativeDraft,
    NarrativeRequest,
    PackageRequest,
    RecommendRequest,
    SubmissionPackage,
    SubmitRequest,
    VerificationReport,
    VerifyRequest,
)
from hope_workflow.queues import TaskQueue


class EligibilityAgent(Protocol):
    async def __call__(self, req: AgentContext, /) -> EligibilityResult: ...


class AlignmentAgent(Protocol):
    async def __call__(self, req: AgentContext, /) -> AlignmentAssessment: ...


class RecommendAgent(Protocol):
    async def __call__(self, req: RecommendRequest, /) -> MatrixRow: ...


class BudgetAgent(Protocol):
    async def __call__(self, req: BudgetRequest, /) -> BudgetDraft: ...


class VerifyAgent(Protocol):
    async def __call__(self, req: VerifyRequest, /) -> VerificationReport: ...


class NarrativeAgent(Protocol):
    async def __call__(self, req: NarrativeRequest, /) -> NarrativeDraft: ...


class ComplianceAgent(Protocol):
    async def __call__(self, req: ComplianceRequest, /) -> ComplianceReport: ...


class PackageAgent(Protocol):
    async def __call__(self, req: PackageRequest, /) -> SubmissionPackage: ...


class SubmitAgent(Protocol):
    async def __call__(self, req: SubmitRequest, /) -> RouteReceipt: ...


@dataclass
class AgentRegistry:
    eligibility: EligibilityAgent
    alignment: AlignmentAgent
    recommend: RecommendAgent
    budget: BudgetAgent
    verify: VerifyAgent
    narrative: NarrativeAgent
    compliance: ComplianceAgent
    package: PackageAgent
    submit: SubmitAgent


class AgentActivities:
    """One activity per agent step. Each runs on its own task queue (AGENT_QUEUES)."""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    @activity.defn(name="agent.eligibility")
    async def eligibility(self, req: AgentContext) -> EligibilityResult:
        return await self.registry.eligibility(req)

    @activity.defn(name="agent.alignment")
    async def alignment(self, req: AgentContext) -> AlignmentAssessment:
        return await self.registry.alignment(req)

    @activity.defn(name="agent.recommend")
    async def recommend(self, req: RecommendRequest) -> MatrixRow:
        return await self.registry.recommend(req)

    @activity.defn(name="agent.budget")
    async def budget(self, req: BudgetRequest) -> BudgetDraft:
        return await self.registry.budget(req)

    @activity.defn(name="agent.verify")
    async def verify(self, req: VerifyRequest) -> VerificationReport:
        return await self.registry.verify(req)

    @activity.defn(name="agent.narrative")
    async def narrative(self, req: NarrativeRequest) -> NarrativeDraft:
        return await self.registry.narrative(req)

    @activity.defn(name="agent.compliance")
    async def compliance(self, req: ComplianceRequest) -> ComplianceReport:
        return await self.registry.compliance(req)

    @activity.defn(name="agent.package")
    async def package(self, req: PackageRequest) -> SubmissionPackage:
        return await self.registry.package(req)

    @activity.defn(name="agent.submit")
    async def submit(self, req: SubmitRequest) -> RouteReceipt:
        return await self.registry.submit(req)

    def by_queue(self) -> dict[TaskQueue, Callable[..., Any]]:
        return {
            TaskQueue.ELIGIBILITY: self.eligibility,
            TaskQueue.ALIGNMENT: self.alignment,
            TaskQueue.RECOMMEND: self.recommend,
            TaskQueue.BUDGET: self.budget,
            TaskQueue.VERIFY: self.verify,
            TaskQueue.NARRATIVE: self.narrative,
            TaskQueue.COMPLIANCE: self.compliance,
            TaskQueue.PACKAGE: self.package,
            TaskQueue.SUBMIT: self.submit,
        }
