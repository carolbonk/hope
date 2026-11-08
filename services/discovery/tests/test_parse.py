from __future__ import annotations

from datetime import date

import pytest
from hope_discovery.parse import (
    context_of,
    find_amount,
    find_deadline,
    parse_amount,
    parse_deadline,
    pick_award,
)

TODAY = date(2026, 11, 8)


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
    ],
)
def test_deadline_formats_yearless_and_rolling(
    quote: str, expected: date | None, rolling: bool, yearless: bool
) -> None:
    parsed = parse_deadline(quote, TODAY)
    assert parsed.date == expected
    assert parsed.rolling is rolling
    assert parsed.yearless is yearless
    if "2025" in quote:
        assert parsed.all_dates == [date(2025, 3, 1)]


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
