from __future__ import annotations

from datetime import date

import pytest
from hope_discovery.parse import (
    context_of,
    cycle_year,
    find_amount,
    find_deadline,
    infer_deadline,
    parse_amount,
    parse_deadline,
    pick_award,
)

TODAY = date(2026, 11, 8)


@pytest.mark.parametrize("today", [date(2026, 1, 1), TODAY])
@pytest.mark.parametrize("page_fallback", [False, True])
def test_inferred_closing_cannot_precede_dated_opening(today: date, page_fallback: bool) -> None:
    quote = "Applications open November 1, 2026 and close January 15."
    pages = ["2026 grant cycle. " + quote]
    if page_fallback:
        assert find_deadline(pages, today) is None
    else:
        assert infer_deadline(quote, pages, today) is None
    next_cycle = ["2027 grant cycle. " + quote]
    inferred = infer_deadline(quote, next_cycle, today)
    assert inferred is not None and inferred.date == date(2027, 1, 15)


@pytest.mark.parametrize("separator", ["to", "\u2013", "-", "through"])
@pytest.mark.parametrize("page_fallback", [False, True])
def test_mixed_year_window_range_end_is_inferred(separator: str, page_fallback: bool) -> None:
    quote = f"Applications open January 1, 2027 {separator} March 1."
    pages = ["2027 grant cycle. " + quote]
    if page_fallback:
        found = find_deadline(pages, TODAY)
        assert found is not None and found[1].date == date(2027, 3, 1)
    else:
        parsed = infer_deadline(quote, pages, TODAY)
        assert parsed is not None and parsed.date == date(2027, 3, 1)


@pytest.mark.parametrize("label", ["Open call closes", "Open call due", "Open call deadline"])
def test_open_call_closing_label_is_a_deadline(label: str) -> None:
    quote = f"March 1, 2027: {label}"
    assert parse_deadline(quote, TODAY).date == date(2027, 3, 1)
    found = find_deadline([quote], TODAY)
    assert found is not None and found[1].date == date(2027, 3, 1)


@pytest.mark.parametrize("page_fallback", [False, True])
@pytest.mark.parametrize("separator", [". Informational", " and informational"])
def test_dated_opening_does_not_turn_webinar_into_deadline(
    page_fallback: bool, separator: str
) -> None:
    quote = f"Applications open January 1, 2027{separator} webinar March 3."
    pages = ["2027 grant cycle. " + quote]
    if page_fallback:
        assert find_deadline(pages, TODAY) is None
    else:
        assert infer_deadline(quote, pages, TODAY) is None


@pytest.mark.parametrize(
    "quote",
    [
        "Applications open until March 1, 2027",
        "Applications open through March 1, 2027",
        "January 1, 2027: applications open. March 1, 2027: applications close.",
    ],
)
def test_opening_cues_preserve_closing_dates(quote: str) -> None:
    assert parse_deadline(quote, TODAY).date == date(2027, 3, 1)
    found = find_deadline([quote], TODAY)
    assert found is not None and found[1].date == date(2027, 3, 1)


def test_dated_opening_does_not_block_yearless_closing_inference() -> None:
    quote = "Applications open January 1, 2027 and close March 1."
    pages = ["2027 grant cycle. " + quote]
    parsed = infer_deadline(quote, pages, TODAY)
    assert parsed is not None and parsed.date == date(2027, 3, 1)
    found = find_deadline(pages, TODAY)
    assert found is not None and found[1].date == date(2027, 3, 1)
    assert infer_deadline(quote, [quote], TODAY) is None


@pytest.mark.parametrize(
    ("quote", "low", "high"),
    [
        ("$50,000", None, 5_000_000),
        ("Awards of $50K", None, 5_000_000),
        ("$1.5 million over two years", None, 150_000_000),
        ("up to $25,000", None, 2_500_000),
        ("between $5,000 and $15,000", 500_000, 1_500_000),
        ("$10,000 - $40,000 per organization", 1_000_000, 4_000_000),
        ("$2,500.50", None, 250_050),
        ("Grants of 50,000 dollars", None, 5_000_000),
        ("USD 7,500", None, 750_000),
        ("No amount listed", "none", "none"),
    ],
)
def test_amount_formats(quote: str, low: int | str | None, high: int | str) -> None:
    parsed = parse_amount(quote)
    if high == "none":
        assert parsed is None or parsed.max is None
        return
    assert parsed is not None and parsed.max is not None
    assert parsed.max.amount_minor == high and parsed.max.currency == "USD"
    if low is not None:
        assert parsed.min is not None and parsed.min.amount_minor == low


