"""Saving a grant starts reading its requirements once; it never blocks or fails the save."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from hope_core import jobs, store
from hope_core.db import connect, tenant_tx
from hope_core.model_gateway import MockProvider, ModelGateway
from hope_core.schemas import GrantCandidate
from hope_core.settings import get_settings
from hope_core.web import FetchError, Page
from hope_discovery import mock
from hope_pillar.api import applications, requirements_autostart

INVITE = "test-invite-code-0123456789"  # set by the hope_api fixture
pytestmark = pytest.mark.db


class OnePageWeb:
    def __init__(self, url: str) -> None:
        self.url = url

    def search(self, query: str, max_results: int = 8) -> list[Any]:
        return []

    def fetch(self, url: str) -> Page:
        if url != self.url:
            raise FetchError("http_403", url)
        return Page(
            url=url,
            final_url=url,
            title="Apply",
            text="Describe the community need your program addresses? (500 words)",
        )


@pytest.fixture
def api(hope_api: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    response = hope_api.post(
        "/v1/auth/signup",
        json={
            "email": "autoread@riverbend.example.org",
            "password": "long-enough-pw",
            "display_name": "Auto",
            "invite_code": INVITE,
        },
    )
    assert response.status_code == 201, response.text
    monkeypatch.setenv("HOPE_JOBS_INLINE", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(requirements_autostart, "ENABLED", True)
    return hope_api


@pytest.fixture
def grant(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> GrantCandidate:
    candidate = GrantCandidate(
        grant_id=uuid4(),
        title="Community Health Access Grant",
        funder="Chelan County Community Foundation",
        url=f"https://ccf.example.org/grants/{uuid4().hex[:6]}",
        summary="Support for rural clinics.",
        fit_score=82,
        discovered_at=datetime(2026, 11, 7, 15, tzinfo=UTC),
    )
    monkeypatch.setattr(
        applications,
        "default_tools",
        lambda: (ModelGateway([mock.register(MockProvider())]), OnePageWeb(candidate.url)),
    )
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        return store.upsert_candidate(tx, candidate)


def save(api: TestClient, grant: GrantCandidate) -> dict[str, Any]:
    response = api.post(f"/v1/grants/{grant.grant_id}/save")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def workspace(api: TestClient) -> dict[str, Any]:
    (item,) = api.get("/v1/applications").json()["items"]
    body: dict[str, Any] = api.get(f"/v1/applications/{item['application_id']}").json()
    return body


def requirement_jobs(db: str) -> list[str]:
    with psycopg.connect(db) as conn:
        rows = conn.execute(
            "SELECT status FROM jobs WHERE tenant_id = %s AND kind = 'requirements'"
            " ORDER BY started_at",
            (get_settings().tenant_id,),
        ).fetchall()
    return [r[0] for r in rows]


def test_save_reads_requirements_once(
    api: TestClient, grant: GrantCandidate, migrated_db: str
) -> None:
    assert save(api, grant)["changed"] is True
    app = workspace(api)
    assert app["questions_status"] == "found"
    assert app["requirements_job"]["status"] == "done"
    (question,) = app["requirements"]["questions"]
    assert question["limit"]["max"] == 500
    assert [e["kind"] for e in app["events"]] == ["requirements", "created"]

    assert save(api, grant)["changed"] is False
    for action in ("pass", "reset", "save"):
        assert api.post(f"/v1/grants/{grant.grant_id}/{action}").status_code == 200
    assert requirement_jobs(migrated_db) == ["done"]
    with psycopg.connect(migrated_db) as conn:
        row = conn.execute(
            "SELECT count(*) FROM application_requirements WHERE application_id = %s",
            (app["application_id"],),
        ).fetchone()
    assert row is not None and row[0] == 1


def test_pass_and_reset_start_nothing(
    api: TestClient, grant: GrantCandidate, migrated_db: str
) -> None:
    for action in ("pass", "reset"):
        assert api.post(f"/v1/grants/{grant.grant_id}/{action}").status_code == 200
    assert requirement_jobs(migrated_db) == []
    assert api.get("/v1/applications").json()["items"] == []


def test_no_second_job_when_one_ran_or_runs(
    api: TestClient, grant: GrantCandidate, migrated_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(requirements_autostart, "ENABLED", False)
    save(api, grant)
    aid = workspace(api)["application_id"]
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        store.create_job(tx, "requirements", aid)
    monkeypatch.setattr(requirements_autostart, "ENABLED", True)
    api.post(f"/v1/grants/{grant.grant_id}/reset")
    save(api, grant)
    assert requirement_jobs(migrated_db) == ["queued"]


def test_no_job_when_requirements_were_pasted(
    api: TestClient, grant: GrantCandidate, migrated_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(requirements_autostart, "ENABLED", False)
    save(api, grant)
    aid = workspace(api)["application_id"]
    pasted = api.post(
        f"/v1/applications/{aid}/requirements/paste",
        json={"text": "1. What problem will this grant address? (250 words max)"},
    )
    assert pasted.status_code == 200, pasted.text
    monkeypatch.setattr(requirements_autostart, "ENABLED", True)
    api.post(f"/v1/grants/{grant.grant_id}/reset")
    save(api, grant)
    assert requirement_jobs(migrated_db) == []
    assert workspace(api)["questions_status"] == "found"


def test_save_succeeds_when_queueing_fails(
    api: TestClient, grant: GrantCandidate, migrated_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("database is down")

    with monkeypatch.context() as patched:
        patched.setattr(requirements_autostart.store, "latest_job", broken)
        assert save(api, grant)["status"] == "saved"
    assert requirement_jobs(migrated_db) == []
    assert workspace(api)["questions_status"] == "unread"


def test_save_succeeds_when_the_job_cannot_start(
    api: TestClient, grant: GrantCandidate, migrated_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("worker pool shut down")

    monkeypatch.setattr(
        requirements_autostart, "jobs", SimpleNamespace(start_job=broken, finish=jobs.finish)
    )
    assert save(api, grant)["status"] == "saved"
    assert requirement_jobs(migrated_db) == ["failed"]
    app = workspace(api)
    assert app["questions_status"] == "unread"
    assert app["requirements_job"]["error"] == "Could not start the job"
    started = api.post(f"/v1/applications/{app['application_id']}/requirements/jobs")
    assert started.status_code == 202, started.text
    assert started.json()["questions_status"] == "found"
