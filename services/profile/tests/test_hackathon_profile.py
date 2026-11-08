"""H1 `/v1/profile`: direct saves (no HITL-0), ETag/If-Match and problem+json errors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
import pytest
from hope_core.settings import get_settings

pytestmark = pytest.mark.db
MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks" / "w2"


def demo() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / "profile.put" / "request.json").read_text())
    return data


def rows(admin_url: str, sql: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(admin_url) as conn:
        return conn.execute(sql, (get_settings().agency_id,)).fetchall()


def test_put_creates_profile_with_defaults(signed_in: Any, migrated_db: str) -> None:
    assert signed_in.get("/v1/me").json()["onboarding_complete"] is False
    created = signed_in.put("/v1/profile", json=demo())
    assert created.status_code == 201, created.text
    assert created.headers["etag"] == '"1"'
    body = created.json()
    assert body["version"] == 1 and body["updated_by"] == "dana@riverbendhealth.example.org"
    assert body["form"]["basics"] == demo()["basics"]
    assert body["ntee_labels"] == {"E32": "Community Clinics", "F30": "Mental Health Treatment"}
    assert signed_in.get("/v1/me").json()["onboarding_complete"] is True

    [(profile,)] = rows(
        migrated_db, "SELECT profile FROM agency_profile_versions WHERE agency_id = %s"
    )
    assert profile["legal"]["state_of_incorporation"] == "WA"
    [rule] = profile["approval_hierarchy"]
    assert rule["gate"] == "HITL-0" and rule["approver_roles"] == ["admin"]
    assert profile["mission"]["focus_areas"] == ["Community Clinics", "Mental Health Treatment"]
    assert [p["status"] for p in profile["programs"]] == ["active", "active"]
    assert rows(
        migrated_db,
        "SELECT hq_city, hq_state, website, updated_by FROM agency_profile_extras"
        " WHERE agency_id = %s",
    ) == [
        (
            "Wenatchee",
            "WA",
            "https://riverbendhealth.example.org/",
            "dana@riverbendhealth.example.org",
        )
    ]
    [(name,)] = rows(migrated_db, "SELECT legal_name FROM agencies WHERE agency_id = %s")
    assert name == "Riverbend Community Health Alliance"


def test_budget_band_midpoint_and_exact(signed_in: Any, migrated_db: str) -> None:
    form = demo()
    form["budget"] = {"budget_band": "250k-1m", "annual_operating_budget_usd": None}
    created = signed_in.put("/v1/profile", json=form).json()
    assert created["form"]["budget"]["annual_operating_budget_usd"] is None
    assert created["form"]["budget"]["budget_band"] == "250k-1m"
    form["budget"] = {"budget_band": "1m-5m", "annual_operating_budget_usd": 3_120_000}
    exact = signed_in.put("/v1/profile", json=form, headers={"If-Match": '"1"'}).json()
    assert exact["form"]["budget"]["annual_operating_budget_usd"] == 3_120_000
    fin = [
        r[0]
        for r in rows(
            migrated_db,
            "SELECT profile->'financials' FROM agency_profile_versions WHERE agency_id = %s"
            " ORDER BY version",
        )
    ]
    assert fin[0]["annual_operating_budget"] == {"amount_minor": 50_000_000, "currency": "USD"}
    assert fin[0]["provenance"]["source_ref"] == "budget_band_midpoint"
    assert fin[0]["budget_band"] == "250k-1m"
    assert fin[1]["annual_operating_budget"]["amount_minor"] == 312_000_000
    assert fin[1]["provenance"]["source"] == "user_input"
    assert fin[1]["provenance"]["source_ref"] == "exact"


def test_protected_change_commits_directly(signed_in: Any, migrated_db: str) -> None:
    signed_in.put("/v1/profile", json=demo())
    form = demo()
    form["basics"]["ein"] = "84-3917266"
    form["basics"]["legal_name"] = "Riverbend Health Alliance"
    saved = signed_in.put("/v1/profile", json=form, headers={"If-Match": '"1"'})
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 2 and saved.headers["etag"] == '"2"'
    assert rows(
        migrated_db, "SELECT count(*) FROM profile_change_proposals WHERE agency_id = %s"
    ) == [(0,)]
    same = signed_in.put("/v1/profile", json=form, headers={"If-Match": '"2"'})
    assert same.status_code == 200 and same.json()["version"] == 2, "a no-op adds no version"


def test_patch_replaces_only_given_sections(signed_in: Any) -> None:
    signed_in.put("/v1/profile", json=demo())
    patched = signed_in.patch(
        "/v1/profile", json={"ntee_codes": ["K31"]}, headers={"If-Match": '"1"'}
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["version"] == 2 and patched.headers["etag"] == '"2"'
    assert body["form"]["ntee_codes"] == ["K31"]
    assert body["ntee_labels"] == {"K31": "Food Banks & Pantries"} or list(body["ntee_labels"]) == [
        "K31"
    ]
    for section in ("basics", "mission", "budget"):
        assert body["form"][section] == demo()[section], section
    assert [p["program_id"] for p in body["form"]["programs"]] == [
        p["program_id"] for p in demo()["programs"]
    ]
    empty = signed_in.patch("/v1/profile", json={}, headers={"If-Match": '"2"'})
    assert empty.status_code == 422
    assert empty.json()["errors"] == [
        {"field": "body", "code": "required", "message": "Send at least one section."}
    ]
    got = signed_in.get("/v1/profile")
    assert got.headers["etag"] == '"2"' and got.json() == body


def test_if_match_conflict_and_required(signed_in: Any) -> None:
    assert signed_in.patch("/v1/profile", json={"ntee_codes": ["K31"]}).status_code == 404
    signed_in.put("/v1/profile", json=demo())
    missing = signed_in.put("/v1/profile", json=demo())
    assert missing.status_code == 428 and missing.json()["code"] == "if_match_required"
    assert signed_in.patch("/v1/profile", json={"ntee_codes": ["K31"]}).status_code == 428
    stale = signed_in.put("/v1/profile", json=demo(), headers={"If-Match": '"7"'})
    assert stale.status_code == 409
    assert stale.json() | {"title": None} == {
        "type": "about:blank",
        "title": None,
        "status": 409,
        "code": "version_conflict",
        "current_version": 1,
    }
    junk = signed_in.patch(
        "/v1/profile", json={"ntee_codes": ["K31"]}, headers={"If-Match": "nope"}
    )
    assert junk.status_code == 409 and junk.json()["current_version"] == 1


@pytest.mark.parametrize(
    ("section", "key", "value", "field", "code"),
    [
        ("basics", "ein", "07-1234567", "basics.ein", "invalid_ein_prefix"),
        ("basics", "ein", "8439", "basics.ein", "invalid_format"),
        ("basics", "hq_state", "XX", "basics.hq_state", "unknown_state"),
        ("basics", "website", "not a url", "basics.website", "invalid_format"),
        ("mission", "mission_statement", "", "mission.mission_statement", "required"),
        ("budget", "fiscal_year_end", "02-30", "budget.fiscal_year_end", "invalid_format"),
        ("programs", None, [], "programs", "required"),
        ("ntee_codes", None, ["E32", "nope"], "ntee_codes", "unknown_ntee_code"),
    ],
)
def test_validation_error_fields(
    signed_in: Any, section: str, key: str | None, value: Any, field: str, code: str
) -> None:
    form = demo()
    if key is None:
        form[section] = value
    else:
        form[section][key] = value
    response = signed_in.put("/v1/profile", json=form)
    assert response.status_code == 422, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "validation_error" and body["status"] == 422
    assert {"field": field, "code": code} in [
        {"field": e["field"], "code": e["code"]} for e in body["errors"]
    ]
    assert all(set(e) == {"field", "code", "message"} for e in body["errors"])
    assert signed_in.get("/v1/profile").status_code == 404


def test_not_found_and_unauthenticated(hope_api: Any, signed_in: Any) -> None:
    missing = signed_in.get("/v1/profile")
    assert missing.status_code == 404 and missing.json()["code"] == "profile_not_found"
    signed_in.post("/v1/auth/logout")
    for method, path, body in [
        ("GET", "/v1/profile", None),
        ("PUT", "/v1/profile", demo()),
        ("PATCH", "/v1/profile", {"ntee_codes": ["E32"]}),
        ("GET", "/v1/profile/ntee-codes?q=clinic", None),
        ("POST", "/v1/profile/ntee-suggestions", {"mission_statement": "x" * 30}),
    ]:
        response = hope_api.request(method, path, json=body)
        assert response.status_code == 401, (method, path)
        assert response.json()["code"] == "not_signed_in"
        assert response.headers["content-type"] == "application/problem+json"


def test_ntee_search_endpoint(signed_in: Any) -> None:
    groups = signed_in.get("/v1/profile/ntee-codes").json()["items"]
    assert len(groups) == 26
    found = signed_in.get("/v1/profile/ntee-codes", params={"q": "clinic", "limit": 2}).json()
    assert found["items"][0]["code"] == "E32" and len(found["items"]) == 2
    assert signed_in.get("/v1/profile/ntee-codes", params={"q": "zzzqqq"}).json() == {"items": []}
    too_many = signed_in.get("/v1/profile/ntee-codes", params={"limit": 500})
    assert too_many.status_code == 422 and too_many.json()["errors"][0]["field"] == "limit"
