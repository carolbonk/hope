from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import psycopg
import pytest
from hope_core.settings import get_settings

pytestmark = pytest.mark.db

MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks" / "w2"


def demo_form() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / "profile.put" / "request.json").read_text())
    return data


def put(client: Any, form: dict[str, Any], etag: str | None = None) -> Any:
    headers = {"If-Match": etag} if etag else {}
    return client.put("/v1/profile", json=form, headers=headers)


def stored(migrated_db: str) -> dict[str, Any]:
    with psycopg.connect(migrated_db) as conn:
        row = conn.execute(
            "SELECT profile FROM agency_profile_versions WHERE agency_id = %s"
            " ORDER BY version DESC LIMIT 1",
            (get_settings().agency_id,),
        ).fetchone()
    assert row is not None
    profile: dict[str, Any] = row[0]
    return profile


def test_put_creates_profile_with_defaults(signed_in: Any, migrated_db: str) -> None:
    created = put(signed_in, demo_form())
    assert created.status_code == 201, created.text
    assert created.headers["ETag"] == '"1"'
    body = created.json()
    assert body["version"] == 1 and body["updated_by"] == "demo@hope.org"
    assert body["onboarding_complete"] is True
    assert body["form"] == demo_form()
    assert body["ntee_labels"] == {"E32": "Community Clinics", "F30": "Mental Health Treatment"}
    profile = stored(migrated_db)
    assert profile["legal"]["hq_city"] == "Wenatchee" and profile["legal"]["hq_state"] == "WA"
    assert profile["legal"]["state_of_incorporation"] == "WA"
    assert profile["approval_hierarchy"] == [
        {
            "gate": "HITL-0",
            "approver_roles": ["admin"],
            "condition": None,
            "min_approvals": 1,
            "sla_hours": None,
            "escalate_to_role": None,
        }
    ]
    assert profile["financials"]["annual_operating_budget"] == {
        "amount_minor": 312_000_000,
        "currency": "USD",
    }
    me = signed_in.get("/v1/me").json()
    assert me["onboarding_complete"] is True
    got = signed_in.get("/v1/profile")
    assert got.status_code == 200 and got.json() == body


def test_budget_band_midpoint_and_exact(signed_in: Any, migrated_db: str) -> None:
    form = demo_form()
    form["budget"] = {"budget_band": "250k-1m", "annual_operating_budget_usd": None}
    created = put(signed_in, form)
    assert created.status_code == 201
    assert created.json()["form"]["budget"] == {
        "budget_band": "250k-1m",
        "annual_operating_budget_usd": None,
        "fiscal_year_end": "12-31",
    }
    fin = stored(migrated_db)["financials"]
    assert fin["annual_operating_budget"]["amount_minor"] == 50_000_000
    assert fin["budget_band"] == "250k-1m"
    assert fin["provenance"]["source_ref"] == "budget_band_midpoint"

    form["budget"] = {"budget_band": "1m-5m", "annual_operating_budget_usd": 1_234_567}
    saved = put(signed_in, form, created.headers["ETag"])
    assert saved.status_code == 200
    assert saved.json()["form"]["budget"]["annual_operating_budget_usd"] == 1_234_567
    fin = stored(migrated_db)["financials"]
    assert fin["annual_operating_budget"]["amount_minor"] == 123_456_700
    assert fin["provenance"]["source_ref"] == "exact"


def test_protected_change_commits_directly(signed_in: Any, migrated_db: str) -> None:
    created = put(signed_in, demo_form())
    form = demo_form()
    form["basics"]["legal_name"] = "Riverbend Health"
    form["basics"]["ein"] = "84-3917266"
    saved = put(signed_in, form, created.headers["ETag"])
    assert saved.status_code == 200 and saved.json()["version"] == 2
    assert stored(migrated_db)["legal"]["legal_name"] == "Riverbend Health"
    with psycopg.connect(migrated_db) as conn:
        row = conn.execute(
            "SELECT count(*) FROM profile_change_proposals WHERE agency_id = %s",
            (get_settings().agency_id,),
        ).fetchone()
        audit = conn.execute(
            "SELECT count(*) FROM audit_log WHERE action = 'profile.updated' AND subject = %s",
            (f"agency:{get_settings().agency_id}",),
        ).fetchone()
    assert row is not None and row[0] == 0
    assert audit is not None and audit[0] >= 2
    again = put(signed_in, form, saved.headers["ETag"])
    assert again.status_code == 200 and again.json()["version"] == 2, "no-op save"


