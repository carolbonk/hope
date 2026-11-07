"""Stub agents that return valid contracts until the real services are integrated.

Deterministic: every output is derived from its inputs, so artifact hashes change only when
the inputs (profile version, feedback, upstream artifacts) change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from hope_core.hashing import content_hash
from hope_core.money import Money
from hope_core.pillar import InMemoryPillar, OutboundPackage, PillarPort, RouteReceipt
from hope_core.schemas.opportunity_matrix import DimensionScores, MatrixRow
from hope_core.schemas.proposal_framework import (
    BudgetLedger,
    CapCheck,
    Goal,
    Kpi,
    LineItem,
    LineItemBasis,
    Objective,
    ProposalFramework,
    Scope,
    Totals,
)

from hope_workflow.agents import AgentRegistry
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

Recommendation = Literal["pursue", "consider", "watch", "skip"]


@dataclass
class StubAgents:
    pillar: PillarPort = field(default_factory=InMemoryPillar)
    eligibility_status: Literal["eligible", "needs_review", "ineligible"] = "eligible"
    recommendation: Recommendation = "pursue"
    calls: list[str] = field(default_factory=list)

    async def eligibility(self, req: AgentContext) -> EligibilityResult:
        self.calls.append("eligibility")
        return EligibilityResult(status=self.eligibility_status, reasons=["stub"], effort_hours=60)

    async def alignment(self, req: AgentContext) -> AlignmentAssessment:
        self.calls.append("alignment")
        return AlignmentAssessment(score=82, rationale="stub alignment")

    async def recommend(self, req: RecommendRequest) -> MatrixRow:
        self.calls.append("recommend")
        score = req.alignment.score
        return MatrixRow(
            opportunity_id=req.ctx.opportunity.opportunity_id,
            rank=1,
            composite_score=score,
            eligibility="eligible",
            scores=DimensionScores(
                mission_alignment=score,
                funding_fit=75,
                effort_to_funding=60,
                win_probability=0.3,
                deadline_feasibility=80,
            ),
            recommendation=self.recommendation,
        )

    async def budget(self, req: BudgetRequest) -> BudgetDraft:
        self.calls.append("budget")
        ctx = req.ctx
        personnel = Money.from_decimal("100000")
        indirect = personnel.apply_bps(1000)
        request = personnel + indirect
        ceiling = ctx.opportunity.funding.award_ceiling
        seed = f"{ctx.workflow_id}:{ctx.profile.version}:{'|'.join(ctx.feedback)}"
        draft = ProposalFramework(
            framework_id=uuid5(NAMESPACE_URL, seed),
            opportunity_id=ctx.opportunity.opportunity_id,
            agency_id=ctx.agency_id,
            version=ctx.profile.version,
            status="verified",
            scope=Scope(
                project_title=ctx.opportunity.title,
                program_ids=[p.program_id for p in ctx.profile.programs],
                goals=[
                    Goal(
                        goal_id="g1",
                        statement="Expand program reach",
                        objectives=[
                            Objective(
                                objective_id="o1",
                                smart_statement="Serve 200 additional youth in 12 months",
                                kpis=[Kpi(metric="youth_served", target=200)],
                            )
                        ],
                    )
                ],
            ),
            budget=BudgetLedger(
                ledger_id=f"ledger-{uuid5(NAMESPACE_URL, seed)}",
                engine_version="stub-0",
                line_items=[
                    LineItem(
                        line_id="L1",
                        category="personnel",
                        basis=LineItemBasis(cost_basis_ref="hris:position:PM-02"),
                        amount_minor=personnel.amount_minor,
                    )
                ],
                totals=Totals(
                    direct_minor=personnel.amount_minor,
                    mtdc_base_minor=personnel.amount_minor,
                    indirect_minor=indirect.amount_minor,
                    request_minor=request.amount_minor,
                    cost_share_minor=0,
                    project_total_minor=request.amount_minor,
                ),
                cap_checks=[
                    CapCheck(
                        rule="award_ceiling",
                        limit_minor=ceiling.amount_minor if ceiling else None,
                        actual_minor=request.amount_minor,
                        status="pass",
                    )
                ],
            ),
        )
        framework = draft.model_copy(update={"content_hash": content_hash(draft)})
        drafted_by = str(req.go.details.get("owner", req.go.decided_by))
        return BudgetDraft(framework=framework, drafted_by=drafted_by)

    async def verify(self, req: VerifyRequest) -> VerificationReport:
        self.calls.append(f"verify:{req.subject}")
        return VerificationReport(passed=True)

    async def narrative(self, req: NarrativeRequest) -> NarrativeDraft:
        self.calls.append("narrative")
        framework_hash = req.framework.content_hash or content_hash(req.framework)
        titles = [s.title for s in req.ctx.opportunity.requirements.sections] or [
            "Project Narrative"
        ]
        sections = {t: f"[stub] {t} for {req.framework.scope.project_title}" for t in titles}
        body = {
            "framework_hash": framework_hash,
            "sections": sections,
            "feedback": req.ctx.feedback,
        }
        digest = content_hash(body)
        return NarrativeDraft(
            draft_id=f"draft-{digest[7:19]}",
            framework_hash=framework_hash,
            sections=sections,
            content_hash=digest,
        )

    async def compliance(self, req: ComplianceRequest) -> ComplianceReport:
        self.calls.append("compliance")
        return ComplianceReport(passed=True)

    async def package(self, req: PackageRequest) -> SubmissionPackage:
        self.calls.append("package")
        manifest = content_hash(
            {"framework": req.framework.content_hash, "draft": req.draft.content_hash}
        )
        channel = req.ctx.opportunity.requirements.submission_channel or (
            "grants_gov" if req.ctx.opportunity.source.system == "grants_gov" else "manual"
        )
        return SubmissionPackage(
            manifest_hash=manifest,
            channel=channel,
            payload_ref=f"s3://hope-artifacts/packages/{manifest[7:]}.zip",
            valid=True,
        )

    async def submit(self, req: SubmitRequest) -> RouteReceipt:
        self.calls.append("submit")
        return self.pillar.route_outbound(
            OutboundPackage(
                tenant_id=req.ctx.tenant_id,
                opportunity_id=req.ctx.opportunity.opportunity_id,
                channel=req.package.channel,
                manifest_hash=req.package.manifest_hash,
                authorized_by=req.authorized_by,
                payload_ref=req.package.payload_ref,
            )
        )

    def registry(self) -> AgentRegistry:
        return AgentRegistry(
            eligibility=self.eligibility,
            alignment=self.alignment,
            recommend=self.recommend,
            budget=self.budget,
            verify=self.verify,
            narrative=self.narrative,
            compliance=self.compliance,
            package=self.package,
            submit=self.submit,
        )
