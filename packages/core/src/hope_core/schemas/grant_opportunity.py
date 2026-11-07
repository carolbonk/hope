from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from hope_core.money import Bps, Money
from hope_core.schemas.common import Contract, Evidence, ExtractionMeta

SourceSystem = Literal[
    "grants_gov", "sam_gov", "candid", "funder_site", "state_portal", "email", "upload"
]
FunderType = Literal[
    "federal",
    "state",
    "local",
    "private_foundation",
    "community_foundation",
    "corporate",
    "other",
]
PipelinePath = Literal["native_text", "layout_model", "ocr", "vision_llm", "human"]

CRITICAL_FIELDS: tuple[str, ...] = ("deadlines.application_due", "funding.award_ceiling")
"""Fields whose absence triggers the missing-field policy (blueprint 8.5)."""


class Source(Contract):
    system: SourceSystem
    source_id: str = Field(description="e.g. Grants.gov opportunity number")
    url: str | None = None
    artifact_ids: list[str] = []
    amendment_seq: int = 0


class Funder(Contract):
    funder_id: str | None = None
    name: str
    type: FunderType
    aln: list[str] = []
    contact_email: str | None = None


class ExtractedStrings(ExtractionMeta):
    value: list[str]


class ExtractedDeadline(ExtractionMeta):
    value: datetime
    timezone: str = Field(description="IANA tz, e.g. America/New_York")


class Deadlines(Contract):
    application_due: ExtractedDeadline | None = None
    loi_due: ExtractedDeadline | None = None
    questions_due: ExtractedDeadline | None = None
    rolling: bool = False
    anticipated_award_date: date | None = None
    project_period_months: int | None = None


class CostShare(Contract):
    required: bool
    ratio_bps: Bps | None = None
    in_kind_allowed: bool | None = None


class IndirectCostPolicy(Contract):
    allowed: bool
    cap_bps: Bps | None = None
    base: Literal["MTDC", "TDC", "salaries_wages", "unspecified"] = "unspecified"


class Funding(Contract):
    award_ceiling: Money | None = None
    award_floor: Money | None = None
    total_program_funding: Money | None = None
    expected_awards: int | None = None
    cost_share: CostShare | None = None
    indirect_cost_policy: IndirectCostPolicy | None = None
    unallowable_costs: list[str] = []
    evidence: list[Evidence] = []


class EligibilityClause(Contract):
    text: str
    compiled_rule: dict[str, Any] | None = Field(None, description="JSON Logic, once approved")
    rule_status: Literal["draft", "approved", "needs_review"] = "draft"
    evidence: list[Evidence] = Field(min_length=1)


class Eligibility(Contract):
    applicant_types: list[str] = []
    geographic_restrictions: list[str] = []
    budget_band_restrictions: list[str] = []
    required_registrations: list[Literal["sam", "uei", "grants_gov", "state_charity", "other"]] = []
    clauses: list[EligibilityClause] = []


class RequirementSection(Contract):
    section_id: str
    title: str
    instructions: str | None = None
    page_limit: float | None = None
    word_limit: int | None = None
    scoring_weight_points: float | None = None
    evaluation_criteria: list[str] = []


class Formatting(Contract):
    font_min_pt: float | None = None
    spacing: str | None = None
    margins_in: float | None = None
    file_types: list[str] = []


class Requirements(Contract):
    sections: list[RequirementSection] = []
    attachments: list[str] = []
    forms: list[str] = Field(default=[], description="e.g. SF-424, SF-424A, SF-LLL")
    formatting: Formatting | None = None
    submission_channel: Literal["grants_gov", "funder_portal", "email", "mail", "other"] | None = (
        None
    )


class ParseQuality(Contract):
    overall_confidence: float = Field(ge=0, le=1)
    missing_critical_fields: list[str] = []
    warnings: list[str] = []
    injection_suspected: bool = False
    pipeline_path: list[PipelinePath] = []


class GrantOpportunity(Contract):
    opportunity_id: UUID
    source: Source
    title: str
    funder: Funder
    summary: str | None = None
    funding_priorities: ExtractedStrings | None = None
    deadlines: Deadlines
    funding: Funding
    eligibility: Eligibility
    requirements: Requirements = Requirements()
    parse_quality: ParseQuality