def test_patch_replaces_only_given_sections(signed_in: Any) -> None:
    created = put(signed_in, demo_form())
    mission = {"mission_statement": "We bring dental care to every rural school.", "values": []}
    patched = signed_in.patch(
        "/v1/profile", json={"mission": mission}, headers={"If-Match": created.headers["ETag"]}
    )
    assert patched.status_code == 200, patched.text
    form = patched.json()["form"]
    assert form["mission"] == {**mission, "vision_statement": None}
    expected = demo_form()
    for section in ("basics", "ntee_codes", "budget", "programs"):
        assert form[section] == expected[section]
    empty = signed_in.patch("/v1/profile", json={}, headers={"If-Match": '"2"'})
    assert empty.status_code == 422
    assert empty.json()["errors"][0] == {
        "field": "body",
        "code": "required",
        "message": "Send at least one section.",
    }


def test_if_match_conflict_and_required(signed_in: Any) -> None:
    created = put(signed_in, demo_form())
    assert created.status_code == 201
    missing = put(signed_in, demo_form())
    assert missing.status_code == 428 and missing.json()["code"] == "if_match_required"
    stale = put(signed_in, demo_form(), '"7"')
    assert stale.status_code == 409
    assert stale.json()["code"] == "version_conflict" and stale.json()["current_version"] == 1
    patch = signed_in.patch("/v1/profile", json={"ntee_codes": ["E32"]})
    assert patch.status_code == 428


def test_concurrent_first_save_conflicts(signed_in: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from hope_profile.repository import ProfileRepository

    def race(*_: Any, **__: Any) -> Any:
        raise psycopg.errors.UniqueViolation("duplicate key value")

    monkeypatch.setattr(ProfileRepository, "_insert_version", race)
    resp = put(signed_in, demo_form())
    assert resp.status_code == 409 and resp.json()["code"] == "version_conflict"


def _set(form: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    form = copy.deepcopy(form)
    *head, last = path.split(".")
    node: Any = form
    for part in head:
        node = node[int(part)] if part.isdigit() else node[part]
    if value is _DROP:
        del node[last]
    else:
        node[int(last) if last.isdigit() else last] = value
    return form


_DROP = object()


@pytest.mark.parametrize(
    ("path", "value", "field", "code"),
    [
        ("basics.ein", "07-1234567", "basics.ein", "invalid_ein_prefix"),
        ("basics.ein", "123456789", "basics.ein", "invalid_format"),
        ("basics.hq_state", "ZZ", "basics.hq_state", "unknown_state"),
        ("basics.legal_name", "", "basics.legal_name", "required"),
        ("basics.hq_city", _DROP, "basics.hq_city", "required"),
        ("basics.website", "not a url", "basics.website", "invalid_format"),
        ("mission.mission_statement", "Too short", "mission.mission_statement", "too_short"),
        ("mission.vision_statement", "x" * 2001, "mission.vision_statement", "too_long"),
        ("ntee_codes", ["E32", "F30", "B20", "O50"], "ntee_codes", "too_many"),
        ("ntee_codes", ["ZZ9"], "ntee_codes", "unknown_ntee_code"),
        ("ntee_codes", ["E32", "E32"], "ntee_codes", "duplicate"),
        ("ntee_codes", [], "ntee_codes", "required"),
        ("budget.fiscal_year_end", "02-31", "budget.fiscal_year_end", "invalid_format"),
        ("programs", [], "programs", "required"),
        ("programs.0.description", "short", "programs.0.description", "too_short"),
    ],
)
def test_validation_error_fields(
    signed_in: Any, path: str, value: Any, field: str, code: str
) -> None:
    response = put(signed_in, _set(demo_form(), path, value))
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "validation_error"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert {"field": field, "code": code} in [
        {"field": e["field"], "code": e["code"]} for e in body["errors"]
    ]
    if code == "invalid_ein_prefix":
        assert body["errors"][0]["message"] == (
            "This EIN prefix isn't assigned by the IRS. Check the number."
        )


def test_not_found_and_unauthenticated(hope_api: Any) -> None:
    for method, path in [
        ("GET", "/v1/profile"),
        ("PUT", "/v1/profile"),
        ("PATCH", "/v1/profile"),
        ("GET", "/v1/profile/ntee-codes"),
        ("POST", "/v1/profile/ntee-suggestions"),
    ]:
        response = hope_api.request(method, path, json={})
        assert response.status_code == 401, (method, path)
        assert response.json()["code"] == "not_signed_in"
    signup = hope_api.post(
        "/v1/auth/signup",
        json={
            "email": "dana@riverbend.example.org",
            "password": "correct-horse-battery",
            "display_name": "Dana Okafor",
            "invite_code": "test-invite-code-0123456789",
        },
    )
    assert signup.status_code == 201
    missing = hope_api.get("/v1/profile")
    assert missing.status_code == 404 and missing.json()["code"] == "profile_not_found"
    patch = hope_api.patch("/v1/profile", json={"ntee_codes": ["E32"]}, headers={"If-Match": '"1"'})
    assert patch.status_code == 404