@pytest.mark.parametrize(
    ("quote", "expected", "rolling", "yearless"),
    [
        ("Applications due March 3, 2027", date(2027, 3, 3), False, False),
        ("Due Mar. 3, 2027", date(2027, 3, 3), False, False),
        ("Deadline: 3 March 2027", date(2027, 3, 3), False, False),
        ("Submit by 03/03/2027", date(2027, 3, 3), False, False),
        ("Closes 2027-03-03", date(2027, 3, 3), False, False),
        ("Submit by 3/3/27", date(2027, 3, 3), False, False),
        (
            "LOI due January 15, 2027; full proposal due March 1, 2027",
            date(2027, 1, 15),
            False,
            False,
        ),
        ("Applications due March 3", None, False, True),
        ("Rolling, applications accepted year-round", None, True, False),
        ("Applications were due March 1, 2025", None, False, False),
        (None, None, False, False),
        ("Applications open January 1, 2027", None, False, False),
        (
            "Applications open February 30, 2027 and close March 1, 2027",
            date(2027, 3, 1),
            False,
            False,
        ),
    ],
)
def test_deadline_formats_yearless_and_rolling(
    quote: str | None, expected: date | None, rolling: bool, yearless: bool
) -> None:
    parsed = parse_deadline(quote, TODAY)
    assert parsed.date == expected
    assert parsed.rolling is rolling
    assert parsed.yearless is yearless
    if quote and "2025" in quote:
        assert parsed.all_dates == [date(2025, 3, 1)]


@pytest.mark.parametrize(
    "quote",
    [
        "Applications open January 1, 2027 and close March 1, 2027.",
        "Applications open Jan 1, 2027 \u2013 close Mar 1, 2027.",
        "Applications open January 1, 2027 and are due March 1, 2027.",
        "Application window: January 1, 2027 through March 1, 2027.",
        "Applications open January 1 and close March 1.",
    ],
)
def test_application_window_uses_closing_deadline(quote: str) -> None:
    pages = ["2027 grant cycle. " + quote]
    parsed = (
        parse_deadline(quote, TODAY) if "2027" in quote else infer_deadline(quote, pages, TODAY)
    )
    assert parsed is not None and parsed.date == date(2027, 3, 1)
    found = find_deadline(pages, TODAY)
    assert found is not None and found[1].date == date(2027, 3, 1)


@pytest.mark.parametrize(
    ("quote", "context", "part", "high", "total"),
    [
        (
            "up to $1 million in grants, ranging from $5,000 to $50,000 per organization",
            "",
            "ranging from $5,000 to $50,000 per organization",
            5_000_000,
            False,
        ),
        (
            "$16.3 million",
            "The foundation awards $16.3 million in grants this year.",
            None,
            0,
            True,
        ),
        ("over $11 million", "", None, 0, True),
        ("Total funding available: $2,000,000", "", None, 0, True),
        ("up to $75,000 per year.", "", "up to $75,000 per year.", 7_500_000, False),
        ("$10,000 - $40,000 per organization.", "", None, 4_000_000, False),
    ],
)
def test_pick_award_prefers_one_award_over_totals(
    quote: str, context: str, part: str | None, high: int, total: bool
) -> None:
    pick = pick_award(quote, context)
    assert pick is not None and pick.amount.max is not None
    assert pick.total is total
    assert pick.text == (part or quote)
    if not total:
        assert pick.amount.max.amount_minor == high


PAGE = (
    "Cascade Fund 2027 Cycle\n"
    "Since 1990 the fund has awarded over $12 million to Washington nonprofits. "
    "This year $400,000 is available in total. "
    "Grants range from $5,000 to $25,000 per organization. "
    "Last year's deadline was March 1, 2026. "
    "Letters of intent are due January 15, 2027, and full proposals must be submitted by "
    "March 1, 2027.\n"
    "Questions? Call us before December 1, 2026."
)


