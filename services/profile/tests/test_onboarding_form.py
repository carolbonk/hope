from __future__ import annotations

import json
from pathlib import Path

from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.settings import get_settings
from hope_profile.onboarding import (
    ProfileForm,
    form_completeness,
    form_json,
    form_to_profile,
    profile_to_form,
)

MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks" / "w2"


def demo() -> ProfileForm:
    data = json.loads((MOCKS / "profile.put" / "request.json").read_text())
    return ProfileForm.model_validate(data)


def test_completeness() -> None:
    expected = json.loads((MOCKS / "profile.get" / "ok.json").read_text())["body"]["completeness"]
    assert form_completeness(demo()).model_dump() == expected
    bare = demo().model_copy(deep=True)
    bare.basics.website = None
    bare.mission.values = []
    bare.budget.annual_operating_budget_usd = None
    report = form_completeness(bare)
    assert report.score == round(100 * 8 / 12)
    assert report.missing[:3] == [
        "basics.website",
        "mission.values",
        "budget.annual_operating_budget_usd",
    ]


def test_form_round_trip() -> None:
    settings = get_settings()
    form = demo()
    data = form_to_profile(form, None, settings)
    profile = AgencyProfile.model_validate(data)
    assert profile.financials.annual_operating_budget.amount_minor == 312_000_000
    assert profile.mission.focus_areas == ["Community Clinics", "Mental Health Treatment"]
    assert form_json(profile_to_form(profile)) == form_json(form)

    form.programs[0].program_id = None
    again = AgencyProfile.model_validate(form_to_profile(form, profile, settings))
    assert again.programs[0].program_id == "prg-mobile-dental-clinic"
    assert [p.program_id for p in again.programs][1] == "prg-chw"
