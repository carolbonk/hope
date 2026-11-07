"""Property tests: the engine's arithmetic invariants hold for any well-formed proposal."""

from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal

from hope_budget.contracts import CostBasisRecord
from hope_budget.engine import BudgetEngine, ProposedLine
from hope_budget.resolver import InMemoryCostBasisResolver
from hope_budget.solver import fit_budget
from hope_budget.testing import line, record, sample_agency, sample_context
from hope_core.money import Money
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

rates = st.integers(min_value=1, max_value=20_000_000)
quantities = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("50"), places=2)
efforts = st.integers(min_value=100, max_value=10_000)
caps = st.integers(min_value=0, max_value=5_000)
NON_PERSONNEL = ("travel", "supplies", "other")

PROPS = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@st.composite
def proposals(draw: st.DrawFn) -> tuple[list[CostBasisRecord], list[ProposedLine]]:
    records: list[CostBasisRecord] = []
    lines: list[ProposedLine] = []
    periods = draw(st.integers(min_value=1, max_value=3))
    for i in range(draw(st.integers(min_value=0, max_value=3))):
        ref = f"hris:position:P{i}"
        records.append(record(ref, "salary", draw(rates)))
        lines.append(
            line(
                f"p{i}",
                "personnel",
                ref,
                effort_bps=draw(efforts),
                period=draw(st.integers(1, periods)),
            )
        )
    for i in range(draw(st.integers(min_value=1, max_value=5))):
        ref = f"erp:item:{i}"
        records.append(record(ref, "unit_cost", draw(rates)))
        lines.append(
            line(
                f"n{i}",
                draw(st.sampled_from(NON_PERSONNEL)),
                ref,
                str(draw(quantities)),
                period=draw(st.integers(1, periods)),
            )
        )
    if draw(st.booleans()):
        records.append(record("erp:quote:eq", "equipment", draw(rates)))
        lines.append(line("eq", "equipment", "erp:quote:eq"))
    for i in range(draw(st.integers(min_value=0, max_value=2))):
        ref = f"erp:subaward:{i}"
        records.append(record(ref, "subaward", draw(rates)))
        for period in range(1, periods + 1):
            lines.append(line(f"s{i}-{period}", "contractual", ref, period=period))
    if draw(st.booleans()):
        records.append(record("erp:match", "unit_cost", draw(rates)))
        lines.append(line("match", "other", "erp:match", funding_source="cost_share_cash"))
    return records, lines


def ctx_for(records: list[CostBasisRecord], **rules: object):  # type: ignore[no-untyped-def]
    ctx = sample_context(records, **{"award_ceiling": None, "award_floor": None, **rules})
    return replace(ctx, resolver=InMemoryCostBasisResolver(records))


def half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


@PROPS
@given(proposals(), caps)
def test_sum_invariants(proposal, cap: int) -> None:  # type: ignore[no-untyped-def]
    records, lines = proposal
    ledger = BudgetEngine(ctx_for(records, indirect_cap_bps=cap)).compute(lines)
    items, t = ledger.line_items, ledger.totals
    direct = sum(i.amount_minor for i in items if i.category != "indirect")
    indirect = sum(i.amount_minor for i in items if i.category == "indirect")
    share = sum(i.amount_minor for i in items if i.funding_source != "request")
    assert (t.direct_minor, t.indirect_minor) == (direct, indirect)
    assert t.cost_share_minor == share
    assert t.request_minor + t.cost_share_minor == t.project_total_minor == direct + indirect
    sf = ledger.sf424a_mapping
    object_classes = [v for k, v in sf.items() if k[:2] == "6" + k[1] and k[1] in "abcdefgh"]
    assert sum(object_classes) == sf["6i_total_direct_charges"] == t.direct_minor
    assert sf["6k_totals"] == sf["5g_total"] == t.project_total_minor
    assert 0 <= t.mtdc_base_minor <= t.direct_minor


@PROPS
@given(proposals())
def test_no_rounding_drift(proposal) -> None:  # type: ignore[no-untyped-def]
    records, lines = proposal
    by_ref = {r.ref: r for r in records}
    ledger = BudgetEngine(ctx_for(records)).compute(lines)
    amounts = {i.line_id: i.amount_minor for i in ledger.line_items}
    for ln in lines:
        rate = Decimal(by_ref[ln.basis.cost_basis_ref].unit_rate.amount_minor)
        factor = Decimal(ln.basis.quantity)
        if ln.basis.effort_pct_bps is not None:
            factor *= Decimal(ln.basis.effort_pct_bps) / 10_000
        expected = half_up(rate * factor)
        assert amounts[ln.line_id] == expected
        if ln.category == "personnel":
            assert amounts[f"{ln.line_id}-fringe"] == half_up(Decimal(expected) * Decimal("0.28"))


