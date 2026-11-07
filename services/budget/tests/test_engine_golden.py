"""Hand-computed golden budgets. Every expected number below was worked out by hand."""

from dataclasses import replace

import pytest
from hope_budget.engine import ENGINE_VERSION, BudgetEngine, BudgetInputError, is_sealed
from hope_budget.rules import AgencyRates, BudgetRules
from hope_budget.testing import (
    SAMPLE_RECORDS,
    line,
    record,
    sample_agency,
    sample_context,
    sample_lines,
)
from hope_core.money import Money
from hope_core.schemas.proposal_framework import BudgetLedger


def amounts(ledger: BudgetLedger) -> dict[str, int]:
    return {i.line_id: i.amount_minor for i in ledger.line_items}


def checks(ledger: BudgetLedger) -> dict[str, str]:
    return {c.rule: c.status for c in ledger.cap_checks}


def test_golden_single_period_mtdc() -> None:
    ledger = BudgetEngine(sample_context()).compute(sample_lines())
    assert ledger.computed_by == "budget-engine"
    assert ledger.engine_version == ENGINE_VERSION
    assert amounts(ledger) == {
        "pm": 36_000_00,  # 72,000 x 50%
        "pm-fringe": 10_080_00,  # 28%
        "coord": 48_500_00,
        "coord-fringe": 13_580_00,
        "travel": 1_237_11,  # 412.37 x 3
        "kits": 33_33,  # 13.33 x 2.5 = 33.325 -> half-up
        "robot": 8_000_00,  # equipment: excluded from MTDC
        "sub": 40_000_00,  # only the first 25,000 is in MTDC
        "stipends": 5_000_00,  # participant support: excluded from MTDC
        "indirect-p1": 13_443_04,  # 10% (funder cap < 15% de minimis) of 134,430.44
    }
    t = ledger.totals
    assert t.direct_minor == 162_430_44
    assert t.mtdc_base_minor == 134_430_44  # 108,160 + 1,237.11 + 33.33 + 25,000
    assert t.indirect_minor == 13_443_04
    assert t.request_minor == 175_873_48
    assert t.cost_share_minor == 0
    assert t.project_total_minor == 175_873_48
    assert checks(ledger) == {
        "award_ceiling": "pass",
        "award_floor": "pass",
        "indirect_cap": "pass",
        "unallowable_cost": "pass",
    }
    indirect = ledger.line_items[-1].basis
    assert (indirect.cost_basis_ref, indirect.quantity) == (
        "opportunity:funding.indirect_cost_policy.cap_bps",
        "0.1",
    )
    assert ledger.sf424a_mapping == {
        "5e_federal": 175_873_48,
        "5f_non_federal": 0,
        "5g_total": 175_873_48,
        "6a_personnel": 84_500_00,
        "6b_fringe_benefits": 23_660_00,
        "6c_travel": 1_237_11,
        "6d_equipment": 8_000_00,
        "6e_supplies": 33_33,
        "6f_contractual": 40_000_00,
        "6g_construction": 0,
        "6h_other": 5_000_00,
        "6i_total_direct_charges": 162_430_44,
        "6j_indirect_charges": 13_443_04,
        "6k_totals": 175_873_48,
    }
    assert is_sealed(ledger)
    assert ledger.ledger_id.startswith("sha256:")


def test_golden_multi_period_subaward_rule_and_cost_share() -> None:
    records = [
        record("hris:position:ED-01", "salary", 60_000_00, "year", fringe_rate_bps=3000),
        record("erp:subaward:SA-01", "subaward", 15_000_00),
        record("erp:subaward:SA-02", "subaward", 30_000_00),
        record("erp:match:board-cash", "unit_cost", 25_000_00),
    ]
    ctx = sample_context(
        records,
        award_ceiling=Money(amount_minor=300_000_00),
        indirect_cap_bps=None,
        cost_share_ratio_bps=1000,
    )
    ctx = replace(
        ctx, agency=sample_agency(indirect_type="negotiated_nicra", indirect_rate_bps=3200)
    )
    lines = [
        line("ed-y1", "personnel", "hris:position:ED-01", effort_bps=10000, period=1),
        line("sa1-y1", "contractual", "erp:subaward:SA-01", period=1),
        line("sa2-y1", "contractual", "erp:subaward:SA-02", period=1),
        line("ed-y2", "personnel", "hris:position:ED-01", effort_bps=5000, period=2),
        line("sa1-y2", "contractual", "erp:subaward:SA-01", period=2),
        line("match", "other", "erp:match:board-cash", funding_source="cost_share_cash"),
    ]
    ledger = BudgetEngine(ctx).compute(lines)
    a = amounts(ledger)
    # Period 1 base: 60,000 + 18,000 + 15,000 (SA-01) + 25,000 (first 25k of SA-02) = 118,000
    # Period 2 base: 30,000 + 9,000 + 10,000 (SA-01 has 10,000 left under its 25k) = 49,000
    assert a["indirect-p1"] == 37_760_00  # 32% NICRA, no funder cap
    assert a["indirect-p2"] == 15_680_00
    t = ledger.totals
    assert t.mtdc_base_minor == 167_000_00
    assert t.direct_minor == 202_000_00  # 177,000 requested + 25,000 match
    assert t.request_minor == 230_440_00
    assert t.cost_share_minor == 25_000_00
    assert t.project_total_minor == 255_440_00
    share = next(c for c in ledger.cap_checks if c.rule == "cost_share_ratio")
    assert (share.limit_minor, share.actual_minor, share.status) == (23_044_00, 25_000_00, "pass")
    assert ledger.periods == 2


