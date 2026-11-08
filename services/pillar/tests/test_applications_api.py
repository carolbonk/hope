"""H6 step 1: the server-side application record, stage gates, evidence, approvals and RLS."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from hope_core import store
from hope_core.db import connect, tenant_tx
from hope_core.schemas import GrantCandidate
from hope_core.settings import get_settings
from hope_core.testing.factories import TENANT_B

INVITE = "test-invite-code-0123456789"  # set by the hope_api fixture


def problem(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    assert body["code"] == code
    return body


@pytest.fixture
def api(hope_api: TestClient) -> TestClient:
    response = hope_api.post(
        "/v1/auth/signup",
        json={
            "email": "apps@riverbend.example.org",
            "password": "long-enough-pw",
            "display_name": "Apps",
            "invite_code": INVITE,
        },
    )
    assert response.status_code == 201, response.text
    return hope_api


@pytest.fixture
def grant(api: TestClient) -> GrantCandidate:
    candidate = GrantCandidate(
        grant_id=uuid4(),
        title="Community Health Access Grant",
        funder="Chelan County Community Foundation",
        url=f"https://ccf.example.org/grants/{uuid4().hex[:6]}",
        summary="Support for rural clinics.",
        fit_score=82,
        discovered_at=datetime(2026, 11, 7, 15, tzinfo=UTC),
    )
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        return store.upsert_candidate(tx, candidate)


def saved_app(api: TestClient, grant: GrantCandidate) -> dict[str, Any]:
    assert api.post(f"/v1/grants/{grant.grant_id}/save").status_code == 200
    (item,) = api.get("/v1/applications").json()["items"]
    body: dict[str, Any] = api.get(f"/v1/applications/{item['application_id']}").json()
    return body


def call(api: TestClient, app: dict[str, Any], path: str, body: dict[str, Any]) -> Any:
    return api.post(
        f"/v1/applications/{app['application_id']}/{path}",
        json=body,
        headers={"If-Match": f'"{app["version"]}"'},
    )


def test_save_creates_one_application_and_reuses_it(api: TestClient, grant: GrantCandidate) -> None:
    app = saved_app(api, grant)
    assert app["stage"] == "saved" and app["grant_id"] == str(grant.grant_id)
    assert app["title"] == grant.title and app["questions_status"] == "unread"
    assert [e["kind"] for e in app["events"]] == ["created"]
    api.post(f"/v1/grants/{grant.grant_id}/pass")
    api.post(f"/v1/grants/{grant.grant_id}/reset")
    api.post(f"/v1/grants/{grant.grant_id}/save")
    items = api.get("/v1/applications").json()["items"]
    assert [i["application_id"] for i in items] == [app["application_id"]]


def test_get_sends_etag_and_unknown_is_404(api: TestClient, grant: GrantCandidate) -> None:
    app = saved_app(api, grant)
    response = api.get(f"/v1/applications/{app['application_id']}")
    assert response.headers["etag"] == '"1"'
    problem(api.get(f"/v1/applications/{uuid4()}"), 404, "application_not_found")
    problem(api.get("/v1/applications/not-a-uuid"), 404, "application_not_found")


def test_writes_need_a_current_if_match(api: TestClient, grant: GrantCandidate) -> None:
    app = saved_app(api, grant)
    url = f"/v1/applications/{app['application_id']}/stage"
    problem(api.post(url, json={"to": "eligibility"}), 428, "if_match_required")
    problem(
        api.post(url, json={"to": "eligibility"}, headers={"If-Match": '"9"'}),
        412,
        "version_mismatch",
    )
    moved = call(api, app, "stage", {"to": "eligibility"})
    assert moved.status_code == 200 and moved.json()["stage"] == "eligibility"
    assert moved.json()["version"] == 2 and moved.headers["etag"] == '"2"'


def test_stage_gates(api: TestClient, grant: GrantCandidate) -> None:
    app = saved_app(api, grant)
    problem(call(api, app, "stage", {"to": "drafting"}), 409, "stage_blocked")
    app = call(api, app, "stage", {"to": "eligibility"}).json()
    app = call(api, app, "evidence", {"requirement_id": "501c3", "status": "unknown"}).json()
    body = problem(call(api, app, "stage", {"to": "approval"}), 409, "stage_blocked")
    assert body["errors"][0]["message"] == "Resolve unknown or failed requirements first."
    app = call(
        api, app, "evidence", {"requirement_id": "501c3", "status": "yes", "note": "IRS letter"}
    ).json()
    assert app["evidence"]["501c3"]["note"] == "IRS letter"
    app = call(api, app, "stage", {"to": "approval"}).json()
    assert app["stage"] == "approval"
    problem(
        call(api, app, "evidence", {"requirement_id": "x", "status": "yes"}), 409, "stage_blocked"
    )


def test_approvals_program_then_director(api: TestClient, grant: GrantCandidate) -> None:
    app = saved_app(api, grant)
    problem(
        call(api, app, "approvals", {"step": "program", "decision": "approve"}),
        409,
        "stage_blocked",
    )
    app = call(api, app, "stage", {"to": "eligibility"}).json()
    app = call(api, app, "stage", {"to": "approval"}).json()
    body = problem(
        call(api, app, "approvals", {"step": "director", "decision": "approve"}),
        409,
        "stage_blocked",
    )
    assert body["errors"][0]["message"] == "Program review must approve first."
    problem(
        call(api, app, "approvals", {"step": "program", "decision": "send_back"}),
        422,
        "comment_required",
    )

    app = call(api, app, "approvals", {"step": "program", "decision": "approve"}).json()
    back = call(
        api,
        app,
        "approvals",
        {"step": "director", "decision": "send_back", "comment": "Fix budget"},
    )
    app = back.json()
    assert app["stage"] == "eligibility" and app["approvals"] == {}

    app = call(api, app, "stage", {"to": "approval"}).json()
    app = call(api, app, "approvals", {"step": "program", "decision": "approve"}).json()
    app = call(api, app, "approvals", {"step": "director", "decision": "approve"}).json()
    assert app["stage"] == "drafting" and set(app["approvals"]) == {"program", "director"}
    app = call(api, app, "stage", {"to": "ready"}).json()
    assert app["stage"] == "ready"
    kinds = [e["kind"] for e in app["events"]]
    assert kinds[:3] == ["stage", "approval", "approval"] and "send_back" in kinds


def test_comments_append_without_version_bump(api: TestClient, grant: GrantCandidate) -> None:
    app = saved_app(api, grant)
    after = api.post(
        f"/v1/applications/{app['application_id']}/comments", json={"text": "Call the PO"}
    )
    assert after.status_code == 200
    assert after.json()["version"] == app["version"]
    assert after.json()["events"][0] == after.json()["events"][0] | {
        "kind": "comment",
        "payload": {"text": "Call the PO"},
    }
    problem(
        api.post(f"/v1/applications/{app['application_id']}/comments", json={"text": ""}),
        422,
        "validation_failed",
    )


def test_other_tenant_sees_nothing(api: TestClient, grant: GrantCandidate) -> None:
    saved_app(api, grant)
    with connect() as conn, tenant_tx(conn, TENANT_B) as tx:
        tx.execute("SELECT count(*) AS n FROM applications")
        assert tx.fetchone() == {"n": 0}
    problem(api.get("/v1/applications/x"), 404, "application_not_found")


def test_requires_sign_in(hope_api: TestClient) -> None:
    problem(hope_api.get("/v1/applications"), 401, "not_signed_in")
