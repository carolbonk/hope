"""Deterministic profile checks: identifiers, fiscal-year math, derived fields, staleness."""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from hope_core.money import Money
from hope_core.schemas.agency_profile import AgencyProfile, BudgetBand
from hope_core.schemas.hitl import Gate

from hope_profile.contracts import CompletenessReport, StaleFieldAlert

EIN_RE = re.compile(r"^(\d{2})-\d{7}$")
# IRS campus prefixes that have never been assigned.
INVALID_EIN_PREFIXES = frozenset(
    {"00", "07", "08", "09", "17", "18", "19", "28", "29", "49", "69", "70", "78", "79", "89"}
    | {"96", "97"}
)
# GSA UEI rules: 12 chars, no letters I or O, first char not 0. The check-digit algorithm is
# not public, so the SAM.gov entity lookup is the source of truth for the last character.
UEI_RE = re.compile(r"^[1-9A-HJ-NP-Z][0-9A-HJ-NP-Z]{11}$")

STALE_THRESHOLDS_DAYS = (7, 30, 60)
AUDIT_MAX_AGE_MONTHS = 18
DEFAULT_HITL0_ROLES = ("org_admin", "finance_director")

_BANDS: tuple[tuple[int, BudgetBand], ...] = (
    (250_000_00, "<250k"),
    (1_000_000_00, "250k-1m"),
    (5_000_000_00, "1m-5m"),
    (25_000_000_00, "5m-25m"),
)


def ein_errors(ein: str) -> list[str]:
    match = EIN_RE.match(ein)
    if not match:
        return ["legal.ein must look like 12-3456789"]
    if match.group(1) in INVALID_EIN_PREFIXES:
        return [f"legal.ein prefix {match.group(1)} is not an IRS-assigned prefix"]
    return []


def uei_errors(uei: str | None) -> list[str]:
    if uei is None or UEI_RE.match(uei):
        return []
    return ["legal.uei must be 12 characters A-Z/0-9, without I or O, not starting with 0"]


def parse_fiscal_year_end(value: str) -> tuple[int, int]:
    """Return (month, day) for an 'MM-DD' fiscal-year end. Feb 29 is allowed (leap-year aware)."""
    month, day = (int(part) for part in value.split("-"))
    if not 1 <= month <= 12 or not 1 <= day <= calendar.monthrange(2024, month)[1]:
        raise ValueError(f"{value} is not a calendar date")
    return month, day


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def fiscal_year_bounds(fiscal_year_end: str, fiscal_year: int) -> tuple[date, date]:
    """FYs are named by the calendar year they end in: FY2027 with 06-30 ends 2027-06-30."""
    month, day = parse_fiscal_year_end(fiscal_year_end)
    end = _clamped(fiscal_year, month, day)
    start = _clamped(fiscal_year - 1, month, day) + timedelta(days=1)
    return start, end


def fiscal_year_for(fiscal_year_end: str, on: date) -> int:
    month, day = parse_fiscal_year_end(fiscal_year_end)
    return on.year if on <= _clamped(on.year, month, day) else on.year + 1


