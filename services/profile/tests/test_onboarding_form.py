"""H1 form model, form <-> profile mapping and completeness (no database)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.testing.factories import agency_profile
from hope_profile.onboarding import (
    BAND_MIDPOINT_MINOR,
    ProfileForm,
    ProfilePatchBody,
    form_completeness,
    form_to_profile,
    merge_sections,
    profile_to_form,
    validation_errors,
)
from pydantic import ValidationError

MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks" / "w2"
NOW = datetime(2026, 11, 7, 21, 40, tzinfo=UTC)


def demo() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / "profile.put" / "request.json").read_text())
    return data


def errors_for(data: dict[str, Any]) -> list[dict[str, str]]:
    with pytest.raises(ValidationError) as caught:
        ProfileForm.model_validate(data)
    return [e.model_dump() for e in validation_errors(caught.value)]


def to_profile(form: ProfileForm, base: AgencyProfile | None = None) -> AgencyProfile:
    ids = (base.tenant_id, base.agency_id) if base else (uuid4(), uuid4())
    data = form_to_profile(form, base, tenant_id=ids[0], agency_id=ids[1], now=NOW)
    return AgencyProfile.model_validate(data | {"version": 1})


def test_form_round_trip() -> None:
    form = ProfileForm.model_validate(demo())
    profile = to_profile(form)
    assert profile_to_form(profile) == form
    assert profile.legal.hq_city == "Wenatchee" and profile.legal.hq_state == "WA"
    assert profile.mission.ntee_codes == ["E32", "F30"]
    assert profile.mission.focus_areas == ["Community Clinics", "Mental Health Treatment"]


def test_exact_budget_is_minor_units_with_exact_provenance() -> None:
    profile = to_profile(ProfileForm.model_validate(demo()))
    budget = profile.financials.annual_operating_budget
    assert budget.amount_minor == 3_120_000 * 100 and budget.currency == "USD"
    provenance = profile.financials.provenance
    assert provenance and provenance.source == "user_input" and provenance.source_ref == "exact"
    assert profile.financials.budget_band in (None, "1m-5m")


def test_band_only_budget_uses_midpoint_and_reads_back_as_band_only() -> None:
    data = demo()
    data["budget"] = {"budget_band": "250k-1m", "annual_operating_budget_usd": None}
    form = ProfileForm.model_validate(data)
    profile = to_profile(form)
    assert profile.financials.annual_operating_budget.amount_minor == BAND_MIDPOINT_MINOR["250k-1m"]
    assert profile.financials.provenance
    assert profile.financials.provenance.source_ref == "budget_band_midpoint"
    back = profile_to_form(profile)
    assert back.budget.annual_operating_budget_usd is None
    assert back.budget.budget_band == "250k-1m"


def test_programs_get_slug_ids_and_base_fields_survive() -> None:
    base = agency_profile()
    data = demo()
    data["programs"][0]["program_id"] = None
    profile = to_profile(ProfileForm.model_validate(data), base)
    assert profile.programs[0].program_id == "prg-mobile-dental-clinic"
    assert profile.agency_id == base.agency_id
    assert profile.legal.uei == base.legal.uei
    assert profile.data_governance == base.data_governance
    assert profile.approval_hierarchy == base.approval_hierarchy


@pytest.mark.parametrize(
    ("path", "value", "field", "code"),
    [
        (("basics", "ein"), "00-1234567", "basics.ein", "invalid_ein_prefix"),
        (("basics", "ein"), "123456789", "basics.ein", "invalid_format"),
        (("basics", "hq_state"), "ZZ", "basics.hq_state", "unknown_state"),
        (("basics", "legal_name"), "A", "basics.legal_name", "too_short"),
        (("basics", "service_area"), [], "basics.service_area", "required"),
        (("mission", "mission_statement"), "too short", "mission.mission_statement", "too_short"),
        (("ntee_codes",), ["E32", "E32"], "ntee_codes", "duplicate"),
        (("ntee_codes",), ["Q99Z"], "ntee_codes", "unknown_ntee_code"),
        (("ntee_codes",), ["E32", "F30", "O50", "K31"], "ntee_codes", "too_many"),
        (("ntee_codes",), [], "ntee_codes", "required"),
        (("budget", "fiscal_year_end"), "13-01", "budget.fiscal_year_end", "invalid_format"),
        (("programs",), [], "programs", "required"),
    ],
)
def test_validation_errors_use_form_paths_and_stable_codes(
    path: tuple[str, ...], value: Any, field: str, code: str
) -> None:
    data = demo()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    errors = errors_for(data)
    assert {"field": field, "code": code} in [
        {"field": e["field"], "code": e["code"]} for e in errors
    ]
    assert all(e["message"] for e in errors)


def test_missing_section_and_unknown_key_are_errors() -> None:
    data = demo()
    del data["budget"]
    assert {"field": "budget", "code": "required"} in [
        {"field": e["field"], "code": e["code"]} for e in errors_for(data)
    ]
    with pytest.raises(ValidationError):
        ProfileForm.model_validate(demo() | {"extra": 1})


def test_merge_sections_replaces_only_sent_sections() -> None:
    form = ProfileForm.model_validate(demo())
    patch = ProfilePatchBody.model_validate({"ntee_codes": ["K31"]})
    merged = merge_sections(form, patch)
    assert merged.ntee_codes == ["K31"]
    assert merged.basics == form.basics and merged.programs == form.programs


def test_completeness() -> None:
    expected = json.loads((MOCKS / "profile.get" / "ok.json").read_text())["body"]
    form = ProfileForm.model_validate(expected["form"])
    assert form_completeness(form).model_dump() == expected["completeness"]


def test_completeness_full_and_required_only() -> None:
    data = demo()
    for program in data["programs"]:
        program["age_range"] = "0-99"
        program["annual_served"] = 10
    assert form_completeness(ProfileForm.model_validate(data)).score == 100
    data["basics"]["website"] = None
    data["mission"]["vision_statement"] = None
    report = form_completeness(ProfileForm.model_validate(data))
    assert report.missing == ["basics.website", "mission.vision_statement"]
    assert report.score == round(100 * 10 / 12)
