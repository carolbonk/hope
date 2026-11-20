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
DATE_US = re.compile(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4}|\d{2})\b(?!/)")
DATE_ISO = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b")
DATE_YEARLESS = re.compile(
    r"\b(?:" + _MONTH_RX + r")\.?\s+\d{1,2}(?:st|nd|rd|th)?\b|\b\d{1,2}/\d{1,2}\b(?!/)", re.I
)
ROLLING = re.compile(
    r"\brolling\b|\bopen until filled\b|\baccepted year[- ]round\b|\byear[- ]round\b"
    r"|\bongoing basis\b|\bany time\b|\banytime\b",
    re.I,
)
_NUM = r"(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?"
_MULT = r"(?:\s*(?P<mult>million|billion|thousand|mm|m|k|b)\b)?"
MONEY = re.compile(r"(?:\$|\bUSD\s?)\s*" + _NUM + _MULT, re.I)
MONEY_WORDS = re.compile(r"\b" + _NUM + _MULT + r"\s*(?:USD|dollars)\b", re.I)  # "50,000 dollars"
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
    inferred: bool = (
        False  # the page left out the year; code took it from the page (`infer_deadline`)
    )


def _amounts(text: str) -> list[tuple[Money, int, int]]:
    found: list[tuple[Money, int, int]] = []
    matches = [*MONEY.finditer(text), *MONEY_WORDS.finditer(text)]
    for m in sorted(matches, key=lambda m: m.start()):
        if any(s < m.end() and m.start() < e for _, s, e in found):
            continue
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


DATE_CUE = re.compile(r"\b(open(?:s|ing|ed)?|clos(?:e|es|ing)|due|deadline)\b", re.I)


def _opening_date(text: str, start: int, previous_end: int) -> bool:
    cues = list(DATE_CUE.finditer(text, previous_end, start))
    return bool(cues and cues[-1].group().lower().startswith("open"))


def _dates(text: str, *, deadlines_only: bool = False) -> list[date]:
    out: list[tuple[int, int, date]] = []
    taken: list[tuple[int, int]] = []
    for rx in (DATE_NAMED, DATE_DAY_FIRST, DATE_US, DATE_ISO):
        for m in rx.finditer(text):
            if any(s < m.end() and m.start() < e for s, e in taken):
                continue
            month = m.group("month")
            month_no = int(month) if month.isdigit() else MONTHS[month.lower().rstrip(".")]
            year = int(m.group("year"))
            year += 2000 if year < 100 else 0  # "3/3/27"
            try:
                out.append((m.start(), m.end(), date(year, month_no, int(m.group("day")))))
            except ValueError:
                continue
            taken.append((m.start(), m.end()))
    ordered = sorted(out)
    return [
        d
        for i, (start, end, d) in enumerate(ordered)
        if not deadlines_only
        or (
            not _opening_date(text, start, ordered[i - 1][1] if i else 0)
            and not (i + 1 < len(ordered) and WINDOW_TO.fullmatch(text[end : ordered[i + 1][0]]))
        )
    ]


def parse_deadline(quote: str | None, today: date) -> DeadlineParse:
    """The earliest non-opening date on or after `today`. Year-less dates are not parsed."""
    if not quote:
        return DeadlineParse(None)
    dates = _dates(quote)
    rolling = bool(ROLLING.search(quote))
    if rolling and not dates:
        return DeadlineParse(None, rolling=True)
    future = sorted(d for d in _dates(quote, deadlines_only=True) if d >= today)
    yearless = not dates and bool(DATE_YEARLESS.search(quote))
    return DeadlineParse(future[0] if future else None, rolling, dates, yearless)


MONTH_DAY = re.compile(
    r"\b(?P<month>" + _MONTH_RX + r")\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?\b(?!,?\s*\d{4})", re.I
)
WINDOW_TO = re.compile(r"\s*(?:through|thru|until|to|-|\u2013|\u2014)\s*", re.I)
ANNUAL = re.compile(r"\b(?:each|every) year\b|\bannually\b|\byearly\b", re.I)
CYCLE_YEAR = re.compile(
    r"(?<![-\u2013/\d])\b(?P<a>20\d\d)\b(?![-\u2013/]\d)\s+(?:grant\s+|funding\s+)?(?:applications?"
    r"|cycle|round|call for proposals|request for proposals|RFP|grants? program)\b"
    r"|\b(?:grants?|program|cycle|round|fiscal year|FY)\s+(?P<b>20\d\d)\b(?![-\u2013/]\d)",
    re.I,
)


