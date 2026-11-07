from datetime import date

import pytest
from hope_core.money import Money
from hope_core.schemas.agency_profile import (
    IndirectRate,
    LastAudit,
    Legal,
    SamRegistration,
)
from hope_core.testing.factories import agency_profile
from hope_profile.diff import diff, merge_patch
from hope_profile.memory import chunk_text
from hope_profile.validators import (
    completeness,
    derive_budget_band,
    ein_errors,
    fiscal_year_bounds,
    fiscal_year_for,
    profile_errors,
    stale_fields,
    uei_errors,
)

TODAY = date(2026, 11, 7)


@pytest.mark.parametrize(
    ("ein", "ok"),
    [("12-3456789", True), ("123456789", False), ("07-1234567", False), ("9-12345678", False)],
)
def test_ein(ein: str, ok: bool) -> None:
    assert (ein_errors(ein) == []) is ok


@pytest.mark.parametrize(
    ("uei", "ok"),
    [
        (None, True),
        ("J7M9HPTGJ1S9", True),
        ("0ABCDEFGHJK1", False),
        ("ABCDEFGHIJK1", False),
        ("ABC", False),
        ("abcdefghjkl1", False),
    ],
)
def test_uei(uei: str | None, ok: bool) -> None:
    assert (uei_errors(uei) == []) is ok


def test_fiscal_year_math() -> None:
    assert fiscal_year_bounds("06-30", 2027) == (date(2026, 7, 1), date(2027, 6, 30))
    assert fiscal_year_bounds("12-31", 2026) == (date(2026, 1, 1), date(2026, 12, 31))
    assert fiscal_year_bounds("02-29", 2027) == (date(2026, 3, 1), date(2027, 2, 28))
    assert fiscal_year_for("06-30", date(2026, 6, 30)) == 2026
    assert fiscal_year_for("06-30", date(2026, 7, 1)) == 2027
    with pytest.raises(ValueError):
        fiscal_year_bounds("02-30", 2026)


@pytest.mark.parametrize(
    ("major", "band"),
    [("249999.99", "<250k"), ("250000", "250k-1m"), ("1850000", "1m-5m"), ("30000000", ">25m")],
)
def test_budget_band(major: str, band: str) -> None:
    assert derive_budget_band(Money.from_decimal(major)) == band
    assert derive_budget_band(Money.from_decimal(major, "EUR")) is None


def test_profile_errors() -> None:
    profile = agency_profile()
    assert profile_errors(profile, TODAY) == []
    profile.financials.fiscal_year_end = "02-30"
    assert "fiscal_year_end" in profile_errors(profile, TODAY)[0]
    profile = agency_profile()
    profile.financials.last_audit = LastAudit(type="financial_audit", fiscal_year=2029)
    profile.financials.indirect_rate = IndirectRate(type="negotiated_nicra")
    assert len(profile_errors(profile, TODAY)) == 2


@pytest.mark.parametrize(
    ("days", "threshold"),
    [(61, None), (60, "60d"), (31, "60d"), (30, "30d"), (7, "7d"), (-1, "expired")],
)
def test_sam_expiry_thresholds(days: int, threshold: str | None) -> None:
    profile = agency_profile()
    profile.legal.sam_registration = SamRegistration(
        status="active", expires_on=date.fromordinal(TODAY.toordinal() + days)
    )
    alerts = stale_fields(profile, TODAY)
    assert [a.threshold for a in alerts] == ([threshold] if threshold else [])
    if threshold:
        assert alerts[0].reason == ("sam_expired" if days < 0 else "sam_expiring")


def test_nicra_and_audit_staleness() -> None:
    profile = agency_profile()
    profile.financials.indirect_rate = IndirectRate(
        type="negotiated_nicra", rate_bps=2500, base="MTDC", agreement_expires_on=date(2026, 11, 1)
    )
    # FY2025 with a 06-30 year end closed 2025-06-30; 18 months later is 2026-12-30.
    profile.financials.last_audit = LastAudit(type="single_audit", fiscal_year=2025)
    assert [a.reason for a in stale_fields(profile, TODAY)] == ["nicra_expired"]
    profile.financials.last_audit = LastAudit(type="single_audit", fiscal_year=2024)
    reasons = [a.reason for a in stale_fields(profile, TODAY)]
    assert reasons == ["nicra_expired", "audit_outdated"]


def test_completeness() -> None:
    profile = agency_profile()
    report = completeness(profile)
    assert 0 < report.score < 100
    assert "legal.uei" in report.missing
    assert "programs" not in report.missing
    assert "programs.outcomes" in report.missing
    profile.legal = Legal.model_validate({**profile.legal.model_dump(), "uei": "J7M9HPTGJ1S9"})
    assert completeness(profile).score > report.score


def test_merge_patch_and_diff() -> None:
    old = {"version": 1, "legal": {"ein": "1", "dba": []}, "mission": {"focus_areas": ["a"]}}
    new = merge_patch(old, {"version": 9, "legal": {"dba": None}, "mission": {"x": 1}})
    assert new == {"version": 9, "legal": {"ein": "1"}, "mission": {"focus_areas": ["a"], "x": 1}}
    changes = diff(old, new)
    assert [(c.path, c.protected) for c in changes] == [("legal.dba", True), ("mission.x", False)]


def test_chunk_text_packs_paragraphs() -> None:
    text = "First para.\n\nSecond para.\n\n" + "Long sentence here. " * 30
    chunks = chunk_text(text, max_chars=120)
    assert chunks[0].startswith("First para.\nSecond para.\nLong sentence")
    assert all(len(c) <= 120 for c in chunks)
    assert chunk_text("  \n\n ") == []
