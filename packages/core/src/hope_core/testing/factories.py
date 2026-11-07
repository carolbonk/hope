"""Valid sample contracts, reused by every service's tests (no copy-pasted fixtures)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from hope_core.money import Money
from hope_core.schemas.agency_profile import (
    AgencyProfile,
    ApprovalRule,
    Financials,
    IndirectRate,
    Legal,
    Mission,
    Program,
)
from hope_core.schemas.common import Evidence
from hope_core.schemas.grant_opportunity import (
    Deadlines,
    Eligibility,
    ExtractedDeadline,
    Funder,
    Funding,
    GrantOpportunity,
    IndirectCostPolicy,
    ParseQuality,
    Source,
)
from hope_core.schemas.hitl import Gate

TENANT_A = UUID("00000000-0000-4000-8000-00000000000a")
TENANT_B = UUID("00000000-0000-4000-8000-00000000000b")


def evidence(page: int = 1, quote: str = "sample") -> Evidence:
    return Evidence(artifact_id="artifact-sample", page=page, quote=quote)


def agency_profile(tenant_id: UUID = TENANT_A, **overrides: object) -> AgencyProfile:
    base = AgencyProfile(
        agency_id=uuid4(),
        tenant_id=tenant_id,
        version=1,
        legal=Legal(
            legal_name="Riverbend Youth Alliance",
            ein="12-3456789",
            tax_status="501c3_public_charity",
        ),
        mission=Mission(
            mission_statement="Mentoring and STEM education for under-served youth in Ohio.",
            focus_areas=["youth development", "STEM education"],
        ),
        financials=Financials(
            fiscal_year_end="06-30",
            annual_operating_budget=Money.from_decimal("1850000"),
            budget_band="1m-5m",
            indirect_rate=IndirectRate(type="de_minimis", rate_bps=1500, base="MTDC"),
            fringe_rate_bps=2800,
        ),
        programs=[
            Program(
                program_id="prog-stem",
                name="After-school STEM Lab",
                description="Weekly robotics and coding sessions for grades 6-9.",
                geography=["US-OH"],
            )
        ],
        approval_hierarchy=[
            ApprovalRule(gate=Gate.GO_NO_GO, approver_roles=["development_director"]),
            ApprovalRule(gate=Gate.BUDGET_SIGNOFF, approver_roles=["finance_director"]),
        ],
    )
    return base.model_copy(update=overrides)


def grant_opportunity(**overrides: object) -> GrantOpportunity:
    due = datetime.now(UTC) + timedelta(days=45)
    base = GrantOpportunity(
        opportunity_id=uuid4(),
        source=Source(system="grants_gov", source_id="HHS-2027-ACF-YD-0001"),
        title="Youth STEM Mentoring Demonstration Grants",
        funder=Funder(
            name="Administration for Children and Families", type="federal", aln=["93.243"]
        ),
        deadlines=Deadlines(
            application_due=ExtractedDeadline(
                value=due, timezone="America/New_York", confidence=0.97, evidence=[evidence(3)]
            )
        ),
        funding=Funding(
            award_ceiling=Money.from_decimal("250000"),
            award_floor=Money.from_decimal("50000"),
            indirect_cost_policy=IndirectCostPolicy(allowed=True, cap_bps=1000, base="MTDC"),
        ),
        eligibility=Eligibility(
            applicant_types=["501c3_public_charity"], geographic_restrictions=["US"]
        ),
        parse_quality=ParseQuality(overall_confidence=0.95, pipeline_path=["native_text"]),
    )
    return base.model_copy(update=overrides)
