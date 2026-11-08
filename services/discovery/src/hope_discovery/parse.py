"""Amounts and deadlines are parsed by code, never by the model (H2 step 7).

Ported from `hope_ingestion.parsing.validators` (money and date regexes).
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from hope_core.money import Money

MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ]
    )
    for m in names
}
_MONTH_RX = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_NAMED = re.compile(
    r"\b(?P<month>" + _MONTH_RX + r")\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<year>\d{4})\b",
    re.I,
)
DATE_DAY_FIRST = re.compile(
    r"\b(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>" + _MONTH_RX + r")\.?,?\s+(?P<year>\d{4})\b",
    re.I,
)
DATE_US = re.compile(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})\b")
DATE_ISO = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b")
DATE_YEARLESS = re.compile(
    r"\b(?:" + _MONTH_RX + r")\.?\s+\d{1,2}(?:st|nd|rd|th)?\b|\b\d{1,2}/\d{1,2}\b(?!/)", re.I
)
ROLLING = re.compile(
    r"\brolling\b|\bopen until filled\b|\baccepted year[- ]round\b|\byear[- ]round\b"
    r"|\bongoing basis\b|\bany time\b|\banytime\b",
    re.I,
)
MONEY = re.compile(
    r"(?:\$|\bUSD\s?)\s*(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?"
    r"(?:\s*(?P<mult>million|billion|thousand|mm|m|k|b)\b)?",
    re.I,
)
NON_USD = re.compile(r"[€£¥]|\b(?:EUR|GBP|CAD|AUD|MXN|COP)\b|\bC\$|\bA\$", re.I)
MULTIPLIERS = {"thousand": 10**3, "k": 10**3, "million": 10**6, "m": 10**6, "mm": 10**6}
MULTIPLIERS |= {"billion": 10**9, "b": 10**9}
RANGE_SEP = re.compile(r"^\s*(?:-|\u2013|\u2014|to|and)\s*$", re.I)


@dataclass(frozen=True)
class AmountParse:
    min: Money | None
    max: Money | None


@dataclass(frozen=True)
class DeadlineParse:
    date: _dt.date | None
    rolling: bool = False
    all_dates: list[_dt.date] = field(default_factory=list)
    yearless: bool = False


def _amounts(text: str) -> list[tuple[Money, int, int]]:
    found = []
    for m in MONEY.finditer(text):
        major = Decimal(m.group("num").replace(",", "") + (m.group("frac") or ""))
        mult = (m.group("mult") or "").lower()
        found.append((Money.from_decimal(major * MULTIPLIERS.get(mult, 1)), m.start(), m.end()))
    return found


def parse_amount(quote: str | None) -> AmountParse | None:
    """`$50,000`, `$50K`, `$1.5 million`, `up to $25,000`, `$10,000-$25,000`, `between $5,000 and
    $15,000`. A single amount is the maximum; a range keeps both ends. Non-USD → None."""
    if not quote or NON_USD.search(quote):
        return None
    found = _amounts(quote)
    if not found:
        return None
    if len(found) >= 2 and RANGE_SEP.match(quote[found[0][2] : found[1][1]]):
        low, high = sorted((found[0][0], found[1][0]), key=lambda m: m.amount_minor)
        return AmountParse(min=low, max=high)
    return AmountParse(min=None, max=found[0][0])


def _dates(text: str) -> list[date]:
    out: list[tuple[int, date]] = []
    taken: list[tuple[int, int]] = []
    for rx in (DATE_NAMED, DATE_DAY_FIRST, DATE_US, DATE_ISO):
        for m in rx.finditer(text):
            if any(s < m.end() and m.start() < e for s, e in taken):
                continue
            month = m.group("month")
            month_no = int(month) if month.isdigit() else MONTHS[month.lower().rstrip(".")]
            try:
                out.append((m.start(), date(int(m.group("year")), month_no, int(m.group("day")))))
            except ValueError:
                continue
            taken.append((m.start(), m.end()))
    return [d for _, d in sorted(out, key=lambda x: x[0])]


def parse_deadline(quote: str | None, today: date) -> DeadlineParse:
    """`deadline` is the earliest date on or after `today`. Year-less dates are not parsed."""
    if not quote:
        return DeadlineParse(None)
    dates = _dates(quote)
    rolling = bool(ROLLING.search(quote))
    if rolling and not dates:
        return DeadlineParse(None, rolling=True)
    future = sorted(d for d in dates if d >= today)
    yearless = not dates and bool(DATE_YEARLESS.search(quote))
    return DeadlineParse(future[0] if future else None, rolling, dates, yearless)


def has_money_or_date(sentence: str) -> bool:
    return bool(MONEY.search(sentence) or _dates(sentence) or DATE_YEARLESS.search(sentence))
