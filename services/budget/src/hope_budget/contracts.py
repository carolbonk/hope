"""Budget models other services will need. Candidates for promotion to `hope_core.schemas`."""

from __future__ import annotations

from typing import Literal

from hope_core.money import Bps, Money
from hope_core.schemas.common import Contract, Provenance
from pydantic import Field

CostKind = Literal[
    "salary",
    "unit_cost",
    "vendor_quote",
    "subaward",
    "equipment",
    "participant_support",
    "rental",
    "tuition_remission",
    "scholarship",
    "patient_care",
]


class CostBasisRecord(Contract):
    """A rate from HRIS/ERP/profile. The only place unit rates come from."""

    ref: str = Field(description="e.g. hris:position:PM-02")
    kind: CostKind
    description: str
    unit: str | None = Field(None, description="e.g. year, trip, month, each")
    unit_rate: Money = Field(description="rate per unit; salaries are per budget period")
    fringe_rate_bps: Bps | None = Field(None, description="position-specific fringe override")
    subaward_id: str | None = Field(None, description="defaults to ref for kind=subaward")
    cost_tags: list[str] = Field(default=[], description="matched against unallowable costs")
    provenance: Provenance | None = Field(None, description="required; records without it fail")


NumericKind = Literal["money", "percent", "number", "identifier"]


class NumericMatch(Contract):
    token: str
    kind: NumericKind
    source_path: str


class NumericMismatch(Contract):
    token: str
    kind: NumericKind
    offset: int
    reason: str


class PolicyViolation(Contract):
    rule: Literal["raw_currency_figure", "raw_percent_figure", "unknown_placeholder"]
    excerpt: str
    offset: int


class NumericReconciliationReport(Contract):
    """Numeric part of the A11 `VerificationReport` (blueprint 2.2 A11, 8.1)."""

    passed: bool
    numeric_mismatches: list[NumericMismatch] = []
    policy_violations: list[PolicyViolation] = []
    matched: list[NumericMatch] = []