def add_months(day: date, months: int) -> date:
    index = day.month - 1 + months
    return _clamped(day.year + index // 12, index % 12 + 1, day.day)


def derive_budget_band(budget: Money) -> BudgetBand | None:
    if budget.currency != "USD":
        return None
    for ceiling, band in _BANDS:
        if budget.amount_minor < ceiling:
            return band
    return ">25m"


def hitl0_roles(profile: AgencyProfile) -> tuple[str, ...]:
    for rule in profile.approval_hierarchy:
        if rule.gate == Gate.PROFILE_COMMIT:
            return tuple(rule.approver_roles)
    return DEFAULT_HITL0_ROLES


def profile_errors(profile: AgencyProfile, today: date) -> list[str]:
    errors = ein_errors(profile.legal.ein) + uei_errors(profile.legal.uei)
    fin = profile.financials
    try:
        current_fy = fiscal_year_for(fin.fiscal_year_end, today)
    except ValueError as exc:
        return [*errors, f"financials.fiscal_year_end: {exc}"]
    if fin.annual_operating_budget.amount_minor < 0:
        errors.append("financials.annual_operating_budget must not be negative")
    audit_fy = fin.last_audit.fiscal_year if fin.last_audit else None
    if audit_fy is not None and audit_fy > current_fy:
        errors.append(f"financials.last_audit.fiscal_year {audit_fy} is after FY{current_fy}")
    rate = fin.indirect_rate
    if rate and rate.type == "negotiated_nicra" and rate.rate_bps is None:
        errors.append("financials.indirect_rate.rate_bps is required for a NICRA")
    return errors


def _expiry_alert(
    profile: AgencyProfile, field: str, prefix: str, expires_on: date, today: date
) -> StaleFieldAlert | None:
    days = (expires_on - today).days
    if days < 0:
        threshold, reason = "expired", f"{prefix}_expired"
    else:
        hit = next((t for t in STALE_THRESHOLDS_DAYS if days <= t), None)
        if hit is None:
            return None
        threshold, reason = f"{hit}d", f"{prefix}_expiring"
    return StaleFieldAlert.model_validate(
        {
            "agency_id": profile.agency_id,
            "field": field,
            "reason": reason,
            "threshold": threshold,
            "ref_date": expires_on,
            "days_remaining": days,
        }
    )


def stale_fields(profile: AgencyProfile, today: date) -> list[StaleFieldAlert]:
    alerts: list[StaleFieldAlert | None] = []
    sam = profile.legal.sam_registration
    if sam and sam.expires_on:
        alerts.append(
            _expiry_alert(
                profile, "legal.sam_registration.expires_on", "sam", sam.expires_on, today
            )
        )
    rate = profile.financials.indirect_rate
    if rate and rate.type == "negotiated_nicra" and rate.agreement_expires_on:
        alerts.append(
            _expiry_alert(
                profile,
                "financials.indirect_rate.agreement_expires_on",
                "nicra",
                rate.agreement_expires_on,
                today,
            )
        )
    audit = profile.financials.last_audit
    if audit and audit.type != "none" and audit.fiscal_year is not None:
        _, fy_end = fiscal_year_bounds(profile.financials.fiscal_year_end, audit.fiscal_year)
        if add_months(fy_end, AUDIT_MAX_AGE_MONTHS) < today:
            alerts.append(
                StaleFieldAlert(
                    agency_id=profile.agency_id,
                    field="financials.last_audit",
                    reason="audit_outdated",
                    threshold="18m",
                    ref_date=fy_end,
                )
            )
    return [alert for alert in alerts if alert is not None]


COMPLETENESS_FIELDS: tuple[str, ...] = (
    "legal.uei",
    "legal.sam_registration",
    "legal.state_of_incorporation",
    "mission.vision_statement",
    "mission.theory_of_change",
    "mission.focus_areas",
    "mission.ntee_codes",
    "financials.indirect_rate",
    "financials.fringe_rate_bps",
    "financials.last_audit",
    "programs",
    "programs.outcomes",
    "programs.target_demographics",
    "grant_history",
    "capacity",
    "compliance_calendar",
)


def _present(value: object, rest: list[str]) -> bool:
    if isinstance(value, list):
        return any(_present(item, rest) for item in value)
    if not rest:
        return value not in (None, "", {})
    return isinstance(value, dict) and _present(value.get(rest[0]), rest[1:])


def completeness(profile: AgencyProfile) -> CompletenessReport:
    data = profile.model_dump(mode="json")
    missing = [p for p in COMPLETENESS_FIELDS if not _present(data, p.split("."))]
    filled = len(COMPLETENESS_FIELDS) - len(missing)
    return CompletenessReport(score=round(100 * filled / len(COMPLETENESS_FIELDS)), missing=missing)
