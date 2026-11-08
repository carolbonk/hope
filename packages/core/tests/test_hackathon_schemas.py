from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from hope_core.money import Money
from hope_core.schemas import (
    AgencyProfile,
    Citation,
    DiscoveryJob,
    DiscoveryProgress,
    GrantCandidate,
    MeView,
    UserView,
)
from hope_core.schemas.export import CONTRACTS
from hope_core.testing.factories import agency_profile
from pydantic import ValidationError

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"
NOW = datetime(2026, 11, 1, tzinfo=UTC)


def candidate(**overrides: object) -> GrantCandidate:
    data: dict[str, object] = {
        "grant_id": uuid4(),
        "title": "Rural Health Access Fund",
        "funder": "Cascade Community Foundation",
        "url": "https://cascadecf.example.org/grants/rural-health-access-fund",
        "summary": "Supports rural clinics [c1].",
        "amount_text": "up to $50,000",
        "amount_max": Money(amount_minor=5_000_000),
        "deadline": date(2027, 3, 31),
        "fit_score": 82,
        "citations": [Citation(citation_id="c1", kind="web", quote="Awards up to $50,000")],
        "discovered_at": NOW,
    }
    data.update(overrides)
    return GrantCandidate.model_validate(data)


def test_contracts_validate_and_round_trip() -> None:
    progress = DiscoveryProgress(queries_total=3, queries_done=1, current_step="Searching")
    job = DiscoveryJob(job_id=uuid4(), status="running", progress=progress, started_at=NOW)
    me = MeView(
        user_id=uuid4(),
        email="a@b.org",
        display_name="A",
        agency_id=uuid4(),
        onboarding_complete=False,
    )
    for model in (
        candidate(),
        job,
        me,
        UserView(user_id=uuid4(), email="a@b.org", display_name="A"),
    ):
        assert type(model).model_validate_json(model.model_dump_json()) == model


def test_amount_max_is_integer_minor_units() -> None:
    dumped = candidate().model_dump(mode="json")
    assert dumped["amount_max"]["amount_minor"] == 5_000_000
    assert isinstance(dumped["amount_max"]["amount_minor"], int)
    with pytest.raises(ValidationError):
        candidate(amount_max={"amount_minor": 12.5, "currency": "USD"})


def test_candidate_rejects_bad_values() -> None:
    with pytest.raises(ValidationError):
        candidate(fit_score=101)
    with pytest.raises(ValidationError):
        candidate(status="archived")
    with pytest.raises(ValidationError):
        Citation(citation_id="c1", kind="web", quote="x" * 501)


def test_profile_gains_hackathon_fields() -> None:
    profile = agency_profile()
    assert profile.service_area == [] and profile.mission.values == []
    data = profile.model_dump(mode="json")
    data["service_area"] = ["Chelan County, WA"]
    data["mission"]["values"] = ["dignity"]
    data["legal"].update(
        hq_city="Wenatchee", hq_state="WA", website="https://riverbend.example.org"
    )
    restored = AgencyProfile.model_validate(data)
    assert restored.service_area == ["Chelan County, WA"]
    assert restored.legal.hq_city == "Wenatchee"


@pytest.mark.parametrize(
    "name",
    ["citation", "discovery-progress", "discovery-job", "grant-candidate", "user-view", "me-view"],
)
def test_exported_and_typed(name: str) -> None:
    assert name in CONTRACTS
    exported = json.loads((SCHEMAS / "json" / f"{name}.schema.json").read_text())
    exported.pop("$id"), exported.pop("$schema")
    assert exported == CONTRACTS[name].model_json_schema()
    ts = (SCHEMAS / "ts" / "src" / "index.ts").read_text()
    assert f"export interface {CONTRACTS[name].__name__} " in ts
