import pytest
from hope_budget.engine import BudgetEngine
from hope_budget.numeric import NumericContext, find_raw_figures, reconcile, render, verify_text
from hope_budget.testing import sample_context, sample_lines
from hope_core.schemas.agency_profile import Outcome, Program
from hope_core.testing.factories import agency_profile, grant_opportunity


@pytest.fixture
def ctx() -> NumericContext:
    ledger = BudgetEngine(sample_context()).compute(sample_lines())
    program = Program(
        program_id="prog-stem",
        name="STEM Lab",
        description="d",
        outcomes=[Outcome(metric_id="youth_served", label="Youth", value=412, period="FY26")],
    )
    profile = agency_profile(programs=[program])
    return NumericContext.build(ledger, profile, grant_opportunity())


def test_render_placeholders(ctx: NumericContext) -> None:
    text = render(
        "We request {{ledger.totals.request_minor | money}} to serve "
        "{{profile.metric:youth_served}} youth, with indirect at {{ledger.indirect_rate_bps | pct}}"
        " of {{ ledger.totals.mtdc_base_minor|money }}.",
        ctx,
    )
    assert text == (
        "We request USD 175,873.48 to serve 412 youth, with indirect at 10% of USD 134,430.44."
    )
    assert reconcile(text, ctx).passed


def test_verify_text_end_to_end(ctx: NumericContext) -> None:
    rendered, report = verify_text(
        "Our ceiling is {{opportunity.funding.award_ceiling | money}} under ALN "
        "{{opportunity.funder.aln[0]}}.",
        ctx,
    )
    assert report.passed, report
    assert rendered == "Our ceiling is USD 250,000.00 under ALN 93.243."
    assert {m.source_path for m in report.matched} == {
        "opportunity.funding.award_ceiling",
        "opportunity.funder.aln[0]",
    }


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("We need $175,873.48 for staff.", "raw_currency_figure"),
        ("We need $ 5 for staff.", "raw_currency_figure"),
        ("A total of 5,000 dollars.", "raw_currency_figure"),
        ("USD 1200 for travel", "raw_currency_figure"),
        ("Indirect is 10% of MTDC.", "raw_percent_figure"),
        ("Indirect is 12.5 percent.", "raw_percent_figure"),
    ],
)
def test_guard_rejects_raw_figures(ctx: NumericContext, text: str, rule: str) -> None:
    assert [v.rule for v in find_raw_figures(text)] == [rule]
    rendered, report = verify_text(text, ctx)
    assert not report.passed and rendered == text
    assert report.policy_violations[0].rule == rule


def test_guard_ignores_placeholders(ctx: NumericContext) -> None:
    assert find_raw_figures("We request {{ledger.totals.request_minor | money}}.") == []


@pytest.mark.parametrize(
    "text",
    [
        "{{ledger.totals.nope | money}}",
        "{{ledger.totals.request_minor | pct}}",
        "{{profile.metric:x}}",
    ],
)
def test_unknown_or_mistyped_placeholder(ctx: NumericContext, text: str) -> None:
    _, report = verify_text(text, ctx)
    assert [v.rule for v in report.policy_violations] == ["unknown_placeholder"]


def test_reconciler_detects_tampered_numbers(ctx: NumericContext) -> None:
    report = reconcile(
        "We request $175,873.49 to serve 413 youth at 10% indirect over 3 years.", ctx
    )
    assert not report.passed
    assert [m.token for m in report.numeric_mismatches] == ["$175,873.49", "413", "3"]
    assert [m.source_path for m in report.matched] == ["ledger.indirect_rate_bps"]


def test_reconciler_kind_must_match(ctx: NumericContext) -> None:
    # 412 is a metric, not a dollar figure or percent
    report = reconcile("$412 and 412%", ctx)
    assert [m.kind for m in report.numeric_mismatches] == ["money", "percent"]


def test_reconciler_allowed_literals_and_identifiers(ctx: NumericContext) -> None:
    text = "Since 2019, the alliance has served 412 youth."
    assert not reconcile(text, ctx).passed
    assert reconcile(text, ctx, allowed=["2019"]).passed


def test_reconciler_ignores_digits_inside_words(ctx: NumericContext) -> None:
    assert reconcile("Form SF-424A and section B2 apply.", ctx).passed
