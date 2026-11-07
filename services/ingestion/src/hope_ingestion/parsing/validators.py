"""Deterministic validators. Models only point at quotes; code turns quotes into typed values
(dates, timezones, Money, basis points). No money amount ever comes from a model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from hope_core.money import Money
from hope_core.schemas.grant_opportunity import CostShare, IndirectCostPolicy

DEFAULT_TZ = "America/New_York"
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
TZ_ALIASES = {
    "America/New_York": ("et", "est", "edt", "eastern"),
    "America/Chicago": ("ct", "cst", "cdt", "central"),
    "America/Denver": ("mt", "mst", "mdt", "mountain"),
    "America/Los_Angeles": ("pt", "pst", "pdt", "pacific"),
    "America/Anchorage": ("akt", "akst", "akdt", "alaska"),
    "Pacific/Honolulu": ("hst", "hawaii"),
    "UTC": ("utc", "gmt", "z"),
}
TZ_LOOKUP = {alias: tz for tz, aliases in TZ_ALIASES.items() for alias in aliases}

DATE_NAMED = re.compile(
    r"\b(?P<month>" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<year>\d{4})\b",
    re.I,
)
DATE_US = re.compile(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})\b")
DATE_ISO = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b")
TIME_12H = re.compile(
    r"\b(?P<h>\d{1,2})(?::(?P<m>\d{2}))?(?::\d{2})?\s*(?P<ampm>[ap])\.?\s*m\b\.?", re.I
)
TIME_24H = re.compile(r"\b(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)\b(?!\s*[ap]\.?\s*m)", re.I)
TIME_WORDS = {"noon": time(12, 0), "midnight": time(23, 59)}
TZ_TOKEN = re.compile(
    r"\b(" + "|".join(sorted(TZ_LOOKUP, key=len, reverse=True)) + r")\b(?:\s+time)?", re.I
)
IANA = re.compile(r"\b([A-Z][a-z]+/[A-Z][A-Za-z_]+)\b")

MONEY = re.compile(
    r"(?:\$|\bUSD\s?)\s*(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?"
    r"\s*(?P<mult>million|billion|thousand|mm|m|k|b)?\b",
    re.I,
)
MULTIPLIERS = {"thousand": 10**3, "k": 10**3, "million": 10**6, "m": 10**6, "mm": 10**6}
MULTIPLIERS |= {"billion": 10**9, "b": 10**9}
PERCENT = re.compile(r"(?P<pct>\d{1,3}(?:\.\d+)?)\s*(?:%|percent)", re.I)
NEGATED = re.compile(
    r"\b(not|no|never)\b[^.;]{0,30}\b(allow\w*|permit\w*|reimburs\w*|charge\w*|fund\w*)\b"
    r"|\bunallowable\b|\bmay not\b|\bprohibited\b",
    re.I,
)
AFFIRMED = re.compile(r"\b(allow\w*|permit\w*|may (?:be )?(?:charged|requested|include))\b", re.I)
NO_COST_SHARE = re.compile(
    r"\b(no|not)\b[^.;]{0,30}\b(cost[- ]?shar\w*|match\w*)\b|\b(cost[- ]?shar\w*|match\w*)\b"
    r"[^.;]{0,30}\b(is |are )?not required\b",
    re.I,
)
COST_SHARE = re.compile(r"\bcost[- ]?shar\w*|\bmatch(?:ing)?\b", re.I)
PAGE_LIMIT = re.compile(
    r"\b(?P<n>\d{1,3})[- ]page\b|\bnot (?:to )?exceed (?P<m>\d{1,3}) pages\b", re.I
)
FORMS = re.compile(r"\bSF[- ]?(?:424[A-D]?|LLL|PPR|425)\b|\bGG[_ ]Lobbying\b", re.I)


@dataclass(frozen=True)
class ParsedDeadline:
    value: datetime
    timezone: str
    has_time: bool
    timezone_assumed: bool

    @property
    def local_date(self) -> date:
        return self.value.astimezone(ZoneInfo(self.timezone)).date()


def _find_date(text: str) -> date | None:
    for rx in (DATE_NAMED, DATE_US, DATE_ISO):
        m = rx.search(text)
        if not m:
            continue
        month = m.group("month")
        month_no = MONTHS[month.lower().rstrip(".")] if not month.isdigit() else int(month)
        try:
            return date(int(m.group("year")), month_no, int(m.group("day")))
        except ValueError:
            return None
    return None


def _find_time(text: str) -> time | None:
    if m := TIME_12H.search(text):
        hour = int(m.group("h")) % 12 + (12 if m.group("ampm").lower() == "p" else 0)
        return time(hour, int(m.group("m") or 0))
    if m := TIME_24H.search(text):
        return time(int(m.group("h")), int(m.group("m")))
    lowered = text.lower()
    return next((t for word, t in TIME_WORDS.items() if word in lowered), None)


def find_timezone(text: str) -> str | None:
    if m := IANA.search(text):
        return m.group(1)
    if m := TZ_TOKEN.search(text):
        return TZ_LOOKUP[m.group(1).lower()]
    return None


def parse_deadline(text: str, default_tz: str | None = None) -> ParsedDeadline | None:
    """Date-only values become 23:59 local time (blueprint 8.5); callers flag them."""
    day = _find_date(text)
    if day is None:
        return None
    clock = _find_time(text)
    tz = find_timezone(text)
    zone = tz or default_tz or DEFAULT_TZ
    value = datetime.combine(day, clock or time(23, 59), tzinfo=ZoneInfo(zone))
    return ParsedDeadline(value, zone, clock is not None, tz is None)


def parse_money(text: str) -> Money | None:
    m = MONEY.search(text)
    if not m:
        return None
    major = Decimal(m.group("num").replace(",", "") + (m.group("frac") or ""))
    mult = (m.group("mult") or "").lower()
    if mult in ("m", "b", "k") and not re.search(r"\d\s*" + mult + r"\b", m.group(0), re.I):
        mult = ""
    return Money.from_decimal(major * MULTIPLIERS.get(mult, 1))


def parse_percent_bps(text: str) -> int | None:
    m = PERCENT.search(text)
    return int((Decimal(m.group("pct")) * 100).to_integral_value()) if m else None


def parse_indirect(text: str) -> IndirectCostPolicy | None:
    lowered = text.lower()
    if "modified total direct" in lowered or "mtdc" in lowered:
        base = "MTDC"
    elif "total direct" in lowered or re.search(r"\btdc\b", lowered):
        base = "TDC"
    elif "salaries and wages" in lowered:
        base = "salaries_wages"
    else:
        base = "unspecified"
    cap = parse_percent_bps(text)
    if NEGATED.search(text) and cap is None:
        return IndirectCostPolicy(allowed=False, base=base)
    if cap is None and not AFFIRMED.search(text):
        return None
    return IndirectCostPolicy(allowed=True, cap_bps=cap, base=base)


def parse_cost_share(text: str) -> CostShare | None:
    if NO_COST_SHARE.search(text):
        return CostShare(required=False)
    if not COST_SHARE.search(text):
        return None
    in_kind = True if re.search(r"in[- ]kind", text, re.I) else None
    return CostShare(required=True, ratio_bps=parse_percent_bps(text), in_kind_allowed=in_kind)


def parse_int(text: str) -> int | None:
    m = re.search(r"\b(\d{1,4})\b", text.replace(",", ""))
    return int(m.group(1)) if m else None


def parse_page_limit(text: str) -> float | None:
    m = PAGE_LIMIT.search(text)
    return float(m.group("n") or m.group("m")) if m else None


def find_forms(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in FORMS.finditer(text):
        form = m.group(0).upper()
        form = re.sub(r"^SF[- ]?", "SF-", form) if form.startswith("SF") else form.replace(" ", "_")
        seen.setdefault(form, None)
    return list(seen)
