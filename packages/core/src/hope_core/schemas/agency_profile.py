from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from hope_core.money import Bps, Money
from hope_core.schemas.common import Contract, Provenance
from hope_core.schemas.hitl import Gate

TaxStatus = Literal[
    "501c3_public_charity",
    "501c3_private_foundation",
    "501c4",
    "501c6",
    "fiscally_sponsored",
    "government",
    "tribal",
    "other",
]
BudgetBand = Literal["<250k", "250k-1m", "1m-5m", "5m-25m", ">25m"]

PROTECTED_PROFILE_PATHS: tuple[str, ...] = (
    "legal",
    "financials",
    "approval_hierarchy",
)
"""Top-level profile sections whose changes require HITL-0 approval."""


class SamRegistration(Contract):
    status: Literal["active", "expired", "pending", "none"]
    expires_on: date | None = None
    exclusions_flag: bool = False


class Legal(Contract):
    legal_name: str
    dba: list[str] = []
    ein: str = Field(pattern=r"^[0-9]{2}-[0-9]{7}$")
    uei: str | None = Field(None, pattern=r"^[A-Z0-9]{12}$")
    sam_registration: SamRegistration | None = None
    tax_status: TaxStatus
    fiscal_sponsor_id: str | None = None
    state_of_incorporation: str | None = None
    provenance: Provenance | None = None


class Mission(Contract):
    mission_statement: str = Field(max_length=2000)
    vision_statement: str | None = Field(None, max_length=2000)
    theory_of_change: str | None = None
    focus_areas: list[str] = []
    ntee_codes: list[str] = []


class IndirectRate(Contract):
    type: Literal["negotiated_nicra", "de_minimis", "none"]
    rate_bps: Bps | None = None
    base: Literal["MTDC", "TDC", "salaries_wages"] | None = None
    agreement_expires_on: date | None = None


class LastAudit(Contract):
    type: Literal["single_audit", "financial_audit", "review", "none"]
    fiscal_year: int | None = None
    findings: bool | None = None
    artifact_id: str | None = None


class Financials(Contract):
    fiscal_year_end: str = Field(pattern=r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
    annual_operating_budget: Money
    budget_band: BudgetBand | None = None
    indirect_rate: IndirectRate | None = None
    fringe_rate_bps: Bps | None = None
    last_audit: LastAudit | None = None
    provenance: Provenance | None = None


class Demographic(Contract):
    population: str
    age_range: str | None = None
    annual_served: int | None = None


class Outcome(Contract):
    metric_id: str
    label: str
    value: float
    unit: str | None = None
    period: str
    provenance: Provenance | None = None


class Program(Contract):
    program_id: str
    name: str
    description: str
    status: Literal["active", "pilot", "planned", "sunset"] = "active"
    annual_cost: Money | None = None
    geography: list[str] = Field(default=[], description="FIPS or ISO-3166-2 codes")
    target_demographics: list[Demographic] = []
    outcomes: list[Outcome] = []


class GrantHistoryItem(Contract):
    funder_id: str
    program_name: str | None = None
    aln: str | None = Field(None, description="Assistance Listing Number, e.g. 93.243")
    amount: Money | None = None
    outcome: Literal["awarded", "declined", "withdrawn", "pending"]
    period_start: date | None = None
    period_end: date | None = None
    reviewer_feedback_artifact_id: str | None = None


class Capacity(Contract):
    grant_writer_fte: float | None = None
    monthly_hours_available: int | None = None
    max_concurrent_applications: int | None = None
    cost_share_capacity: Money | None = None


class ApprovalRule(Contract):
    gate: Gate
    condition: dict[str, Any] | None = Field(None, description="JSON Logic over the gate payload")
    approver_roles: list[str] = Field(min_length=1)
    min_approvals: int = 1
    sla_hours: int | None = None
    escalate_to_role: str | None = None


class ComplianceItem(Contract):
    item: Literal[
        "sam_renewal",
        "form_990",
        "single_audit",
        "state_charity_registration",
        "insurance_renewal",
        "nicra_renewal",
        "board_meeting",
        "custom",
    ]
    due_on: date
    owner_user_id: str | None = None


class DataGovernance(Contract):
    allow_cross_tenant_learning: bool = False
    allow_style_finetune: bool = False
    data_residency: Literal["us", "eu", "ca"] = "us"
    retention_days: int | None = None


class AgencyProfile(Contract):
    agency_id: UUID
    tenant_id: UUID
    version: int = Field(ge=1)
    valid_from: datetime | None = None
    legal: Legal
    mission: Mission
    financials: Financials
    programs: list[Program] = []
    grant_history: list[GrantHistoryItem] = []
    capacity: Capacity | None = None
    approval_hierarchy: list[ApprovalRule] = Field(min_length=1)
    compliance_calendar: list[ComplianceItem] = []
    data_governance: DataGovernance = DataGovernance()
