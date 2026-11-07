"""Placeholder rendering, raw-figure guard and numeric reconciliation (blueprint 8.1).

LLM text carries placeholders like `{{ledger.totals.request_minor | money}}` or
`{{profile.metric:youth_served}}`. The renderer fills them from the ledger, profile and
opportunity; the reconciler then maps every number in the rendered text back to one of them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from hope_core.money import BPS_PER_UNIT, Money
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.grant_opportunity import GrantOpportunity
from hope_core.schemas.proposal_framework import BudgetLedger, Totals

from hope_budget.contracts import (
    NumericKind,
    NumericMatch,
    NumericMismatch,
    NumericReconciliationReport,
    PolicyViolation,
)

PLACEHOLDER = re.compile(r"\{\{\s*(?P<path>[^{}|]+?)\s*(?:\|\s*(?P<filter>\w+)\s*)?\}\}")
RAW_CURRENCY = re.compile(
    r"(?:[$€£]|\b(?:USD|EUR|GBP)\b)\s?\d|\d[\d,]*(?:\.\d+)?\s?(?:dollars?|USD|EUR|GBP)\b",
    re.IGNORECASE,
)
RAW_PERCENT = re.compile(r"\d[\d,]*(?:\.\d+)?\s?(?:%|percent\b|per cent\b)", re.IGNORECASE)
NUMBER = re.compile(
    r"(?<![A-Za-z0-9_.\-])"
    r"(?P<cur>(?:USD|EUR|GBP)\s|[$€£]\s?)?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?!\.\d|\d)"
    r"(?P<pct>\s?%|\spercent\b)?"
    r"(?![A-Za-z0-9_])"
)
SYMBOL_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP"}


class RenderError(KeyError):
    pass


@dataclass(frozen=True)
class NumericValue:
    kind: NumericKind
    value: Decimal
    """Minor units for money, basis points for percent, the number itself otherwise."""
    currency: str = "USD"
    text: str | None = None


def format_number(value: Decimal) -> str:
    return format(value.normalize(), ",f")


def format_value(value: NumericValue, filter_name: str | None = None) -> str:
    name = filter_name or {"money": "money", "percent": "pct"}.get(value.kind, "number")
    if name == "money" and value.kind == "money":
        return Money(amount_minor=int(value.value), currency=value.currency).format()
    if name == "pct" and value.kind == "percent":
        return format_number(value.value / 100) + "%"
    if name == "number" and value.kind in ("number", "identifier"):
        return value.text or format_number(value.value)
    raise RenderError(f"filter {name!r} does not apply to a {value.kind} value")


class NumericContext:
    def __init__(self, values: dict[str, NumericValue]) -> None:
        self.values = values

    @classmethod
    def build(
        cls,
        ledger: BudgetLedger | None = None,
        profile: AgencyProfile | None = None,
        opportunity: GrantOpportunity | None = None,
    ) -> NumericContext:
        values: dict[str, NumericValue] = {}

        def money(path: str, minor: int | None, currency: str) -> None:
            if minor is not None:
                values[path] = NumericValue("money", Decimal(minor), currency)

        def money_of(path: str, amount: Money | None) -> None:
            if amount is not None:
                money(path, amount.amount_minor, amount.currency)

        def scalar(path: str, kind: NumericKind, value: float | int | None) -> None:
            if value is not None:
                values[path] = NumericValue(kind, Decimal(str(value)))

        if ledger is not None:
            cur = ledger.currency
            for name in Totals.model_fields:
                money(f"ledger.totals.{name}", getattr(ledger.totals, name), cur)
            for key, minor in ledger.sf424a_mapping.items():
                money(f"ledger.sf424a.{key}", minor, cur)
            for item in ledger.line_items:
                money(f"ledger.line.{item.line_id}", item.amount_minor, cur)
                if item.category == "indirect":
                    rate = Decimal(item.basis.quantity) * BPS_PER_UNIT
                    values["ledger.indirect_rate_bps"] = NumericValue("percent", rate)
        if profile is not None:
            fin = profile.financials
            money_of("profile.financials.annual_operating_budget", fin.annual_operating_budget)
            scalar("profile.financials.fringe_rate_bps", "percent", fin.fringe_rate_bps)
            if fin.indirect_rate is not None:
                rate_bps = fin.indirect_rate.rate_bps
                scalar("profile.financials.indirect_rate_bps", "percent", rate_bps)
            for program in profile.programs:
                money_of(f"profile.program:{program.program_id}.annual_cost", program.annual_cost)
                for outcome in program.outcomes:
                    scalar(f"profile.metric:{outcome.metric_id}", "number", outcome.value)
        if opportunity is not None:
            funding = opportunity.funding
            money_of("opportunity.funding.award_ceiling", funding.award_ceiling)
            money_of("opportunity.funding.award_floor", funding.award_floor)
            money_of("opportunity.funding.total_program_funding", funding.total_program_funding)
            scalar("opportunity.funding.expected_awards", "number", funding.expected_awards)
            if funding.cost_share is not None:
                ratio = funding.cost_share.ratio_bps
                scalar("opportunity.funding.cost_share_ratio_bps", "percent", ratio)
            if funding.indirect_cost_policy is not None:
                cap = funding.indirect_cost_policy.cap_bps
                scalar("opportunity.funding.indirect_cap_bps", "percent", cap)
            months = opportunity.deadlines.project_period_months
            scalar("opportunity.deadlines.project_period_months", "number", months)
            for i, aln in enumerate(opportunity.funder.aln):
                values[f"opportunity.funder.aln[{i}]"] = NumericValue(
                    "identifier", Decimal(0), text=aln
                )
        return cls(values)

    def get(self, path: str) -> NumericValue:
        if path not in self.values:
            raise RenderError(f"unknown placeholder {path!r}")
        return self.values[path]


def render(template: str, ctx: NumericContext) -> str:
    def fill(match: re.Match[str]) -> str:
        return format_value(ctx.get(match["path"]), match["filter"])

    return PLACEHOLDER.sub(fill, template)


def find_raw_figures(text: str) -> list[PolicyViolation]:
    """Currency or percent figures typed by a model instead of placeholders are a hard fail."""
    blanked = PLACEHOLDER.sub(lambda m: " " * len(m[0]), text)
    found: list[PolicyViolation] = []
    for rule, pattern in (
        ("raw_currency_figure", RAW_CURRENCY),
        ("raw_percent_figure", RAW_PERCENT),
    ):
        for match in pattern.finditer(blanked):
            found.append(
                PolicyViolation.model_validate(
                    {"rule": rule, "excerpt": match[0], "offset": match.start()}
                )
            )
    return sorted(found, key=lambda v: v.offset)


def reconcile(
    text: str, ctx: NumericContext, allowed: Iterable[str] = ()
) -> NumericReconciliationReport:
    """Map every number in rendered text to a ledger, profile or opportunity value."""
    allowed_set = set(allowed)
    matched: list[NumericMatch] = []
    mismatches: list[NumericMismatch] = []
    for match in NUMBER.finditer(text):
        token = match[0].strip()
        number = Decimal(match["num"].replace(",", ""))
        kind: NumericKind = "money" if match["cur"] else "percent" if match["pct"] else "number"
        currency = (
            SYMBOL_CURRENCY.get(match["cur"].strip(), match["cur"].strip())
            if match["cur"]
            else None
        )
        path = _lookup(ctx, kind, number, match["num"], currency)
        if path is None and match["num"] in allowed_set:
            path = "allowed"
        if path is None:
            mismatches.append(
                NumericMismatch(
                    token=token,
                    kind=kind,
                    offset=match.start(),
                    reason="no ledger, profile or opportunity value matches",
                )
            )
        else:
            matched.append(NumericMatch(token=token, kind=kind, source_path=path))
    return NumericReconciliationReport(
        passed=not mismatches, numeric_mismatches=mismatches, matched=matched
    )


def _lookup(
    ctx: NumericContext, kind: NumericKind, number: Decimal, raw: str, currency: str | None
) -> str | None:
    for path, value in ctx.values.items():
        if kind == "money":
            if value.kind == "money" and value.currency == currency and value.value == number * 100:
                return path
        elif kind == "percent":
            if value.kind == "percent" and value.value == number * 100:
                return path
        elif (
            (value.kind == "identifier" and value.text == raw)
            or (value.kind == "number" and value.value == number)
            or (value.kind in ("money", "percent") and value.value == number * 100)
        ):
            return path
    return None


def verify_text(
    llm_text: str, ctx: NumericContext, allowed: Iterable[str] = ()
) -> tuple[str, NumericReconciliationReport]:
    """Guard, render and reconcile model-written text in one pass."""
    violations = find_raw_figures(llm_text)
    for match in PLACEHOLDER.finditer(llm_text):
        try:
            format_value(ctx.get(match["path"]), match["filter"])
        except RenderError:
            violations.append(
                PolicyViolation(rule="unknown_placeholder", excerpt=match[0], offset=match.start())
            )
    if violations:
        return llm_text, NumericReconciliationReport(passed=False, policy_violations=violations)
    rendered = render(llm_text, ctx)
    return rendered, reconcile(rendered, ctx, allowed)