def _month_days(quote: str) -> list[tuple[int, int]]:
    """Year-less `March 1` dates, minus a window's opening date (`March 1 through June 1`)."""
    found = list(MONTH_DAY.finditer(quote))
    out = []
    for i, m in enumerate(found):
        if _opening_date(quote, m.start(), found[i - 1].end() if i else 0):
            continue
        if i + 1 < len(found) and WINDOW_TO.fullmatch(quote[m.end() : found[i + 1].start()]):
            continue
        out.append((MONTHS[m.group("month").lower().rstrip(".")], int(m.group("day"))))
    return out


def cycle_year(pages: list[str]) -> int | None:
    """The one funding-cycle year the pages name (`2027 grant cycle`, `Grant 2027`), else None."""
    years = {int(m.group("a") or m.group("b")) for t in pages for m in CYCLE_YEAR.finditer(t)}
    return years.pop() if len(years) == 1 else None


def infer_deadline(quote: str, pages: list[str], today: date) -> DeadlineParse | None:
    """A year-less deadline gets its year only from the page: the next date when the quote says it
    repeats (`each year`, `annually`), or the page's one cycle year. Never a guess: no year on the
    page, or a past result, gives None (the deadline stays unknown)."""
    days = _month_days(quote) if not _dates(quote) else []
    year = None if ANNUAL.search(quote) else cycle_year(pages)
    if not days or (year is None and not ANNUAL.search(quote)):
        return None
    out = []
    for month, day in days:
        for y in (year,) if year else (today.year, today.year + 1):
            try:
                d = date(y, month, day)
            except ValueError:
                continue
            if d >= today:
                out.append(d)
                break
    if not out:
        return None
    return DeadlineParse(min(out), all_dates=sorted(out), inferred=True)


def has_money(text: str) -> bool:
    """Any amount, USD or not (`€50,000` is an amount quote, just not one code converts)."""
    return bool(MONEY.search(text) or MONEY_WORDS.search(text) or NON_USD.search(text))


def has_money_or_date(sentence: str) -> bool:
    return bool(
        MONEY.search(sentence)
        or MONEY_WORDS.search(sentence)
        or _dates(sentence)
        or DATE_YEARLESS.search(sentence)
    )


# --- Finding the facts on the page when the model's quote is missing or unusable -----------------

_CLAUSE = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9(\"'$])|\n+|\s+\u2022\s+|\s{3,}")
AWARD_WORDS = re.compile(
    r"\bawards?(?::| of| range| ranging| up to| between| amounts?| sizes?)"
    r"|\bgrants? (?:of|range|ranging|sizes?|amounts?|up to|between)"
    r"|\bup to\b|\bmaximum\b|\bmax\.?\s|\branging\b|\branges? from"
    r"|\brequest(?:s|ed)? (?:of|up to|between)"
    r"|\bper (?:organization|applicant|project|grant|year|award|agency|grantee|recipient)\b"
    r"|\bfunding (?:of|amount|level)|\bbetween \$",
    re.I,
)
TOTAL_WORDS = re.compile(
    r"\btotal\b|\btotaling\b|\bavailable\b|\bpool\b|\bbudget\b|\bhas (?:awarded|granted|invested)"
    r"|\b(?:over|more than|nearly|almost) \$|\bin (?:total )?(?:grants|funding|awards)\b"
    r"|\bdistributed\b|\braised\b|\bsince \d{4}|\bendowment\b|\binvest(?:s|ed|ment)\b"
    r"|\bmatch(?:ing)?\b|\bfee\b|\bcost\b|\bsalary\b"
    r"|\b(?:grants|funds|dollars|total) awarded\b|\bawarded (?:to date|since|so far)\b",
    re.I,
)
DEADLINE_WORDS = re.compile(
    r"\bdeadline|\bdue\b|\bclos(?:e|es|ing)\b|\bsubmi(?:t|tted|ssions?)\b|\bno later than\b"
    r"|\bapply by\b|\baccepted (?:until|through|by)\b|\bapplications? (?:open|window|period)\b"
    r"|\bmust be received\b|\bletters? of (?:intent|inquiry)\b|\bLOI\b",
    re.I,
)
PAST_WORDS = re.compile(
    r"\bwere due\b|\bwas due\b|\bclosed\b|\bpast\b|\bprevious\b|\blast year", re.I
)
QUOTE_MAX = 300


