"""H2 `/v1/discovery/jobs*`: codes, `since_seq`, run list and the W3 mock shapes (AC15)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from hope_core.settings import get_settings
from hope_discovery.demo import demo_profile
from hope_discovery.settings import get_discovery_settings
from psycopg.types.json import Jsonb

INVITE = "test-invite-code-0123456789"  # set by the hope_api fixture

pytestmark = pytest.mark.db
MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks" / "w3"
REQUEST = {"focus_keywords": ["dental"], "location": "Chelan County, WA"}


def mock(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / f"{name}.json").read_text())
    return data


def shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [shape(v) for v in value[:1]]
    return type(value).__name__


def same(response: Any, name: str) -> None:
    expected = mock(name)
    assert response.status_code == expected["status"], (name, response.text)
    body = response.json()
    assert shape(body) == shape(expected["body"]), name
    if "code" in expected["body"]:
        assert body["code"] == expected["body"]["code"]
        assert response.headers["content-type"] == expected["headers"]["content-type"]


def same_steps(body: dict[str, Any], name: str) -> None:
    """Each step kind in the mock has the same keys and types as ours."""
    ours = {s["kind"]: shape(s) for s in body["steps"]}
    for step in mock(name)["body"]["steps"]:
        assert ours[step["kind"]] == shape(step), step["kind"]


def put_profile(admin_url: str, **overrides: Any) -> None:
    profile = demo_profile().model_copy(update=overrides)
    with psycopg.connect(admin_url) as conn:
        conn.execute(
            "INSERT INTO agency_profile_versions"
            " (agency_id, tenant_id, version, profile, recorded_by)"
            " VALUES (%s, %s, (SELECT COALESCE(max(version), 0) + 1 FROM agency_profile_versions"
            "  WHERE agency_id = %s), %s, 'test')",
            (
                profile.agency_id,
                profile.tenant_id,
                profile.agency_id,
                Jsonb(profile.model_dump(mode="json")),
            ),
        )


@pytest.fixture
def api(hope_api: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("HOPE_JOBS_INLINE", "1")
    monkeypatch.delenv("HOPE_OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    get_discovery_settings.cache_clear()
    response = hope_api.post(
        "/v1/auth/signup",
        json={
            "email": "dana@riverbend.example.org",
            "password": "long-enough",
            "display_name": "Dana",
            "invite_code": INVITE,
        },
    )
    assert response.status_code == 201
    yield hope_api
    get_discovery_settings.cache_clear()


def queue_job(admin_url: str) -> str:
    s = get_settings()
    with psycopg.connect(admin_url) as conn:
        row = conn.execute(
            "INSERT INTO jobs (tenant_id, kind) VALUES (%s, 'discovery') RETURNING job_id",
            (s.tenant_id,),
        ).fetchone()
        assert row is not None
        conn.execute(
            "INSERT INTO discovery_runs (job_id, tenant_id, focus_keywords, location, created_by)"
            " VALUES (%s, %s, %s, %s, %s)",
            (row[0], s.tenant_id, REQUEST["focus_keywords"], REQUEST["location"], s.tenant_id),
        )
    return str(row[0])


def test_start_validation_and_errors(
    api: TestClient, migrated_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    same(api.post("/v1/discovery/jobs", json=REQUEST), "discovery.start/profile_incomplete")
    put_profile(migrated_db, programs=[])
    body = api.post("/v1/discovery/jobs", json={}).json()
    assert body["code"] == "profile_incomplete" and body["missing"] == ["programs"]
    put_profile(migrated_db)

    for bad in (
        {"focus_keywords": ["x"]},
        {"focus_keywords": ["a" * 41]},
        {"focus_keywords": ["one", "two", "three", "four", "five", "six"]},
        {"location": "W"},
        {"location": "W" * 81},
        {"focus_keywords": "dental"},
        {"other": 1},
    ):
        response = api.post("/v1/discovery/jobs", json=bad)
        assert response.status_code == 422, bad
        assert response.json()["code"] == "validation_error", bad

    running = queue_job(migrated_db)
    response = api.post("/v1/discovery/jobs", json=REQUEST)
    same(response, "discovery.start/job_running")
    assert response.json()["job_id"] == running
    with psycopg.connect(migrated_db) as conn:
        conn.execute("UPDATE jobs SET status = 'failed' WHERE job_id = %s", (running,))

    monkeypatch.setenv("HOPE_DISCOVERY_DAILY_LIMIT", "1")
    get_discovery_settings.cache_clear()
    same(api.post("/v1/discovery/jobs", json=REQUEST), "discovery.start/daily_limit")

    api.post("/v1/auth/logout")
    response = api.post("/v1/discovery/jobs", json=REQUEST)
    assert (response.status_code, response.json()["code"]) == (401, "not_signed_in")
    assert api.get("/v1/discovery/jobs").status_code == 401


def test_get_since_seq_and_candidates(api: TestClient, migrated_db: str) -> None:
    put_profile(migrated_db)
    started = api.post(
        "/v1/discovery/jobs",
        json={"focus_keywords": [" dental ", "Dental"], "location": " Chelan County,  WA "},
    )
    same(started, "discovery.start/queued")
    job_id = started.json()["job"]["job_id"]
    assert started.json()["request"] == REQUEST

    view = api.get(f"/v1/discovery/jobs/{job_id}").json()
    assert view["job"]["status"] == "done"
    seqs = [s["seq"] for s in view["steps"]]
    assert seqs == list(range(1, len(seqs) + 1)) and view["last_seq"] == seqs[-1]
    later = api.get(f"/v1/discovery/jobs/{job_id}", params={"since_seq": 3}).json()
    assert [s["seq"] for s in later["steps"]] == seqs[3:]
    assert later["last_seq"] == view["last_seq"]
    tail = api.get(f"/v1/discovery/jobs/{job_id}", params={"since_seq": view["last_seq"]})
    assert tail.json()["steps"] == []

    titles = {c["title"]: c for c in view["candidates"]}
    assert set(titles) == {
        "Rural Oral Health Access Grant 2027",
        "Community Health Worker Training Grants",
        "Mobile Health Equipment Fund",
    }
    assert all(c["is_new"] and c["status"] == "new" for c in view["candidates"])
    saved = [s for s in view["steps"] if s["kind"] == "candidate"]
    assert {s["grant_id"] for s in saved} == {c["grant_id"] for c in view["candidates"]}

    response = api.get(f"/v1/discovery/jobs/{job_id}", params={"since_seq": -1})
    assert (response.status_code, response.json()["code"]) == (422, "validation_error")
    same(
        api.get("/v1/discovery/jobs/00000000-0000-0000-0000-000000000000"),
        "discovery.get/not_found",
    )


def test_list_runs(api: TestClient, migrated_db: str) -> None:
    same(api.get("/v1/discovery/jobs"), "discovery.list/empty")
    put_profile(migrated_db)
    first = api.post("/v1/discovery/jobs", json=REQUEST).json()["job"]["job_id"]
    second = api.post("/v1/discovery/jobs", json=REQUEST).json()["job"]["job_id"]
    response = api.get("/v1/discovery/jobs")
    same(response, "discovery.list/ok")
    body = response.json()
    assert [i["job_id"] for i in body["items"]] == [second, first]
    assert body["running_job_id"] is None
    assert body["items"][1]["candidates_found"] == 3 and body["items"][1]["candidates_new"] == 3
    assert body["items"][0]["candidates_new"] == 0
    assert len(api.get("/v1/discovery/jobs", params={"limit": 1}).json()["items"]) == 1
    for bad in (0, 51):
        response = api.get("/v1/discovery/jobs", params={"limit": bad})
        assert response.json()["code"] == "validation_error"


def test_shapes_match_contract_mocks(api: TestClient, migrated_db: str) -> None:
    put_profile(migrated_db)
    job_id = api.post("/v1/discovery/jobs", json=REQUEST).json()["job"]["job_id"]
    done = api.get(f"/v1/discovery/jobs/{job_id}")
    same(done, "discovery.get/done")
    same_steps(done.json(), "discovery.get/done")
    same_steps(done.json(), "discovery.get/running")

    with psycopg.connect(migrated_db) as conn:
        conn.execute("UPDATE jobs SET status = 'failed' WHERE kind = 'discovery'")
    failed_id = queue_job(migrated_db)
    with psycopg.connect(migrated_db) as conn:
        conn.execute(
            "UPDATE jobs SET status = 'failed', error = 'x', finished_at = now() WHERE job_id = %s",
            (failed_id,),
        )
    same(api.get(f"/v1/discovery/jobs/{failed_id}"), "discovery.get/failed")
