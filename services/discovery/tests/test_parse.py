from __future__ import annotations

from datetime import date

import pytest
from hope_discovery.parse import parse_amount, parse_deadline

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
