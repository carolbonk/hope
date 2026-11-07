"""Deterministic Budget Engine (blueprint 2.2 A7, 8.1). Every amount in a ledger comes from here.

Rounding: half-up per line in minor units; totals are sums of rounded lines.
Indirect is charged on the requested share only, one line per budget period.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Literal

from hope_core.hashing import content_hash
from hope_core.money import BPS_PER_UNIT, Bps, Money, sum_money
from hope_core.schemas.common import Contract
from hope_core.schemas.proposal_framework import (
    BudgetCategory,
    BudgetLedger,
    CapCheck,
    LineItem,
    LineItemBasis,
    Totals,
)
from pydantic import Field

from hope_budget.contracts import CostBasisRecord
from hope_budget.resolver import CostBasisResolver
from hope_budget.rules import (
    PROFILE_REF,
    AgencyRates,
    BudgetRules,
    IndirectBase,
    effective_indirect,
    indirect_limit_bps,
)

ENGINE_VERSION = "hope-budget-engine/0.1.0"

DirectCategory = Literal[
    "personnel", "travel", "equipment", "supplies", "contractual", "construction", "other"
]
FundingSource = Literal["request", "cost_share_cash", "cost_share_in_kind"]

MTDC_EXCLUDED_CATEGORIES: frozenset[BudgetCategory] = frozenset({"equipment", "construction"})
MTDC_EXCLUDED_KINDS = frozenset(
    {
        "equipment",
        "participant_support",
        "rental",
        "tuition_remission",
        "scholarship",
        "patient_care",
    }
)

SF424A_LINES: dict[BudgetCategory, str] = {
    "personnel": "6a_personnel",
    "fringe": "6b_fringe_benefits",
    "travel": "6c_travel",
    "equipment": "6d_equipment",
    "supplies": "6e_supplies",
    "contractual": "6f_contractual",
    "construction": "6g_construction",
    "other": "6h_other",
    "indirect": "6j_indirect_charges",
}


class BudgetInputError(ValueError):
    """Proposal rejected before any math: unresolvable refs, missing provenance, bad shapes."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class ProposedLine(Contract):
    """A direct-cost line as proposed (by A7 or a human). Fringe and indirect are derived."""

    line_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    category: DirectCategory
    description: str | None = None
    period: int = Field(1, ge=1)
    basis: LineItemBasis
    funding_source: FundingSource = "request"
    justification: str | None = None
    locked: bool = Field(False, description="the solver may not change this line")
    min_effort_bps: Bps | None = Field(None, description="solver lower bound for personnel")
    min_quantity: str | None = Field(None, description="solver lower bound for other lines")
    quantity_step: str | None = Field(None, description="solver quantity granularity")


def parse_quantity(raw: str) -> Decimal | None:
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value.is_finite() and value >= 0 else None


def rate_quantity(bps: int) -> str:
    return format(Decimal(bps) / BPS_PER_UNIT, "f")


def ceil_bps(amount_minor: int, bps: int) -> int:
    return int((Decimal(amount_minor) * bps / BPS_PER_UNIT).to_integral_value(ROUND_CEILING))


def seal(ledger: BudgetLedger) -> BudgetLedger:
    """Set `ledger_id` to the content hash of everything else in the ledger."""
    return ledger.model_copy(update={"ledger_id": content_hash(_unsealed(ledger))})


def is_sealed(ledger: BudgetLedger) -> bool:
    return ledger.ledger_id == content_hash(_unsealed(ledger))


def _unsealed(ledger: BudgetLedger) -> BudgetLedger:
    return ledger.model_copy(update={"ledger_id": ""})


@dataclass(frozen=True)
class BudgetContext:
    resolver: CostBasisResolver
    agency: AgencyRates
    rules: BudgetRules
    periods: int | None = None


@dataclass(frozen=True)
class _Row:
    item: LineItem
    record: CostBasisRecord
    order: int
    is_fringe: bool = False