def test_find_amount_and_deadline_on_page() -> None:
    found = find_amount(["Welcome.", PAGE])
    assert found is not None
    quote, amount = found
    assert quote.text == "Grants range from $5,000 to $25,000 per organization." and quote.page == 2
    assert amount.min is not None and amount.min.amount_minor == 500_000
    assert amount.max is not None and amount.max.amount_minor == 2_500_000

    dl = find_deadline([PAGE], TODAY)
    assert dl is not None
    assert dl[0].text.startswith("Letters of intent are due January 15, 2027")
    assert dl[1].date == date(2027, 1, 15)


def test_find_deadline_rolling_none_and_past_only() -> None:
    rolling = find_deadline(["We review applications on a rolling basis."], TODAY)
    assert rolling is not None and rolling[1].rolling and rolling[1].date is None
    assert find_deadline(["Applications were due March 1, 2025."], TODAY) is None
    assert find_deadline(["Our office opened March 1, 2027."], TODAY) is None
    assert find_amount(["We have invested $3 million since 2001."]) is None
    assert find_amount(["A $50 fee applies."]) is None


def test_context_of_finds_the_clause() -> None:
    assert context_of("$400,000", [PAGE]) == "This year $400,000 is available in total."
    assert context_of("not on the page", [PAGE]) == ""


def test_cumulative_awarded_reads_as_total() -> None:
    pick = pick_award("Grants Awarded $5,921,817.32")
    assert pick is not None and pick.total
    assert find_amount(["Grants Awarded $5,921,817.32"]) is None
    pick = pick_award("Up to $5,000 will be awarded per organization.")
    assert pick is not None and not pick.total


@pytest.mark.parametrize(
    ("quote", "pages", "want"),
    [
        ("Applications are accepted each year from March 1 through June 1.", [], date(2027, 6, 1)),
        ("Proposals are due annually on December 1.", [], date(2026, 12, 1)),
        ("The deadline is August 15.", ["Now Accepting 2027 Applications"], date(2027, 8, 15)),
        ("Due March 3.", ["Rural Oral Health Access Grant 2027."], date(2027, 3, 3)),
        ("LOIs due February 1 and proposals due April 1 each year.", [], date(2027, 2, 1)),
    ],
)
def test_infer_deadline_takes_the_year_from_the_page(
    quote: str, pages: list[str], want: date
) -> None:
    got = infer_deadline(quote, pages, TODAY)
    assert got is not None and got.inferred and got.date == want


@pytest.mark.parametrize(
    ("quote", "pages"),
    [
        ("The deadline is August 15.", []),  # no year anywhere
        ("The deadline is August 15.", ["Now Accepting 2026 Applications"]),  # that date has passed
        ("The deadline is August 15.", ["2026 Applications", "2027 grant cycle"]),  # two years
        ("The deadline is August 15.", ["2026-2027 grant cycle"]),  # a span names no one year
        ("Applications due March 3, 2027.", ["2027 grant cycle"]),  # has its year: not inferred
        ("Apply any time.", ["2027 grant cycle"]),
    ],
)
def test_infer_deadline_never_guesses(quote: str, pages: list[str]) -> None:
    assert infer_deadline(quote, pages, TODAY) is None


def test_cycle_year() -> None:
    assert cycle_year(["The 2027 grant cycle opens soon."]) == 2027
    assert cycle_year(["FY 2027 funding"]) == 2027
    assert cycle_year(["Founded in 2004.", "Annual report 2025"]) is None


def test_find_deadline_prefers_stated_years_then_inferred_then_rolling() -> None:
    page = "2027 grant cycle. Applications are rolling. Full proposals are due May 1."
    found = find_deadline([page], TODAY)
    assert found is not None and found[1].date == date(2027, 5, 1) and found[1].inferred
    assert found[0].text == "Full proposals are due May 1."
    stated = page + " Letters of intent due January 15, 2027."
    found = find_deadline([stated], TODAY)
    assert found is not None and found[1].date == date(2027, 1, 15) and not found[1].inferred
