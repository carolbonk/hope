"""Sample cost basis and contexts for tests (reused across budget tests and other services)."""

from __future__ import annotations

from datetime import UTC, datetime

from hope_core.money import Money
from hope_core.schemas.common import Provenance
from hope_core.schemas.proposal_framework import LineItemBasis

from hope_budget.contracts import CostBasisRecord, CostKind
from hope_budget.engine import BudgetContext, DirectCategory, FundingSource, ProposedLine
from hope_budget.resolver import InMemoryCostBasisResolver
from hope_budget.rules import AgencyRates, BudgetRules

CAPTURED = datetime(2026, 7, 1, tzinfo=UTC)


def provenance(source_ref: str = "sample") -> Provenance:
    return Provenance(source="erp_sync", source_ref=source_ref, captured_at=CAPTURED)


def record(
    ref: str, kind: CostKind, rate_minor: int, unit: str | None = None, **extra: object
) -> CostBasisRecord:
    return CostBasisRecord.model_validate(
        {
            "ref": ref,
            "kind": kind,
            "description": ref,
            "unit": unit,
            "unit_rate": Money(amount_minor=rate_minor),
            "provenance": provenance(ref),
            **extra,
        }
    )


def line(
    line_id: str,
    category: DirectCategory,
    ref: str,
    quantity: str = "1",
    effort_bps: int | None = None,
    period: int = 1,
    funding_source: FundingSource = "request",
    **extra: object,
) -> ProposedLine:
    return ProposedLine.model_validate(
        {
            "line_id": line_id,
            "category": category,
            "period": period,
            "basis": LineItemBasis(
                cost_basis_ref=ref, quantity=quantity, effort_pct_bps=effort_bps
            ),
            "funding_source": funding_source,
            **extra,
        }
    )


SAMPLE_RECORDS = [
    record("hris:position:PM-02", "salary", 72_000_00, "year"),
    record("hris:position:CO-01", "salary", 48_500_00, "year"),
    record("erp:travel:mileage-trip", "unit_cost", 412_37, "trip"),
    record("erp:supplies:lab-kit", "unit_cost", 13_33, "kit"),
    record("erp:vendor-quote:Q-118", "equipment", 8_000_00, "each"),
    record("erp:subaward:SA-01", "subaward", 40_000_00, "agreement"),
    record("erp:stipend:youth", "participant_support", 5_000_00, "cohort"),
    record("erp:catering:gala", "unit_cost", 1_200_00, "event", cost_tags=["entertainment"]),
    record("erp:match:volunteer-hours", "unit_cost", 30_00, "hour"),
]


def sample_lines() -> list[ProposedLine]:
    """Golden budget 1 (hand-computed in test_engine_golden.py)."""
    return [
        line("pm", "personnel", "hris:position:PM-02", effort_bps=5000),
        line("coord", "personnel", "hris:position:CO-01", effort_bps=10000),
        line("travel", "travel", "erp:travel:mileage-trip", "3"),
        line("kits", "supplies", "erp:supplies:lab-kit", "2.5"),
        line("robot", "equipment", "erp:vendor-quote:Q-118"),
        line("sub", "contractual", "erp:subaward:SA-01"),
        line("stipends", "other", "erp:stipend:youth"),
    ]


def sample_agency(**overrides: object) -> AgencyRates:
    values: dict[str, object] = {
        "fringe_rate_bps": 2800,
        "indirect_type": "de_minimis",
        "indirect_rate_bps": 1500,
        "indirect_base": "MTDC",
        "provenance": provenance("profile"),
    }
    return AgencyRates.model_validate({**values, **overrides})


def sample_rules(**overrides: object) -> BudgetRules:
    values: dict[str, object] = {
        "award_ceiling": Money(amount_minor=250_000_00),
        "award_floor": Money(amount_minor=50_000_00),
        "indirect_cap_bps": 1000,
        "indirect_base": "MTDC",
        "unallowable_costs": ("entertainment",),
    }
    return BudgetRules.model_validate({**values, **overrides})


def sample_context(records: list[CostBasisRecord] | None = None, **rules: object) -> BudgetContext:
    return BudgetContext(
        resolver=InMemoryCostBasisResolver(records or SAMPLE_RECORDS),
        agency=sample_agency(),
        rules=sample_rules(**rules),
    )