class BudgetEngine:
    def __init__(self, ctx: BudgetContext) -> None:
        self.ctx = ctx

    def validate(self, lines: Sequence[ProposedLine]) -> list[str]:
        ctx, errors = self.ctx, []
        seen: set[str] = set()
        uses_agency_fringe = False
        for line in lines:
            where = f"line {line.line_id}"
            if line.line_id in seen:
                errors.append(f"{where}: duplicate line_id")
            seen.add(line.line_id)
            if line.basis.unit_rate_minor is not None:
                errors.append(f"{where}: unit_rate_minor must come from the cost basis record")
            if parse_quantity(line.basis.quantity) is None:
                errors.append(f"{where}: quantity {line.basis.quantity!r} is not a decimal >= 0")
            if ctx.periods is not None and line.period > ctx.periods:
                errors.append(f"{where}: period {line.period} exceeds {ctx.periods}")
            personnel = line.category == "personnel"
            effort = line.basis.effort_pct_bps
            if personnel and (effort is None or effort > BPS_PER_UNIT):
                errors.append(f"{where}: personnel needs effort_pct_bps between 0 and 10000")
            if not personnel and effort is not None:
                errors.append(f"{where}: effort_pct_bps is only valid on personnel")
            record = ctx.resolver.resolve(line.basis.cost_basis_ref)
            if record is None:
                errors.append(
                    f"{where}: cost_basis_ref {line.basis.cost_basis_ref} does not resolve"
                )
                continue
            if record.provenance is None:
                errors.append(f"{where}: cost basis {record.ref} has no provenance")
            if record.unit_rate.currency != ctx.rules.currency:
                errors.append(f"{where}: {record.ref} is {record.unit_rate.currency}")
            if record.unit_rate.amount_minor < 0:
                errors.append(f"{where}: {record.ref} has a negative rate")
            if personnel != (record.kind == "salary"):
                errors.append(f"{where}: category {line.category} does not fit {record.kind}")
            if record.kind == "subaward" and line.category != "contractual":
                errors.append(f"{where}: subawards belong in contractual")
            if personnel and record.fringe_rate_bps is None:
                uses_agency_fringe = True
        agency = ctx.agency
        if uses_agency_fringe and agency.fringe_rate_bps is None:
            errors.append("agency fringe rate is missing")
        uses_agency_indirect = ctx.rules.indirect_allowed and agency.indirect_type != "none"
        if (uses_agency_fringe or uses_agency_indirect) and agency.provenance is None:
            errors.append("agency rates have no provenance")
        if agency.indirect_type == "negotiated_nicra" and agency.indirect_rate_bps is None:
            errors.append("negotiated NICRA has no rate")
        return errors

    def compute(self, lines: Sequence[ProposedLine]) -> BudgetLedger:
        errors = self.validate(lines)
        if errors:
            raise BudgetInputError(errors)
        rules = self.ctx.rules
        rows = self._direct_rows(lines)
        rate_bps, rate_ref, base_type = effective_indirect(self.ctx.agency, rules)
        bases = self._indirect_bases(rows, base_type)
        indirect_items = [
            LineItem(
                line_id=f"indirect-p{period}",
                category="indirect",
                description=f"Indirect costs, period {period}",
                period=period,
                basis=LineItemBasis(
                    cost_basis_ref=rate_ref,
                    quantity=rate_quantity(rate_bps),
                    unit="rate",
                    unit_rate_minor=base.amount_minor,
                ),
                amount_minor=base.apply_bps(rate_bps).amount_minor,
            )
            for period, base in sorted(bases.items())
            if rate_bps and base.amount_minor
        ]
        items = [row.item for row in rows] + indirect_items
        totals = self._totals(items, bases)
        limit_bps = indirect_limit_bps(self.ctx.agency, rules)
        indirect_limit = sum(base.apply_bps(limit_bps).amount_minor for base in bases.values())
        ledger = BudgetLedger(
            ledger_id="",
            engine_version=ENGINE_VERSION,
            currency=rules.currency,
            periods=max([self.ctx.periods or 1, *(item.period for item in items)]),
            line_items=items,
            totals=totals,
            cap_checks=self._cap_checks(items, totals, indirect_limit),
            sf424a_mapping=_sf424a(items, totals),
        )
        return seal(ledger)

    def _direct_rows(self, lines: Sequence[ProposedLine]) -> list[_Row]:
        unallowable = {cost.strip().lower() for cost in self.ctx.rules.unallowable_costs}
        rows: list[_Row] = []
        for line in lines:
            record = self.ctx.resolver.resolve(line.basis.cost_basis_ref)
            assert record is not None  # validated
            quantity = Decimal(line.basis.quantity)
            effort = line.basis.effort_pct_bps
            if effort is not None:
                quantity = quantity * effort / BPS_PER_UNIT
            tags = {tag.lower() for tag in record.cost_tags} | {line.category}
            allowability: Literal["allowable", "unallowable"] = (
                "unallowable" if tags & unallowable else "allowable"
            )
            amount = record.unit_rate.times(quantity)
            item = LineItem(
                line_id=line.line_id,
                category=line.category,
                description=line.description or record.description,
                period=line.period,
                basis=line.basis.model_copy(
                    update={
                        "unit_rate_minor": record.unit_rate.amount_minor,
                        "unit": line.basis.unit or record.unit,
                    }
                ),
                amount_minor=amount.amount_minor,
                funding_source=line.funding_source,
                justification=line.justification,
                allowability=allowability,
            )
            rows.append(_Row(item, record, len(rows)))
            if line.category == "personnel":
                fringe_bps = record.fringe_rate_bps
                fringe_ref = record.ref
                if fringe_bps is None:
                    fringe_bps = self.ctx.agency.fringe_rate_bps or 0
                    fringe_ref = f"{PROFILE_REF}.fringe_rate_bps"
                if fringe_bps:
                    fringe = item.model_copy(
                        update={
                            "line_id": f"{line.line_id}-fringe",
                            "category": "fringe",
                            "description": f"Fringe benefits on {line.line_id}",
                            "basis": LineItemBasis(
                                cost_basis_ref=fringe_ref,
                                quantity=rate_quantity(fringe_bps),
                                unit="rate",
                                unit_rate_minor=amount.amount_minor,
                            ),
                            "amount_minor": amount.apply_bps(fringe_bps).amount_minor,
                            "justification": None,
                        }
                    )
                    rows.append(_Row(fringe, record, len(rows), is_fringe=True))
        return rows

    def _indirect_bases(self, rows: list[_Row], base_type: IndirectBase) -> dict[int, Money]:
        currency = self.ctx.rules.currency
        threshold = self.ctx.rules.subaward_mtdc_threshold_minor
        used: dict[str, int] = defaultdict(int)
        bases: dict[int, Money] = {}
        for row in sorted(rows, key=lambda r: (r.item.period, r.order)):
            item, record = row.item, row.record
            if item.funding_source != "request":
                continue
            included = item.amount_minor
            if base_type == "salaries_wages":
                included = included if item.category == "personnel" else 0
            elif base_type == "MTDC":
                if item.category in MTDC_EXCLUDED_CATEGORIES or record.kind in MTDC_EXCLUDED_KINDS:
                    included = 0
                elif record.kind == "subaward":
                    subaward = record.subaward_id or record.ref
                    included = max(0, min(included, threshold - used[subaward]))
                    used[subaward] += included
            base = bases.get(item.period, Money.zero(currency))
            bases[item.period] = base + Money(amount_minor=included, currency=currency)
        return bases

    def _totals(self, items: list[LineItem], bases: dict[int, Money]) -> Totals:
        currency = self.ctx.rules.currency

        def total(keep: bool | None = None, *, request: bool | None = None) -> int:
            picked = [
                Money(amount_minor=item.amount_minor, currency=currency)
                for item in items
                if (keep is None or (item.category != "indirect") == keep)
                and (request is None or (item.funding_source == "request") == request)
            ]
            return sum_money(picked, currency).amount_minor

        request = total(request=True)
        cost_share = total(request=False)
        return Totals(
            direct_minor=total(True),
            mtdc_base_minor=sum_money(list(bases.values()), currency).amount_minor,
            indirect_minor=total(False),
            request_minor=request,
            cost_share_minor=cost_share,
            project_total_minor=request + cost_share,
        )

    def _cap_checks(
        self, items: list[LineItem], totals: Totals, indirect_limit: int
    ) -> list[CapCheck]:
        rules = self.ctx.rules
        request = totals.request_minor
        checks: list[CapCheck] = []
        if rules.award_ceiling is not None:
            limit = rules.award_ceiling.amount_minor
            checks.append(_check("award_ceiling", limit, request, request <= limit))
        if rules.award_floor is not None:
            limit = rules.award_floor.amount_minor
            checks.append(_check("award_floor", limit, request, request >= limit))
        checks.append(
            _check(
                "indirect_cap",
                indirect_limit,
                totals.indirect_minor,
                totals.indirect_minor <= indirect_limit,
            )
        )
        if rules.cost_share_ratio_bps:
            required = ceil_bps(request, rules.cost_share_ratio_bps)
            eligible = eligible_cost_share(items, rules)
            checks.append(_check("cost_share_ratio", required, eligible, eligible >= required))
        unallowable = sum(i.amount_minor for i in items if i.allowability == "unallowable")
        checks.append(_check("unallowable_cost", 0, unallowable, unallowable == 0))
        return checks


def eligible_cost_share(items: Sequence[LineItem], rules: BudgetRules) -> int:
    sources = {"cost_share_cash"} | (
        {"cost_share_in_kind"} if rules.cost_share_in_kind_allowed else set()
    )
    return sum(
        i.amount_minor
        for i in items
        if i.funding_source in sources and i.allowability != "unallowable"
    )


def _check(rule: str, limit: int, actual: int, ok: bool) -> CapCheck:
    return CapCheck.model_validate(
        {
            "rule": rule,
            "limit_minor": limit,
            "actual_minor": actual,
            "status": "pass" if ok else "fail",
        }
    )


def _sf424a(items: list[LineItem], totals: Totals) -> dict[str, int]:
    mapping = dict.fromkeys(SF424A_LINES.values(), 0)
    for item in items:
        mapping[SF424A_LINES[item.category]] += item.amount_minor
    mapping["6i_total_direct_charges"] = totals.direct_minor
    mapping["6k_totals"] = totals.direct_minor + totals.indirect_minor
    mapping["5e_federal"] = totals.request_minor
    mapping["5f_non_federal"] = totals.cost_share_minor
    mapping["5g_total"] = totals.project_total_minor
    return dict(sorted(mapping.items()))