@PROPS
@given(proposals(), caps)
def test_indirect_never_above_cap(proposal, cap: int) -> None:  # type: ignore[no-untyped-def]
    records, lines = proposal
    ledger = BudgetEngine(ctx_for(records, indirect_cap_bps=cap)).compute(lines)
    periods = [i for i in ledger.line_items if i.category == "indirect"]
    rate = min(cap, 1500)
    for item in periods:
        assert Decimal(item.basis.quantity) * 10_000 <= rate
    assert (
        ledger.totals.indirect_minor * 10_000
        <= ledger.totals.mtdc_base_minor * rate + 5_000 * len(periods)
    )
    check = next(c for c in ledger.cap_checks if c.rule == "indirect_cap")
    assert check.status == "pass"


@PROPS
@given(proposals(), caps, caps)
def test_cap_monotonicity(proposal, a: int, b: int) -> None:  # type: ignore[no-untyped-def]
    records, lines = proposal
    low, high = sorted((a, b))
    lo = BudgetEngine(ctx_for(records, indirect_cap_bps=low)).compute(lines)
    hi = BudgetEngine(ctx_for(records, indirect_cap_bps=high)).compute(lines)
    assert lo.totals.indirect_minor <= hi.totals.indirect_minor
    assert lo.totals.direct_minor == hi.totals.direct_minor


@PROPS
@given(proposals())
def test_mtdc_subaward_threshold(proposal) -> None:  # type: ignore[no-untyped-def]
    records, lines = proposal
    ctx = ctx_for(records, indirect_base="TDC")
    tdc = BudgetEngine(ctx).compute(lines).totals.mtdc_base_minor
    mtdc = BudgetEngine(replace(ctx, rules=ctx.rules.model_copy(update={"indirect_base": "MTDC"})))
    ledger = mtdc.compute(lines)
    excluded = sum(i.amount_minor for i in ledger.line_items if i.category == "equipment")
    sub_total = sum(i.amount_minor for i in ledger.line_items if i.line_id.startswith("s"))
    by_sub: dict[str, int] = {}
    for i in ledger.line_items:
        if i.line_id.startswith("s"):
            key = i.basis.cost_basis_ref
            by_sub[key] = by_sub.get(key, 0) + i.amount_minor
    sub_in_base = sum(min(v, 25_000_00) for v in by_sub.values())
    # cost-share lines carry no indirect, so they are outside every base
    assert ledger.totals.mtdc_base_minor == tdc - excluded - sub_total + sub_in_base


@PROPS
@given(proposals())
def test_hash_is_deterministic(proposal) -> None:  # type: ignore[no-untyped-def]
    records, lines = proposal
    a = BudgetEngine(ctx_for(records)).compute(lines)
    b = BudgetEngine(ctx_for(list(reversed(records)))).compute(lines)
    assert a.ledger_id == b.ledger_id


SOLVER = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@SOLVER
@given(proposals(), st.integers(min_value=1, max_value=99))
def test_solver_fits_or_reports(proposal, pct: int) -> None:  # type: ignore[no-untyped-def]
    records, lines = proposal
    full = BudgetEngine(ctx_for(records)).compute(lines).totals.request_minor
    ceiling = Money(amount_minor=max(1, full * pct // 100))
    ctx = ctx_for(records, award_ceiling=ceiling)
    solution = fit_budget(lines, ctx)
    recomputed = BudgetEngine(ctx).compute(solution.lines)
    assert recomputed.totals == solution.ledger.totals
    assert recomputed.line_items == solution.ledger.line_items
    if solution.feasible:
        assert solution.ledger.totals.request_minor <= ceiling.amount_minor
    else:
        assert "award_ceiling" in solution.unresolved
    original = {ln.line_id: ln for ln in lines}
    for ln in solution.lines:
        before = original[ln.line_id]
        assert Decimal(ln.basis.quantity) <= Decimal(before.basis.quantity)
        if before.basis.effort_pct_bps is not None:
            assert ln.basis.effort_pct_bps is not None
            assert 1000 <= ln.basis.effort_pct_bps <= before.basis.effort_pct_bps or (
                ln.basis.effort_pct_bps == before.basis.effort_pct_bps
            )


@SOLVER
@given(proposals(), st.integers(1, 99), st.integers(1, 99))
def test_solver_ceiling_monotonicity(proposal, a: int, b: int) -> None:  # type: ignore[no-untyped-def]
    records, lines = proposal
    full = BudgetEngine(ctx_for(records)).compute(lines).totals.request_minor
    low, high = sorted((a, b))
    fit = [
        fit_budget(
            lines, ctx_for(records, award_ceiling=Money(amount_minor=max(1, full * p // 100)))
        )
        for p in (low, high)
    ]
    if fit[0].feasible and fit[1].feasible:
        assert fit[0].ledger.totals.request_minor <= fit[1].ledger.totals.request_minor


def test_agency_rate_is_used_when_below_cap() -> None:
    records = [record("erp:x", "unit_cost", 100_000_00)]
    ctx = replace(
        ctx_for(records, indirect_cap_bps=3000),
        agency=sample_agency(indirect_rate_bps=800, indirect_type="negotiated_nicra"),
    )
    assert (
        BudgetEngine(ctx).compute([line("x", "supplies", "erp:x")]).totals.indirect_minor
        == 8_000_00
    )
