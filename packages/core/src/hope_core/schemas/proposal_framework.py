from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from hope_core.money import Bps
from hope_core.schemas.common import Contract
from hope_core.schemas.hitl import Gate

BudgetCategory = Literal[
    "personnel",
    "fringe",
    "travel",
    "equipment",
    "supplies",
    "contractual",
    "construction",
    "other",
    "indirect",
]
CapRule = Literal[
    "award_ceiling",
    "award_floor",
    "indirect_cap",
    "cost_share_ratio",
    "category_cap",
    "unallowable_cost",
    "period_cap",
]


class Kpi(Contract):
    metric: str
    baseline_ref: str | None = Field(None, description="profile metric_id; never a free number")
    target: float | None = None
    unit: str | None = None


class Activity(Contract):
    activity_id: str
    description: str
    start_month: int | None = None
    end_month: int | None = None
    responsible_role: str | None = None


class Objective(Contract):
    objective_id: str
    smart_statement: str
    kpis: list[Kpi] = Field(min_length=1)
    activities: list[Activity] = []


class Goal(Contract):
    goal_id: str
    statement: str
    objectives: list[Objective] = Field(min_length=1)


class LogicModel(Contract):
    inputs: list[str] = []
    activities: list[str] = []
    outputs: list[str] = []
    outcomes_short: list[str] = []
    outcomes_long: list[str] = []


class RequirementCoverage(Contract):
    section_id: str
    covered_by: list[str] = []
    status: Literal["covered", "partial", "missing"]


class Scope(Contract):
    project_title: str
    problem_statement_ref: str | None = None
    program_ids: list[str] = []
    goals: list[Goal] = Field(min_length=1)
    logic_model: LogicModel | None = None
    requirement_coverage: list[RequirementCoverage] = []


class LineItemBasis(Contract):
    """What an LLM may propose. Amounts are never part of the basis."""

    cost_basis_ref: str = Field(description="e.g. hris:position:PM-02 or erp:vendor-quote:Q-118")
    quantity: str = Field("1", description="decimal string")
    unit: str | None = None
    unit_rate_minor: int | None = Field(None, description="resolved by the engine from the ref")
    effort_pct_bps: Bps | None = None


class LineItem(Contract):
    line_id: str
    category: BudgetCategory
    description: str | None = None
    period: int = Field(1, ge=1)
    basis: LineItemBasis
    amount_minor: int
    funding_source: Literal["request", "cost_share_cash", "cost_share_in_kind"] = "request"
    justification: str | None = None
    allowability: Literal["allowable", "unallowable", "needs_review"] = "allowable"


class Totals(Contract):
    direct_minor: int
    mtdc_base_minor: int
    indirect_minor: int
    request_minor: int
    cost_share_minor: int
    project_total_minor: int


class CapCheck(Contract):
    rule: CapRule
    limit_minor: int | None = None
    actual_minor: int | None = None
    status: Literal["pass", "fail", "adjusted"]
    adjustment_note: str | None = None


class BudgetLedger(Contract):
    ledger_id: str
    computed_by: Literal["budget-engine"] = Field(
        "budget-engine", description="ledgers from any other producer are rejected"
    )
    engine_version: str
    currency: str = "USD"
    periods: int = 1
    line_items: list[LineItem]
    totals: Totals
    cap_checks: list[CapCheck]
    sf424a_mapping: dict[str, int] = {}


class Approval(Contract):
    gate: Gate
    approver_user_id: str
    approved_hash: str
    at: datetime
    esign_envelope_id: str | None = None


class ProposalFramework(Contract):
    framework_id: UUID
    opportunity_id: UUID
    agency_id: UUID
    version: int = Field(ge=1)
    status: Literal["draft", "verified", "approved_locked", "superseded"]
    content_hash: str | None = Field(None, description="sha256 of canonical JSON")
    scope: Scope
    budget: BudgetLedger
    approvals: list[Approval] = []
    extra: dict[str, Any] = {}
