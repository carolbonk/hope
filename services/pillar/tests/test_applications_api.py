"""H6 step 1: the server-side application record, stage gates, evidence, approvals and RLS."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from hope_core import store
from hope_core.db import connect, tenant_tx
from hope_core.schemas import GrantCandidate
from hope_core.settings import get_settings
from hope_core.testing.factories import TENANT_B
from psycopg.types.json import Jsonb

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
    body = problem(call(api, app, "stage", {"to": "ready"}), 409, "stage_blocked")
    assert body["errors"][0]["message"].startswith("Finish the checklist first")
    app = call(
        api, app, "stage", {"to": "ready", "override_reason": "Funder accepts it by email."}
    ).json()
    assert app["stage"] == "ready"
    assert app["events"][0]["payload"]["override_reason"] == "Funder accepts it by email."
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


class OnePageWeb:
    def __init__(self, url: str) -> None:
        self.url = url

    def search(self, query: str, max_results: int = 8) -> list[Any]:
        return []

    def fetch(self, url: str) -> Any:
        from hope_core.web import FetchError, Page

        if url != self.url:
            raise FetchError("http_403", url)
        return Page(
            url=url,
            final_url=url,
            title="Apply",
            text="Describe the community need your program addresses? (500 words)"
            " Upload your IRS determination letter. Applications are due March 1, 2027.",
        )


@pytest.fixture
def inline_jobs(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("HOPE_JOBS_INLINE", "1")
    get_settings.cache_clear()
    return monkeypatch


def test_requirements_job_reads_questions(
    api: TestClient, grant: GrantCandidate, inline_jobs: pytest.MonkeyPatch
) -> None:
    from hope_core.model_gateway import MockProvider, ModelGateway
    from hope_discovery import mock
    from hope_pillar.api import applications

    inline_jobs.setattr(
        applications,
        "default_tools",
        lambda: (ModelGateway([mock.register(MockProvider())]), OnePageWeb(grant.url)),
    )
    app = saved_app(api, grant)
    assert app["requirements"] is None and app["requirements_job"] is None
    started = api.post(f"/v1/applications/{app['application_id']}/requirements/jobs")
    assert started.status_code == 202, started.text
    body = started.json()
    assert body["questions_status"] == "found"
    assert body["requirements_job"]["status"] == "done"
    (question,) = body["requirements"]["questions"]
    assert question["limit"] == {"unit": "words", "max": 500, "includes_spaces": None}
    assert [a["name"] for a in body["requirements"]["attachments"]] == ["IRS determination letter"]
    assert body["requirements"]["submission"]["deadline_date"] == "2027-03-01"
    assert body["events"][0]["kind"] == "requirements"
    assert body["events"][0]["payload"]["questions"] == 1


def test_requirements_not_found_when_pages_blocked(
    api: TestClient, grant: GrantCandidate, inline_jobs: pytest.MonkeyPatch
) -> None:
    from hope_core.model_gateway import MockProvider, ModelGateway
    from hope_discovery import mock
    from hope_pillar.api import applications

    inline_jobs.setattr(
        applications,
        "default_tools",
        lambda: (ModelGateway([mock.register(MockProvider())]), OnePageWeb("https://nowhere")),
    )
    app = saved_app(api, grant)
    body = api.post(f"/v1/applications/{app['application_id']}/requirements/jobs").json()
    assert body["questions_status"] == "not_found"
    assert body["requirements"]["pages"] == [
        {"url": grant.url, "status": "failed", "reason": "http_403"}
    ]
    problem(api.post(f"/v1/applications/{uuid4()}/requirements/jobs"), 404, "application_not_found")


PASTED_FORM = """Section B: Narrative
1. Community Problem: What problem will this grant address? (250 words max)
2. How will you measure success? Limit 1,000 characters including spaces.
Please contact program staff with questions.
Attach your most recent audited financial statements."""


@pytest.fixture
def drafting(
    api: TestClient, inline_jobs: pytest.MonkeyPatch, migrated_db: str
) -> pytest.MonkeyPatch:
    from hope_core.model_gateway import MockProvider, ModelGateway
    from hope_discovery import mock
    from hope_discovery.demo import demo_profile
    from hope_pillar.api import applications

    profile = demo_profile()
    with psycopg.connect(migrated_db) as conn:
        conn.execute(
            "INSERT INTO agency_profile_versions (agency_id, tenant_id, version, profile,"
            " recorded_by) VALUES (%s, %s, 1, %s, 'test')",
            (profile.agency_id, profile.tenant_id, Jsonb(profile.model_dump(mode="json"))),
        )
    inline_jobs.setattr(
        applications,
        "default_tools",
        lambda: (ModelGateway([mock.register(MockProvider())]), OnePageWeb("https://nowhere")),
    )
    return inline_jobs


def test_pasted_form_drafts_edits_and_exports(
    api: TestClient, grant: GrantCandidate, drafting: pytest.MonkeyPatch
) -> None:
    app = saved_app(api, grant)
    base = f"/v1/applications/{app['application_id']}"
    problem(api.post(f"{base}/requirements/paste", json={}), 422, "validation_failed")
    pdf = {"pdf_base64": "bm90IGEgcGRm"}
    problem(api.post(f"{base}/requirements/paste", json=pdf), 422, "validation_failed")

    app = api.post(f"{base}/requirements/paste", json={"text": PASTED_FORM}).json()
    assert app["questions_status"] == "found"
    prompts = [(q["prompt"], q["source"], q["limit"]) for q in app["questions"]]
    assert prompts == [
        (
            "Community Problem: What problem will this grant address?",
            "pasted",
            {"unit": "words", "max": 250, "includes_spaces": None},
        ),
        (
            "How will you measure success?",
            "pasted",
            {"unit": "characters", "max": 1000, "includes_spaces": True},
        ),
    ]
    need, success = (q["key"] for q in app["questions"])
    status = {i["label"]: i["status"] for i in app["checklist"]["items"]}
    assert status["Community Problem: What problem will this grant address?"] == "missing"
    (doc,) = app["requirements"]["attachments"]
    assert "financial statements" in doc["name"].lower() and status[doc["name"]] == "in_dossier"

    app = api.post(f"{base}/answers/{need}/draft").json()
    (answer,) = app["answers"]
    assert answer["origin"] == "ai" and answer["citations"]
    assert answer["to_confirm"] == ["local data on need"]
    assert app["events"][0]["kind"] == "draft"
    problem(api.post(f"{base}/answers/nope/draft"), 404, "question_not_found")

    edit = {"text": "Rural families drive 90 minutes to a clinic."}
    problem(api.patch(f"{base}/answers/{need}", json=edit), 428, "if_match_required")
    app = api.patch(
        f"{base}/answers/{need}", json=edit, headers={"If-Match": f'"{app["version"]}"'}
    ).json()
    assert app["answers"][0]["origin"] == "human" and app["answers"][0]["to_confirm"] == []
    problem(api.post(f"{base}/answers/{need}/draft"), 409, "human_edit")

    app = api.post(f"{base}/answers/draft-all").json()
    assert app["answers_job"]["status"] == "done"
    texts = {a["question_key"]: a for a in app["answers"]}
    assert texts[need]["text"] == edit["text"] and texts[success]["origin"] == "ai"

    app = api.post(f"{base}/answers/{need}/draft", json={"confirm_overwrite": True}).json()
    assert {a["question_key"]: a["origin"] for a in app["answers"]}[need] == "ai"

    md = api.get(f"{base}/export.md")
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert "What problem will this grant address?" in md.text and "_Limit: 250 words_" in md.text


def test_no_questions_uses_labelled_standard_sections(
    api: TestClient, grant: GrantCandidate, drafting: pytest.MonkeyPatch
) -> None:
    app = saved_app(api, grant)
    assert len(app["questions"]) == 6 and {q["source"] for q in app["questions"]} == {"standard"}
    app = api.post(f"/v1/applications/{app['application_id']}/answers/draft-all").json()
    assert len(app["answers"]) == 6
    assert app["answers_job"]["result"] == {"drafted": 6, "skipped": 0}


def test_staff_facts_replace_to_confirm_on_redraft(
    api: TestClient, grant: GrantCandidate, drafting: pytest.MonkeyPatch
) -> None:
    app = saved_app(api, grant)
    base = f"/v1/applications/{app['application_id']}"
    app = api.post(f"{base}/requirements/paste", json={"text": PASTED_FORM}).json()
    need = app["questions"][0]["key"]
    app = api.post(f"{base}/answers/{need}/draft").json()
    (asked,) = app["checklist"]["inputs_needed"][:1]
    assert asked["text"] == "local data on need" and asked["answer"] is None

    fact = {"need": "local data on need", "answer": "38% of residents live 30+ miles away."}
    problem(api.post(f"{base}/facts", json=fact), 428, "if_match_required")
    app = call(api, app, "facts", fact).json()
    assert [(f["need"], f["answer"]) for f in app["facts"]] == [(fact["need"], fact["answer"])]
    assert app["checklist"]["inputs_needed"][0]["answer"] == fact["answer"]
    assert app["events"][0]["kind"] == "fact"

    app = api.post(f"{base}/answers/{need}/draft").json()
    answer = next(a for a in app["answers"] if a["question_key"] == need)
    assert answer["to_confirm"] == []
    assert "TO CONFIRM" not in answer["text"] and fact["answer"] in answer["text"]
    status = {i["key"]: i["status"] for i in app["checklist"]["items"] if i["kind"] == "question"}
    assert status[need] != "to_confirm"

    app = call(api, app, "facts", {"need": fact["need"], "answer": ""}).json()
    assert app["facts"] == []


RULES_FORM = (
    PASTED_FORM
    + "\nApplicants must be 501(c)(3) nonprofits located in Washington."
    + "\nApplicants requesting more than $50,000 must submit an audit."
)


def test_grant_rules_are_checked_and_changes_shown(
    api: TestClient, grant: GrantCandidate, drafting: pytest.MonkeyPatch
) -> None:
    app = saved_app(api, grant)
    base = f"/v1/applications/{app['application_id']}"
    app = api.post(f"{base}/requirements/paste", json={"text": RULES_FORM}).json()
    assert app["changes"] == [] and app["requirements_revision"] == 1
    rules = {r["kind"]: r for r in app["rules"]}
    assert rules["eligibility"]["status"] == "met"
    assert rules["eligibility"]["quote"] == (
        "Applicants must be 501(c)(3) nonprofits located in Washington."
    )
    assert rules["conditional"]["status"] == "unknown"

    problem(call(api, app, "ask", {"amount_minor": 0}), 422, "validation_failed")
    app = call(api, app, "ask", {"amount_minor": 6_000_000}).json()
    assert app["ask"] == {"amount_minor": 6_000_000, "currency": "USD"}
    audit = next(r for r in app["rules"] if r["kind"] == "conditional")
    assert audit["status"] == "applies" and audit["owner"] == "finance"
    assert any(
        n["text"] == f"Required for you: {audit['quote']}"
        for n in app["checklist"]["inputs_needed"]
    )

    more = "Applicants must be located in Ohio.\nUpload your board list."
    app = api.post(f"{base}/requirements/paste", json={"text": more}).json()
    assert app["requirements_revision"] == 2
    assert [(c["what"], c["change"], c["text"]) for c in app["changes"]] == [
        ("upload", "added", "board list"),
        ("eligibility", "added", "Applicants must be located in Ohio."),
    ]
    ohio = next(r for r in app["rules"] if "Ohio" in r["quote"])
    assert ohio["status"] == "not_met" and "Washington" not in ohio["reason"]

    app = call(api, app, "stage", {"to": "eligibility"}).json()
    body = problem(call(api, app, "stage", {"to": "approval"}), 409, "stage_blocked")
    assert "Location" in body["errors"][0]["message"]
    app = call(
        api, app, "evidence", {"requirement_id": ohio["key"], "status": "yes", "note": "HQ moved"}
    ).json()
    ohio = next(r for r in app["rules"] if r["key"] == ohio["key"])
    assert (ohio["status"], ohio["reason"]) == ("met", "Confirmed by staff: HQ moved")
    assert call(api, app, "stage", {"to": "approval"}).status_code == 200


def test_staff_facts_are_reused_on_other_grants(
    api: TestClient, grant: GrantCandidate, drafting: pytest.MonkeyPatch
) -> None:
    first = saved_app(api, grant)
    fact = {"need": "local data on need", "answer": "38% of residents live 30+ miles away."}
    call(api, first, "facts", fact)

    other = GrantCandidate(
        grant_id=uuid4(),
        title="Rural Clinic Fund",
        funder="Another Foundation",
        summary="Rural clinics.",
        url=f"https://another.example.org/{uuid4().hex[:6]}",
        fit_score=70,
        discovered_at=datetime(2026, 11, 7, 15, tzinfo=UTC),
    )
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        store.upsert_candidate(tx, other)
    assert api.post(f"/v1/grants/{other.grant_id}/save").status_code == 200
    second_id = next(
        i["application_id"]
        for i in api.get("/v1/applications").json()["items"]
        if i["grant_id"] == str(other.grant_id)
    )
    base = f"/v1/applications/{second_id}"
    app = api.get(base).json()
    assert [(f["need"], f["shared"]) for f in app["facts"]] == [(fact["need"], True)]

    app = api.post(f"{base}/requirements/paste", json={"text": PASTED_FORM}).json()
    need = app["questions"][0]["key"]
    app = api.post(f"{base}/answers/{need}/draft").json()
    answer = next(a for a in app["answers"] if a["question_key"] == need)
    assert answer["to_confirm"] == []


def test_a_new_paste_replaces_the_deadline_and_shows_the_change(
    api: TestClient, grant: GrantCandidate, drafting: pytest.MonkeyPatch
) -> None:
    app = saved_app(api, grant)
    base = f"/v1/applications/{app['application_id']}"
    form = "What problem will this grant address? (200 words)\nApplications are due March 1, 2027."
    api.post(f"{base}/requirements/paste", json={"text": form})
    later = form.replace("March 1, 2027", "March 15, 2027")
    app = api.post(f"{base}/requirements/paste", json={"text": later}).json()
    assert app["requirements"]["submission"]["deadline_date"] == "2027-03-15"
    assert [(c["what"], c["change"]) for c in app["changes"]] == [("deadline", "changed")]
    assert "March 1, 2027" in (app["changes"][0]["before"] or "")