def test_subaward_threshold_is_per_subaward_not_per_line() -> None:
    records = [record("erp:subaward:A", "subaward", 20_000_00, subaward_id="SUB-A")]
    records.append(record("erp:subaward:A-amend", "subaward", 20_000_00, subaward_id="SUB-A"))
    ctx = sample_context(records, indirect_cap_bps=None, award_floor=None)
    lines = [
        line("a1", "contractual", "erp:subaward:A"),
        line("a2", "contractual", "erp:subaward:A-amend"),
    ]
    ledger = BudgetEngine(ctx).compute(lines)
    assert ledger.totals.mtdc_base_minor == 25_000_00
    assert ledger.totals.indirect_minor == 3_750_00  # 15% de minimis


@pytest.mark.parametrize(
    ("base", "expected_base"),
    [("TDC", 162_430_44), ("salaries_wages", 84_500_00), ("MTDC", 134_430_44)],
)
def test_indirect_base_types(base: str, expected_base: int) -> None:
    ledger = BudgetEngine(sample_context(indirect_base=base)).compute(sample_lines())
    assert ledger.totals.mtdc_base_minor == expected_base


def test_indirect_not_allowed_and_no_agency_rate() -> None:
    ctx = sample_context(indirect_allowed=False)
    assert BudgetEngine(ctx).compute(sample_lines()).totals.indirect_minor == 0
    ctx = replace(ctx, agency=sample_agency(indirect_type="none"))
    assert BudgetEngine(ctx).compute(sample_lines()).totals.indirect_minor == 0


def test_de_minimis_is_capped_at_15_percent() -> None:
    assert sample_agency(indirect_rate_bps=2500).indirect_bps() == 1500
    assert sample_agency(indirect_rate_bps=None).indirect_bps() == 1500


def test_unallowable_cost_fails_check() -> None:
    lines = [*sample_lines(), line("gala", "other", "erp:catering:gala")]
    ledger = BudgetEngine(sample_context()).compute(lines)
    unallowable = next(c for c in ledger.cap_checks if c.rule == "unallowable_cost")
    assert (unallowable.actual_minor, unallowable.status) == (1_200_00, "fail")
    assert next(i for i in ledger.line_items if i.line_id == "gala").allowability == "unallowable"


def test_rejects_unresolvable_ref_and_missing_provenance() -> None:
    bare = record("hris:position:X-9", "salary", 1_00).model_copy(update={"provenance": None})
    ctx = sample_context([*SAMPLE_RECORDS, bare])
    lines = [
        line("ghost", "travel", "erp:travel:nowhere"),
        line("x9", "personnel", "hris:position:X-9", effort_bps=100),
    ]
    with pytest.raises(BudgetInputError) as err:
        BudgetEngine(ctx).compute(lines)
    assert any("does not resolve" in e for e in err.value.errors)
    assert any("has no provenance" in e for e in err.value.errors)


def test_rejects_agency_rates_without_provenance_and_proposed_rates() -> None:
    ctx = sample_context()
    ctx = replace(ctx, agency=sample_agency(provenance=None))
    with pytest.raises(BudgetInputError, match="agency rates have no provenance"):
        BudgetEngine(ctx).compute(sample_lines())
    sneaky = line("pm", "personnel", "hris:position:PM-02", effort_bps=5000)
    sneaky = sneaky.model_copy(
        update={"basis": sneaky.basis.model_copy(update={"unit_rate_minor": 1})}
    )
    with pytest.raises(BudgetInputError, match="must come from the cost basis record"):
        BudgetEngine(sample_context()).compute([sneaky])


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        (line("p", "personnel", "hris:position:PM-02"), "needs effort_pct_bps"),
        (line("p", "travel", "hris:position:PM-02"), "does not fit salary"),
        (line("t", "travel", "erp:travel:mileage-trip", effort_bps=10), "only valid on personnel"),
        (line("t", "travel", "erp:travel:mileage-trip", "-1"), "is not a decimal"),
        (line("s", "other", "erp:subaward:SA-01"), "subawards belong in contractual"),
    ],
)
def test_rejects_bad_shapes(bad, message) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(BudgetInputError, match=message):
        BudgetEngine(sample_context()).compute([bad])


def test_rules_and_rates_from_contracts() -> None:
    from hope_core.testing.factories import agency_profile, grant_opportunity

    rules = BudgetRules.from_funding(grant_opportunity().funding)
    assert (rules.indirect_cap_bps, rules.indirect_base, rules.currency) == (1000, "MTDC", "USD")
    rates = AgencyRates.from_profile(agency_profile())
    assert (rates.fringe_rate_bps, rates.indirect_bps(), rates.provenance) == (2800, 1500, None)


def test_currency_mismatch_rejected() -> None:
    euro = record("erp:eu", "unit_cost", 100).model_copy(
        update={"unit_rate": Money(amount_minor=100, currency="EUR")}
    )
    ctx = sample_context([euro])
    with pytest.raises(BudgetInputError, match="is EUR"):
        BudgetEngine(ctx).compute([line("e", "supplies", "erp:eu")])
