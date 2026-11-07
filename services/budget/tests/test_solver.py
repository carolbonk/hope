from hope_budget.engine import BudgetEngine
from hope_budget.solver import fit_budget
from hope_budget.testing import line, sample_context, sample_lines
from hope_core.money import Money
from hope_core.schemas.proposal_framework import BudgetLedger, CapCheck


def status(ledger: BudgetLedger, rule: str) -> CapCheck:
    return next(c for c in ledger.cap_checks if c.rule == rule)


def test_within_limits_is_untouched() -> None:
    ctx = sample_context()
    solution = fit_budget(sample_lines(), ctx)
    assert solution.feasible and not solution.adjustments
    assert solution.ledger == BudgetEngine(ctx).compute(sample_lines())


def test_over_ceiling_cuts_non_personnel_first() -> None:
    ctx = sample_context(award_ceiling=Money(amount_minor=150_000_00))
    lines = [*sample_lines(), line("extra-travel", "travel", "erp:travel:mileage-trip", "40")]
    solution = fit_budget(lines, ctx)
    assert solution.feasible
    ledger = solution.ledger
    assert ledger.totals.request_minor <= 150_000_00
    check = status(ledger, "award_ceiling")
    assert check.status == "adjusted" and check.adjustment_note
    efforts = {line.line_id: line.basis.effort_pct_bps for line in solution.lines}
    assert efforts["pm"] == 5000 and efforts["coord"] == 10000
    assert all(a.change != "effort_pct_bps" for a in solution.adjustments)
    # amounts are the engine's, never the solver's
    recomputed = BudgetEngine(ctx).compute(solution.lines)
    assert recomputed.line_items == ledger.line_items and recomputed.totals == ledger.totals


def test_minimal_cut_lands_just_under_ceiling() -> None:
    ctx = sample_context(award_ceiling=Money(amount_minor=175_000_00), award_floor=None)
    lines = [*sample_lines(), line("trips", "travel", "erp:travel:mileage-trip", "10")]
    solution = fit_budget(lines, ctx)
    assert solution.feasible
    assert solution.ledger.totals.request_minor == 174_966_27  # 12 of 13 trips cut
    assert {a.line_id for a in solution.adjustments} == {"travel", "trips"}
    # restoring a single trip breaks the ceiling: the cut is minimal at trip granularity
    bumped = [
        ln.model_copy(update={"basis": ln.basis.model_copy(update={"quantity": "2"})})
        if ln.line_id == "travel"
        else ln
        for ln in solution.lines
    ]
    assert BudgetEngine(ctx).compute(bumped).totals.request_minor > 175_000_00


def test_cuts_effort_only_when_non_personnel_is_exhausted() -> None:
    ctx = sample_context(award_ceiling=Money(amount_minor=100_000_00), award_floor=None)
    solution = fit_budget(sample_lines(), ctx)
    assert solution.feasible
    assert solution.ledger.totals.request_minor <= 100_000_00
    kept = {line.line_id for line in solution.lines}
    assert kept <= {"pm", "coord"}  # every non-personnel line went first
    assert any(a.change == "effort_pct_bps" for a in solution.adjustments)
    for line_ in solution.lines:
        assert (line_.basis.effort_pct_bps or 0) >= 1000  # policy floor


def test_effort_floor_makes_it_infeasible() -> None:
    ctx = sample_context(award_ceiling=Money(amount_minor=10_000_00), award_floor=None)
    solution = fit_budget(sample_lines(), ctx)
    assert not solution.feasible
    assert "award_ceiling" in solution.unresolved
    assert status(solution.ledger, "award_ceiling").status == "fail"


def test_locked_lines_are_kept() -> None:
    ctx = sample_context(award_ceiling=Money(amount_minor=150_000_00))
    lines = [
        ln.model_copy(update={"locked": True}) if ln.line_id == "sub" else ln
        for ln in sample_lines()
    ]
    solution = fit_budget(lines, ctx)
    assert solution.feasible
    assert "sub" in {ln.line_id for ln in solution.lines}


def test_unallowable_lines_are_removed() -> None:
    ctx = sample_context()
    lines = [*sample_lines(), line("gala", "other", "erp:catering:gala")]
    solution = fit_budget(lines, ctx)
    assert solution.feasible
    assert [a.line_id for a in solution.adjustments] == ["gala"]
    assert status(solution.ledger, "unallowable_cost").status == "adjusted"


def test_cost_share_shortfall_reduces_request() -> None:
    lines = [
        *sample_lines(),
        line(
            "match",
            "other",
            "erp:match:volunteer-hours",
            "500",
            funding_source="cost_share_in_kind",
        ),
    ]
    ctx = sample_context(cost_share_ratio_bps=1000)  # need 10% of request = ~17.6k, have 15k
    assert status(BudgetEngine(ctx).compute(lines), "cost_share_ratio").status == "fail"
    solution = fit_budget(lines, ctx)
    assert solution.feasible
    share = status(solution.ledger, "cost_share_ratio")
    assert share.status == "adjusted"
    assert (share.actual_minor or 0) >= (share.limit_minor or 0)


def test_floor_failure_is_not_fixable() -> None:
    ctx = sample_context(award_floor=Money(amount_minor=200_000_00))
    solution = fit_budget(sample_lines(), ctx)
    assert not solution.feasible and solution.unresolved == ["award_floor"]