@dataclass(frozen=True)
class AwardPick:
    """What code makes of a quote with money in it. `text` is the part naming one award; `total`
    means the wording reads as program totals or cumulative giving, not one award."""

    text: str
    amount: AmountParse
    total: bool


def pick_award(quote: str, context: str = "") -> AwardPick | None:
    """`up to $1 million in grants, ranging from $5,000 to $50,000 per organization` → the
    `$5,000 to $50,000` part. `context` is the page clause around the quote, read for total wording
    when the quote alone has none (`$16.3 million` in "…awards $16.3 million in grants")."""
    for part in re.split(r"[,;]\s+", quote):
        if _amounts(part) and AWARD_WORDS.search(part) and not TOTAL_WORDS.search(part):
            parsed = parse_amount(part)
            if parsed is not None and parsed.max is not None:
                return AwardPick(part.strip(), parsed, False)
    parsed = parse_amount(quote)
    if parsed is None or parsed.max is None:
        return None
    total = bool(TOTAL_WORDS.search(quote)) or bool(
        context and TOTAL_WORDS.search(context) and not AWARD_WORDS.search(context)
    )
    return AwardPick(quote, parsed, total)


def context_of(quote: str, pages: list[str]) -> str:
    """The page clause that contains `quote` (case and spacing ignored), else ""."""
    q = " ".join(quote.lower().split())
    for text in pages:
        for clause in clauses(text):
            if q and q in " ".join(clause.lower().split()):
                return clause
    return ""


@dataclass(frozen=True)
class Found:
    """A fact code found on the page itself: the clause it came from (a real quote) and its page."""

    text: str
    page: int


def clauses(text: str) -> list[str]:
    return [c.strip() for c in _CLAUSE.split(text) if c and c.strip()]


def _clip(clause: str, start: int, end: int) -> str:
    """At most `QUOTE_MAX` characters of `clause`, centred on [start, end)."""
    if len(clause) <= QUOTE_MAX:
        return clause
    lo = max(0, min(start - 120, len(clause) - QUOTE_MAX))
    return clause[lo : lo + QUOTE_MAX].strip()


def find_amount(pages: list[str]) -> tuple[Found, AmountParse] | None:
    """The best per-award amount stated on the pages: a clause with a USD figure and award wording,
    and none of the wording of program totals or costs. Earliest wins on ties."""
    best: tuple[int, Found, AmountParse] | None = None
    for page_no, text in enumerate(pages, start=1):
        for clause in clauses(text):
            if not _amounts(clause) or not AWARD_WORDS.search(clause):
                continue
            pick = pick_award(clause, clause)
            if pick is None or pick.total or not AWARD_WORDS.search(pick.text):
                continue
            found = _amounts(pick.text)
            quote = _clip(pick.text, found[0][1], found[-1][2]) if found else pick.text
            score = len(AWARD_WORDS.findall(pick.text))
            if best is None or score > best[0]:
                best = (score, Found(quote, page_no), pick.amount)
    return (best[1], best[2]) if best else None


def find_deadline(pages: list[str], today: date) -> tuple[Found, DeadlineParse] | None:
    """The earliest future date the pages give as a deadline, else one `infer_deadline` can date
    from the page, else a rolling statement.

    Only clauses with deadline wording count. Past dates found this way never mark a grant expired:
    pages often mention last cycle's dates."""
    dated: tuple[date, Found] | None = None
    inferred: tuple[DeadlineParse, Found] | None = None
    rolling: Found | None = None
    for page_no, text in enumerate(pages, start=1):
        for clause in clauses(text):
            if not DEADLINE_WORDS.search(clause) and not ROLLING.search(clause):
                continue
            if PAST_WORDS.search(clause):
                continue
            future = [d for d in _dates(clause, deadlines_only=True) if d >= today]
            if future and DEADLINE_WORDS.search(clause):
                if dated is None or min(future) < dated[0]:
                    dated = (min(future), Found(_clip(clause, 0, len(clause)), page_no))
            elif DEADLINE_WORDS.search(clause) and (guess := infer_deadline(clause, pages, today)):
                if inferred is None or (guess.date or today) < (inferred[0].date or today):
                    inferred = (guess, Found(_clip(clause, 0, len(clause)), page_no))
            elif rolling is None and ROLLING.search(clause) and not _dates(clause):
                rolling = Found(_clip(clause, 0, len(clause)), page_no)
    if dated:
        return dated[1], parse_deadline(dated[1].text, today)
    if inferred:
        return inferred[1], inferred[0]
    if rolling:
        return rolling, DeadlineParse(None, rolling=True)
    return None
