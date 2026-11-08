"""My bids: owners, dates, reviews, blockers, final review and the recorded receipt."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from hope_core import store
from hope_core.db import connect, tenant_tx
from hope_core.schemas import GrantCandidate
from hope_core.settings import get_settings
from hope_core.testing.factories import TENANT_B
from hope_discovery.requirements import (
    Attachment,
    Question,
    Requirements,
    Sourced,
    Submission,
)
from hope_pillar.api.applications import save_requirements

INVITE = "test-invite-code-0123456789"  # set by the hope_api fixture
URL = "https://ccf.example.org/apply"
MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks" / "w7"


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
            "email": "bids@riverbend.example.org",
            "password": "long-enough-pw",
            "display_name": "Bea",
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


def requirements(prompt: str = "Describe the need.", deadline: date | None = None) -> Requirements:
    return Requirements(
        questions=[Question(key="need", prompt=prompt, url=URL)],
        attachments=[Attachment(name="IRS determination letter", quote="Attach it.", url=URL)],
        submission=Submission(
            deadline=Sourced(text="Due soon", url=URL) if deadline else None,
            deadline_date=deadline,
        ),
    )


def read(bid: dict[str, Any], req: Requirements, answer: bool = True) -> None:
    """Stand in for the requirements job: store a read and (optionally) a drafted answer."""
    aid = UUID(bid["application_id"])
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        save_requirements(tx, aid, req)
        if answer:
            tx.execute(
                "INSERT INTO application_answers (application_id, tenant_id, question_key, text,"
                " origin) VALUES (%s, current_tenant(), 'need', 'Rural clinics close early.', 'ai')"
                " ON CONFLICT DO NOTHING",
                (aid,),
            )


def start(api: TestClient, grant: GrantCandidate) -> dict[str, Any]:
    response = api.post("/v1/bids", json={"grant_id": str(grant.grant_id)})
    assert response.status_code in (200, 201), response.text
    body: dict[str, Any] = response.json()
    return body


def get(api: TestClient, grant: GrantCandidate) -> dict[str, Any]:
    body: dict[str, Any] = api.get(f"/v1/bids/{grant.grant_id}").json()
    return body


def call(
    api: TestClient, bid: dict[str, Any], path: str, body: dict[str, Any], method: str = "POST"
) -> Any:
    return api.request(
        method,
        f"/v1/bids/{bid['grant_id']}/{path}",
        json=body,
        headers={"If-Match": f'"{bid["version"]}"'},
    )


def me(api: TestClient) -> str:
    (member,) = api.get("/v1/members").json()["items"]
    assert member["display_name"] == "Bea" and "email" not in member
    return str(member["user_id"])


def prepare(api: TestClient, bid: dict[str, Any], owner: str) -> dict[str, Any]:
    """Assign, finish and approve every requirement."""
    for item in bid["items"]:
        r = call(api, bid, f"items/{item['key']}", {"owner": owner, "status": "ready"}, "PUT")
        bid = r.json()
        bid = call(api, bid, f"items/{item['key']}/review", {"decision": "approved"}).json()
    return bid


def codes(bid: dict[str, Any]) -> list[tuple[str, str | None]]:
    return [(b["code"], b.get("key")) for b in bid["blocker_list"]]


def test_start_saves_the_grant_and_reuses_the_bid(api: TestClient, grant: GrantCandidate) -> None:
    response = api.post("/v1/bids", json={"grant_id": str(grant.grant_id)})
    assert response.status_code == 201 and response.headers["etag"] == '"1"'
    bid = response.json()
    assert bid["phase"] == "preparing" and bid["title"] == grant.title
    assert api.get(f"/v1/grants/{grant.grant_id}").json()["status"] == "saved"
    assert [i["application_id"] for i in api.get("/v1/applications").json()["items"]] == [
        bid["application_id"]
    ]
    assert codes(bid)[0] == ("no_requirements", None)
    again = api.post("/v1/bids", json={"grant_id": str(grant.grant_id)})
    assert again.status_code == 200 and again.json()["application_id"] == bid["application_id"]
    listed = api.get("/v1/bids").json()
    assert listed["total"] == 1 and listed["items"][0]["grant_id"] == str(grant.grant_id)
    events = api.get(f"/v1/applications/{bid['application_id']}").json()["events"]
    assert [e["payload"].get("action") for e in events if e["kind"] == "bid"] == ["started"]


def test_unknown_grant_and_bid_are_404(api: TestClient, grant: GrantCandidate) -> None:
    problem(api.post("/v1/bids", json={"grant_id": str(uuid4())}), 404, "grant_not_found")
    problem(api.get(f"/v1/bids/{grant.grant_id}"), 404, "bid_not_found")
    problem(api.get("/v1/bids/not-a-uuid"), 404, "bid_not_found")
    assert api.get("/v1/bids").json() == {"items": [], "total": 0}


def test_items_come_from_the_application_checklist(api: TestClient, grant: GrantCandidate) -> None:
    read(start(api, grant), requirements(deadline=date.today() + timedelta(days=30)))
    bid = get(api, grant)
    assert [(i["key"], i["kind"]) for i in bid["items"]] == [
        ("need", "question"),
        ("irs_501c3", "attachment"),
    ]
    assert all(i["status"] == "missing" and i["owner"] is None for i in bid["items"])
    assert ("no_owner", "need") in codes(bid) and ("not_ready", "irs_501c3") in codes(bid)
    deadline = date.today() + timedelta(days=30)
    assert bid["deadline"] == deadline.isoformat()
    assert [(m["key"], m["due"], m["done"]) for m in bid["plan"]] == [
        ("owners", (deadline - timedelta(days=14)).isoformat(), False),
        ("drafts", (deadline - timedelta(days=7)).isoformat(), False),
        ("reviews", (deadline - timedelta(days=3)).isoformat(), False),
        ("final_review", (deadline - timedelta(days=1)).isoformat(), False),
    ]


def test_writes_need_a_current_version_a_known_item_and_member(
    api: TestClient, grant: GrantCandidate
) -> None:
    bid = start(api, grant)
    read(bid, requirements())
    bid = get(api, grant)
    url = f"/v1/bids/{grant.grant_id}/items/need"
    problem(api.put(url, json={"status": "working"}), 428, "if_match_required")
    problem(
        api.put(url, json={"status": "working"}, headers={"If-Match": '"9"'}),
        412,
        "version_mismatch",
    )
    problem(call(api, bid, "items/nope", {"status": "working"}, "PUT"), 404, "item_not_found")
    problem(call(api, bid, "items/need", {"owner": str(uuid4())}, "PUT"), 422, "unknown_member")
    problem(call(api, bid, "items/need", {"status": "done"}, "PUT"), 422, "validation_failed")
    due = (date.today() + timedelta(days=5)).isoformat()
    owner = me(api)
    updated = call(api, bid, "items/need", {"owner": owner, "due": due, "note": "Ana"}, "PUT")
    assert updated.status_code == 200 and updated.headers["etag"] == '"2"'
    item = updated.json()["items"][0]
    assert (item["owner"], item["due"], item["note"], item["status"]) == (
        owner,
        due,
        "Ana",
        "missing",
    )
    cleared = call(api, updated.json(), "items/need", {"owner": None}, "PUT").json()
    assert cleared["items"][0]["owner"] is None and cleared["items"][0]["due"] == due


def test_review_rules(api: TestClient, grant: GrantCandidate) -> None:
    read(start(api, grant), requirements())
    bid = get(api, grant)
    problem(call(api, bid, "items/need/review", {"decision": "approved"}), 409, "bid_blocked")
    bid = call(
        api, bid, "items/need", {"status": "ready", "evidence_ref": "Draft v1"}, "PUT"
    ).json()
    problem(
        call(api, bid, "items/need/review", {"decision": "changes_requested"}),
        422,
        "comment_required",
    )
    bid = call(
        api, bid, "items/need/review", {"decision": "changes_requested", "comment": "Add data"}
    ).json()
    item = bid["items"][0]
    assert item["status"] == "working" and item["review"]["comment"] == "Add data"
    bid = call(api, bid, "items/need", {"status": "ready"}, "PUT").json()
    assert bid["items"][0]["review"] is None, "a changed requirement needs a new review"
    bid = call(api, bid, "items/need/review", {"decision": "approved"}).json()
    assert bid["items"][0]["review"]["decision"] == "approved"
    owner_only = call(api, bid, "items/need", {"owner": me(api)}, "PUT").json()
    assert owner_only["items"][0]["review"]["decision"] == "approved", "assigning keeps it"
    assert ("not_reviewed", "need") not in codes(owner_only)


def test_a_new_read_with_changed_wording_makes_the_review_stale(
    api: TestClient, grant: GrantCandidate
) -> None:
    read(start(api, grant), requirements())
    bid = prepare(api, get(api, grant), me(api))
    assert codes(bid) == []
    read(bid, requirements())  # same wording: the review stands
    assert codes(get(api, grant)) == []
    read(bid, requirements(prompt="Describe the need and who you serve."))
    bid = get(api, grant)
    assert codes(bid) == [("stale_review", "need")]
    assert bid["items"][0]["review"]["stale"] is True


def test_final_review_then_receipt_then_read_only(api: TestClient, grant: GrantCandidate) -> None:
    read(start(api, grant), requirements(deadline=date.today() + timedelta(days=20)))
    bid = get(api, grant)
    body = problem(call(api, bid, "final-review", {}), 409, "bid_blocked")
    assert {e["code"] for e in body["errors"]} >= {"no_owner", "not_ready"}
    problem(
        call(
            api,
            bid,
            "submission",
            {"receipt": "R-1", "portal": "x", "submitted_at": "2026-11-20T10:00:00Z"},
        ),
        409,
        "bid_blocked",
    )
    bid = prepare(api, bid, me(api))
    bid = call(api, bid, "final-review", {"comment": "Go"}).json()
    assert bid["phase"] == "final_reviewed" and bid["final_review"]["comment"] == "Go"
    assert all(m["done"] for m in bid["plan"])
    undone = call(api, bid, "items/need", {"note": "late edit"}, "PUT").json()
    assert undone["phase"] == "preparing" and undone["final_review"] is None
    bid = call(api, undone, "items/need/review", {"decision": "approved"}).json()
    bid = call(api, bid, "final-review", {}).json()
    receipt = {
        "receipt": "CCF-2026-0042",
        "portal": "CCF portal",
        "submitted_at": "2026-11-20T10:00:00Z",
    }
    bid = call(api, bid, "submission", receipt).json()
    assert bid["phase"] == "submitted" and bid["blocker_list"] == []
    assert bid["submission"]["receipt"] == "CCF-2026-0042"
    assert bid["submission"]["sent_by_hope"] is False
    problem(call(api, bid, "items/need", {"note": "x"}, "PUT"), 409, "bid_submitted")
    problem(call(api, bid, "submission", receipt), 409, "bid_submitted")
    actions = [
        e["payload"]["action"]
        for e in api.get(f"/v1/applications/{bid['application_id']}").json()["events"]
        if e["kind"] == "bid"
    ]
    assert actions[0] == "submission" and "final_review_undone" in actions


def test_a_passed_deadline_blocks(api: TestClient, grant: GrantCandidate) -> None:
    read(start(api, grant), requirements(deadline=date.today() - timedelta(days=1)))
    bid = prepare(api, get(api, grant), me(api))
    assert ("deadline_passed", None) in codes(bid)
    problem(call(api, bid, "final-review", {}), 409, "bid_blocked")


def test_another_tenant_cannot_see_the_bid(api: TestClient, grant: GrantCandidate) -> None:
    start(api, grant)
    with connect() as conn, tenant_tx(conn, TENANT_B) as tx:
        tx.execute("SELECT count(*) AS n FROM bids")
        assert tx.fetchone() == {"n": 0}


def test_bids_need_a_session(hope_api: TestClient) -> None:
    assert hope_api.get("/v1/bids").status_code == 401
    assert hope_api.get("/v1/members").status_code == 401


def shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [shape(v) for v in value[:1]]
    return type(value).__name__


def same(response: Any, name: str) -> dict[str, Any]:
    """The response has the status, keys and value types of `contracts/mocks/w7/<name>.json`."""
    body: dict[str, Any] = response.json()
    path = MOCKS / f"{name}.json"
    if os.environ.get("UPDATE_CONTRACT_MOCKS"):
        headers = (
            {"content-type": "application/problem+json"} if response.status_code >= 400 else {}
        )
        mock = {"status": response.status_code, "headers": headers, "body": body}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(mock, indent=2) + "\n")
    expected = json.loads(path.read_text())
    assert response.status_code == expected["status"], (name, response.text)
    assert shape(body) == shape(expected["body"]), name
    if "code" in expected["body"]:
        assert body["code"] == expected["body"]["code"], name
    return body


def test_responses_match_the_contract_mocks(api: TestClient, grant: GrantCandidate) -> None:
    owner = same(api.get("/v1/members"), "members.list/ok")["items"][0]["user_id"]
    same(api.get("/v1/bids"), "bids.list/empty")
    same(api.post("/v1/bids", json={"grant_id": str(uuid4())}), "bids.start/not_found")
    read(
        same(api.post("/v1/bids", json={"grant_id": str(grant.grant_id)}), "bids.start/created"),
        requirements(deadline=date.today() + timedelta(days=30)),
    )
    same(api.post("/v1/bids", json={"grant_id": str(grant.grant_id)}), "bids.start/existing")
    same(api.get(f"/v1/bids/{uuid4()}"), "bids.get/not_found")
    bid = same(api.get(f"/v1/bids/{grant.grant_id}"), "bids.get/ok")
    same(call(api, bid, "final-review", {}), "bids.final_review/blocked")
    same(
        call(
            api,
            bid,
            "submission",
            {"receipt": "R-1", "portal": "x", "submitted_at": "2026-11-20T10:00:00Z"},
        ),
        "bids.submission/not_final_reviewed",
    )
    same(call(api, bid, "items/need/review", {"decision": "approved"}), "bids.review/not_ready")
    same(call(api, bid, "items/need", {"owner": str(uuid4())}, "PUT"), "bids.item/unknown_member")
    same(
        call(api, bid | {"version": 0}, "items/need", {"note": "x"}, "PUT"),
        "bids.item/version_mismatch",
    )
    bid = same(
        call(
            api,
            bid,
            "items/need",
            {"owner": owner, "status": "ready", "evidence_ref": "Drive: Need.docx"},
            "PUT",
        ),
        "bids.item/ok",
    )
    same(
        call(api, bid, "items/need/review", {"decision": "changes_requested"}),
        "bids.review/comment_required",
    )
    bid = same(call(api, bid, "items/need/review", {"decision": "approved"}), "bids.review/ok")
    bid = prepare(api, bid, owner)
    bid = same(call(api, bid, "final-review", {"comment": "Ready to send"}), "bids.final_review/ok")
    receipt = {
        "receipt": "CCF-2026-0042",
        "portal": "CCF online portal",
        "submitted_at": "2026-11-20T10:00:00Z",
    }
    bid = same(call(api, bid, "submission", receipt), "bids.submission/ok")
    same(call(api, bid, "items/need", {"note": "x"}, "PUT"), "bids.item/submitted")
    same(api.get("/v1/bids"), "bids.list/ok")
