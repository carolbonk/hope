"""OR-Tools fit of an over-limit budget (blueprint 8.1).

The solver only changes the proposal (effort percentages and quantities) and every candidate is
recomputed by the Budget Engine, so it never writes an amount. Order of preference: drop
unallowable lines, cut non-personnel quantities, and only then cut personnel effort.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Literal

from hope_core.money import BPS_PER_UNIT
from hope_core.schemas.proposal_framework import BudgetLedger, CapCheck
from ortools.sat.python import cp_model
from pydantic import BaseModel, ConfigDict

from hope_budget.engine import (
    MTDC_EXCLUDED_CATEGORIES,
    MTDC_EXCLUDED_KINDS,
    BudgetContext,
    BudgetEngine,
    ProposedLine,
    eligible_cost_share,
    parse_quantity,
    seal,
)
from hope_budget.rules import effective_indirect

SCALE = 100
"""Solver works in hundredths of a minor unit; the engine recomputes exact amounts."""

FIXABLE_RULES = frozenset({"award_ceiling", "cost_share_ratio", "unallowable_cost"})


class Adjustment(BaseModel):
    model_config = ConfigDict(frozen=True)

    line_id: str
    change: Literal["removed", "quantity", "effort_pct_bps"]
    before: str
    after: str
    reason: str

    def describe(self) -> str:
        if self.change == "removed":
            return f"removed {self.line_id} ({self.reason})"
        return f"{self.line_id} {self.change} {self.before} -> {self.after} ({self.reason})"


class BudgetSolution(BaseModel):
    ledger: BudgetLedger
    lines: list[ProposedLine]
    adjustments: list[Adjustment] = []
    feasible: bool
    unresolved: list[str] = []


@dataclass
class SolverPolicy:
    default_min_effort_bps: int = 1000
    max_iterations: int = 8
    time_limit_s: float = 10.0


@dataclass
class _Var:
    line: ProposedLine
    var: cp_model.IntVar
    hi: int
    step: Decimal
    coef: int
    base_coef: int
    subaward: str | None
    personnel: bool
    adjustable: bool = field(default=True)


def fit_budget(
    lines: Sequence[ProposedLine], ctx: BudgetContext, policy: SolverPolicy | None = None
) -> BudgetSolution:
    policy = policy or SolverPolicy()
    engine = BudgetEngine(ctx)
    original = engine.compute(lines)
    failing = _failing(original)
    if not failing:
        return BudgetSolution(ledger=original, lines=list(lines), feasible=True)
    if failing - FIXABLE_RULES:
        return BudgetSolution(
            ledger=original, lines=list(lines), feasible=False, unresolved=sorted(failing)
        )

    unallowable = {
        i.line_id
        for i in original.line_items
        if i.allowability == "unallowable" and i.category not in ("fringe", "indirect")
    }
    working = [line for line in lines if line.line_id not in unallowable]
    ledger = engine.compute(working)
    margin = 0
    for _ in range(policy.max_iterations):
        overshoot = _overshoot(ledger, ctx)
        if overshoot <= 0:
            break
        candidate = _solve(working, ctx, ledger, margin, policy)
        if candidate is None:
            break
        attempt = engine.compute(candidate)
        excess = _overshoot(attempt, ctx)
        if excess <= 0:
            working, ledger = candidate, attempt
            break
        margin += excess
    still = _failing(ledger)
    adjustments = _diff(lines, working, unallowable)
    if still:
        return BudgetSolution(
            ledger=original,
            lines=list(lines),
            adjustments=adjustments,
            feasible=False,
            unresolved=sorted(still),
        )
    note = "; ".join(a.describe() for a in adjustments)
    checks = [
        c.model_copy(update={"status": "adjusted", "adjustment_note": note})
        if c.rule in failing
        else c
        for c in ledger.cap_checks
    ]
    sealed = seal(ledger.model_copy(update={"cap_checks": checks}))
    return BudgetSolution(ledger=sealed, lines=working, adjustments=adjustments, feasible=True)


def _failing(ledger: BudgetLedger) -> set[str]:
    return {c.rule for c in ledger.cap_checks if c.status == "fail"}


def _check(ledger: BudgetLedger, rule: str) -> CapCheck | None:
    return next((c for c in ledger.cap_checks if c.rule == rule), None)


def _request_cap(ledger: BudgetLedger, ctx: BudgetContext) -> int | None:
    """Largest request that passes the ceiling and the cost-share ratio for this ledger."""
    caps: list[int] = []
    if ctx.rules.award_ceiling is not None:
        caps.append(ctx.rules.award_ceiling.amount_minor)
    ratio = ctx.rules.cost_share_ratio_bps
    if ratio:
        eligible = eligible_cost_share(ledger.line_items, ctx.rules)
        caps.append(int((Decimal(eligible) * BPS_PER_UNIT / ratio).to_integral_value(ROUND_FLOOR)))
    return min(caps) if caps else None


def _overshoot(ledger: BudgetLedger, ctx: BudgetContext) -> int:
    cap = _request_cap(ledger, ctx)
    return 0 if cap is None else ledger.totals.request_minor - cap


def _step(line: ProposedLine, quantity: Decimal) -> Decimal:
    if line.quantity_step is not None:
        step = parse_quantity(line.quantity_step)
        if step and quantity % step == 0:
            return step
    exponent = int(quantity.as_tuple().exponent)
    return Decimal(1).scaleb(min(exponent, 0))


def _scaled(value: Decimal) -> int:
    return int((value * SCALE).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _solve(
    lines: list[ProposedLine],
    ctx: BudgetContext,
    ledger: BudgetLedger,
    margin: int,
    policy: SolverPolicy,
) -> list[ProposedLine] | None:
    cap = _request_cap(ledger, ctx)
    if cap is None:
        return None
    rate_bps, _, base_type = effective_indirect(ctx.agency, ctx.rules)
    model = cp_model.CpModel()
    variables: list[_Var] = []
    for line in lines:
        if line.funding_source != "request":
            continue
        record = ctx.resolver.resolve(line.basis.cost_basis_ref)
        assert record is not None  # validated by the engine
        quantity = Decimal(line.basis.quantity)
        rate = Decimal(record.unit_rate.amount_minor)
        personnel = line.category == "personnel"
        if personnel:
            effort = line.basis.effort_pct_bps or 0
            step = Decimal(1)
            hi = effort
            lo = line.min_effort_bps
            lo = min(hi, policy.default_min_effort_bps if lo is None else lo)
            unit_amount = rate * quantity / BPS_PER_UNIT
            fringe = record.fringe_rate_bps
            fringe = (ctx.agency.fringe_rate_bps or 0) if fringe is None else fringe
        else:
            step = _step(line, quantity)
            hi = int(quantity / step)
            minimum = parse_quantity(line.min_quantity or "0") or Decimal(0)
            lo = min(hi, int((minimum / step).to_integral_value(ROUND_CEILING)))
            unit_amount = rate * step
            fringe = 0
        if line.locked:
            lo = hi
        full = unit_amount * (BPS_PER_UNIT + fringe) / BPS_PER_UNIT
        if base_type == "salaries_wages":
            in_base, base_unit = personnel, unit_amount
        elif base_type == "TDC":
            in_base, base_unit = True, full
        else:
            in_base = not (
                line.category in MTDC_EXCLUDED_CATEGORIES or record.kind in MTDC_EXCLUDED_KINDS
            )
            base_unit = full
        subaward = (record.subaward_id or record.ref) if record.kind == "subaward" else None
        variables.append(
            _Var(
                line=line,
                var=model.new_int_var(lo, hi, line.line_id),
                hi=hi,
                step=step,
                coef=_scaled(full),
                base_coef=_scaled(base_unit) if in_base else 0,
                subaward=subaward if base_type == "MTDC" else None,
                personnel=personnel,
                adjustable=lo < hi,
            )
        )

    if not any(v.adjustable for v in variables):
        return None
    direct = sum(v.coef * v.var for v in variables)
    base_terms = [v.base_coef * v.var for v in variables if v.subaward is None]
    threshold = ctx.rules.subaward_mtdc_threshold_minor * SCALE
    for subaward in sorted({v.subaward for v in variables if v.subaward}):
        members = [v for v in variables if v.subaward == subaward]
        upper = sum(v.base_coef * v.hi for v in members)
        total = model.new_int_var(0, upper, f"sub-{subaward}")
        model.add(total == sum(v.base_coef * v.var for v in members))
        included = model.new_int_var(0, min(upper, threshold), f"sub-{subaward}-mtdc")
        model.add_min_equality(included, [total, threshold])
        base_terms.append(included)
    base = sum(base_terms)
    request_upper = sum(v.coef * v.hi for v in variables) * 2 + 1
    request = model.new_int_var(0, request_upper, "request")
    model.add(BPS_PER_UNIT * request >= BPS_PER_UNIT * direct + rate_bps * base)
    model.add(request <= (cap - margin) * SCALE)
    floor = ctx.rules.award_floor
    if floor is not None and ledger.totals.request_minor >= floor.amount_minor:
        model.add(
            BPS_PER_UNIT * direct + rate_bps * base >= BPS_PER_UNIT * floor.amount_minor * SCALE
        )

    personnel_cut = sum(v.coef * (v.hi - v.var) for v in variables if v.personnel)
    total_cut = sum(v.coef * (v.hi - v.var) for v in variables)
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.max_time_in_seconds = policy.time_limit_s
    if any(v.personnel and v.adjustable for v in variables):
        model.minimize(personnel_cut)
        if solver.solve(model) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None
        model.add(personnel_cut <= round(solver.objective_value))
    model.minimize(total_cut)
    if solver.solve(model) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    chosen = {v.line.line_id: v for v in variables}
    out: list[ProposedLine] = []
    for line in lines:
        v = chosen.get(line.line_id)
        if v is None:
            out.append(line)
            continue
        value = int(solver.value(v.var))
        if value == v.hi:
            out.append(line)
        elif value == 0:
            continue
        elif v.personnel:
            out.append(_with_basis(line, effort_pct_bps=value))
        else:
            out.append(_with_basis(line, quantity=format((value * v.step).normalize(), "f")))
    return out


def _with_basis(line: ProposedLine, **update: object) -> ProposedLine:
    return line.model_copy(update={"basis": line.basis.model_copy(update=update)})


def _diff(
    before: Sequence[ProposedLine], after: Sequence[ProposedLine], unallowable: set[str]
) -> list[Adjustment]:
    kept = {line.line_id: line for line in after}
    out: list[Adjustment] = []
    for line in before:
        new = kept.get(line.line_id)
        if new is None:
            reason = "unallowable cost" if line.line_id in unallowable else "fit under limits"
            out.append(
                Adjustment(
                    line_id=line.line_id,
                    change="removed",
                    before=line.basis.quantity,
                    after="0",
                    reason=reason,
                )
            )
        elif new.basis.effort_pct_bps != line.basis.effort_pct_bps:
            out.append(
                Adjustment(
                    line_id=line.line_id,
                    change="effort_pct_bps",
                    before=str(line.basis.effort_pct_bps),
                    after=str(new.basis.effort_pct_bps),
                    reason="fit under limits",
                )
            )
        elif new.basis.quantity != line.basis.quantity:
            out.append(
                Adjustment(
                    line_id=line.line_id,
                    change="quantity",
                    before=line.basis.quantity,
                    after=new.basis.quantity,
                    reason="fit under limits",
                )
            )
    return out
