"""H3: `/v1/grants` list, detail and save / pass / reset (spec H3, AC1-AC9)."""

from __future__ import annotations

import ast
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from hope_core import store
from hope_core.db import connect, tenant_tx
from hope_core.money import Money
from hope_core.schemas.hackathon import Citation, GrantCandidate
from hope_core.settings import get_settings
from hope_pillar.api import grants

INVITE = "test-invite-code-0123456789"  # set by the hope_api fixture
TODAY = date(2026, 11, 7)
ROOT = Path(__file__).resolve().parents[3]
MOCKS = ROOT / "contracts" / "mocks" / "w4"
GRANTS_PY = ROOT / "services" / "pillar" / "src" / "hope_pillar" / "api" / "grants.py"

G88 = UUID("3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10")  # mocks: strong, later
G74 = UUID("5d1c7a90-2b3e-4f61-9c8d-0e1f2a3b4c5d")  # mocks: good, rolling
G62 = UUID("00000000-0000-4000-8000-000000000062")  # urgent, amount text only
G48 = UUID("00000000-0000-4000-8000-000000000048")  # weak, unknown deadline, no amount
G77 = UUID("00000000-0000-4000-8000-000000000077")  # soon, one unknown marker
G70 = UUID("00000000-0000-4000-8000-000000000070")  # saved
G40 = UUID("00000000-0000-4000-8000-000000000040")  # passed
G80 = UUID("00000000-0000-4000-8000-000000000080")  # past
JOB_ID = UUID("0b9f5c3e-1d2a-4c6b-9e8f-7a6b5c4d3e21")


def mock(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / f"{name}.json").read_text())
    return data


def shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [shape(v) for v in value[:1]]
    return type(value).__name__


def problem(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body: dict[str, Any] = response.json()
    assert body["code"] == code and body["status"] == status
    return body


def _marked(item: dict[str, Any]) -> str:
    ids = item["citation_ids"]
    return f"{item['text']} {''.join(f'[{i}]' for i in ids)}" if ids else item["text"]


def _from_mock(card: dict[str, Any], **extra: Any) -> GrantCandidate:
    return GrantCandidate(
        grant_id=card["grant_id"],
        title=card["title"],
        funder=card["funder"],
        url=card["url"],
        summary=card["summary"],
        amount_text=card["amount_text"],
        amount_max=card["amount_max"],
        deadline_text=card["deadline_text"],
        deadline=card["deadline"],
        fit_score=card["fit_score"],
        fit_reasons=[_marked(r) for r in card["reasons"]],
        concerns=[_marked(c) for c in card["concerns"]],
        citations=card["citations"],
        status=card["status"],
        discovered_at=card["discovered_at"],
        **extra,
    )


def _cite(n: int, quote: str) -> Citation:
    return Citation(citation_id=f"c{n}", kind="web", url="https://x.example.org", quote=quote)


def _built(
    grant_id: UUID,
    fit: int,
    *,
    title: str,
    deadline: date | None = None,
    deadline_text: str | None = None,
    amount_text: str | None = None,
    amount_max: Money | None = None,
    status: str = "new",
    discovered: str = "2026-11-06T10:00:00Z",
    reasons: list[str] | None = None,
    concerns: list[str] | None = None,
) -> GrantCandidate:
    return GrantCandidate.model_validate(
        {
            "grant_id": grant_id,
            "title": title,
            "funder": f"{title} Funder",
            "url": f"https://www.{str(grant_id)[-2:]}.example.net/grant",
            "summary": f"Support for {title.lower()}. [c1]",
            "amount_text": amount_text,
            "amount_max": amount_max,
            "deadline_text": deadline_text,
            "deadline": deadline,
            "fit_score": fit,
            "fit_reasons": reasons if reasons is not None else ["Mission match [c1]"],
            "concerns": concerns if concerns is not None else [],
            "citations": [_cite(1, "mission match"), _cite(2, "second source")],
            "status": status,
            "discovered_at": discovered,
        }
    )


def seed_candidates() -> list[GrantCandidate]:
    new, detail = mock("grants.list/new")["body"]["items"], mock("grants.get/ok")["body"]
    g88 = _from_mock(
        new[0],
        eligibility_summary=detail["eligibility_summary"],
        found_by_job_id=JOB_ID,
    ).model_copy(
        update={
            "summary": f"{detail['summary']} [c1]",
            "citations": [Citation.model_validate(c) for c in detail["citations"]],
        }
    )
    day = TODAY.fromordinal
    return [
        g88,
        _from_mock(new[1]),
        _built(
            G62,
            62,
            title="Urgent Food Access",
            deadline=day(TODAY.toordinal() + 6),
            deadline_text="Due November 13, 2026",
            amount_text="Up to $25,000",
            discovered="2026-11-06T09:00:00Z",
        ),
        _built(
            G48,
            48,
            title="Arts Weak Fit",
            deadline_text="Spring 2027",
            discovered="2026-11-07T16:00:00Z",
            reasons=["No markers here"],
        ),
        _built(
            G77,
            77,
            title="Soon Housing",
            deadline=day(TODAY.toordinal() + 18),
            deadline_text="Due November 25, 2026",
            amount_text="up to $90,000",
            amount_max=Money(amount_minor=9_000_000),
            discovered="2026-11-07T15:00:00Z",
            reasons=["Housing [c1]", "Made-up source [c9]", "Two [c2][c1]", "Fourth [c2]"],
            concerns=["Small staff [c2]", "One", "Two [c7]", "Three [c1]"],
        ),
        _built(G70, 70, title="Saved Clinic", deadline=date(2027, 1, 15), status="saved"),
        _built(G40, 40, title="Passed Library", deadline=date(2026, 12, 1), status="passed"),
        _built(
            G80,
            80,
            title="Past Water",
            deadline=day(TODAY.toordinal() - 3),
            deadline_text="Closed November 4, 2026",
            amount_max=Money(amount_minor=50_000_000),
        ),
    ]


@pytest.fixture
def api(hope_api: TestClient, migrated_db: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Signed in, `_today()` fixed to 2026-11-07, and the H3 test seed stored."""
    monkeypatch.setattr(grants, "_today", lambda: TODAY)
    settings = get_settings()
    with psycopg.connect(migrated_db) as conn:
        conn.execute(
            "INSERT INTO jobs (job_id, tenant_id, kind, status)"
            " VALUES (%s, %s, 'discovery', 'done')",
            (JOB_ID, settings.tenant_id),
        )
    with connect() as conn, tenant_tx(conn, settings.tenant_id) as tx:
        for candidate in seed_candidates():
            store.upsert_candidate(tx, candidate)
    response = hope_api.post(
        "/v1/auth/signup",
        json={
            "email": "curator@riverbend.example.org",
            "password": "correct-horse-battery",
            "display_name": "Curator",
            "invite_code": INVITE,
        },
    )
    assert response.status_code == 201, response.text
    return hope_api


def ids(body: dict[str, Any]) -> list[UUID]:
    return [UUID(item["grant_id"]) for item in body["items"]]


def listing(api: TestClient, **params: Any) -> dict[str, Any]:
    response = api.get("/v1/grants", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def db_row(admin_url: str, grant_id: UUID) -> dict[str, Any]:
    with psycopg.connect(admin_url, row_factory=psycopg.rows.dict_row) as conn:
        row = conn.execute("SELECT * FROM grant_candidates WHERE grant_id = %s", (grant_id,))
        found = row.fetchone()
    assert found is not None
    return found


# --- AC1 ---------------------------------------------------------------------------------------


@pytest.mark.db
def test_list_sorts_counts_hidden_past(api: TestClient) -> None:
    counts = {"new": 6, "saved": 1, "passed": 1}
    default = listing(api)
    assert ids(default) == [G88, G77, G74, G62, G48]
    assert (default["total"], default["counts"], default["hidden_past"]) == (5, counts, 1)
    assert (default["limit"], default["offset"]) == (20, 0)
    assert {i["status"] for i in default["items"]} == {"new"}

    assert ids(listing(api, sort="deadline")) == [G62, G77, G88, G74, G48]
    assert ids(listing(api, sort="amount")) == [G77, G88, G74, G62, G48]
    assert ids(listing(api, sort="newest")) == [G48, G77, G88, G74, G62]
    assert ids(listing(api, status="new", sort="fit")) == ids(default)

    with_past = listing(api, include_past=True)
    assert ids(with_past) == [G88, G80, G77, G74, G62, G48]
    assert (with_past["total"], with_past["hidden_past"]) == (6, 0)
    assert ids(listing(api, include_past=True, sort="deadline"))[:2] == [G80, G62]
    assert ids(listing(api, include_past=True, sort="amount"))[0] == G80

    saved = listing(api, status="saved")
    assert (ids(saved), saved["total"], saved["counts"], saved["hidden_past"]) == (
        [G70],
        1,
        counts,
        0,
    )
    passed = listing(api, status="passed")
    assert (ids(passed), passed["counts"], passed["hidden_past"]) == ([G40], counts, 0)


@pytest.mark.db
def test_sort_amount_puts_non_usd_with_unknown(api: TestClient) -> None:
    settings = get_settings()
    with connect() as conn, tenant_tx(conn, settings.tenant_id) as tx:
        euro = _built(
            uuid4(),
            99,
            title="Euro Fund",
            amount_max=Money(amount_minor=99_000_000, currency="EUR"),
        )
        store.upsert_candidate(tx, euro)
    order = ids(listing(api, sort="amount"))
    assert order[:3] == [G77, G88, G74]
    assert order[3:] == [euro.grant_id, G62, G48]


# --- AC2 ---------------------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.parametrize(
    ("params", "expected", "total"),
    [
        ({"q": "cascade"}, [G88], 1),
        ({"q": "crcf.EXAMPLE"}, [G74], 1),
        ({"q": "DENTAL"}, [G88], 1),
        ({"q": "housing"}, [G77], 1),
        ({"q": "no such grant"}, [], 0),
        ({"q": "water"}, [], 0),
        ({"q": "water", "include_past": "true"}, [G80], 1),
        ({"deadline_within_days": 7}, [G62], 1),
        ({"deadline_within_days": 21}, [G77, G62], 2),
        ({"deadline_within_days": 365}, [G88, G77, G62], 3),
        ({"deadline_within_days": 365, "include_past": "true"}, [G88, G77, G62], 3),
        ({"limit": 1}, [G88], 5),
        ({"limit": 2, "offset": 2}, [G74, G62], 5),
        ({"offset": 4}, [G48], 5),
        ({"offset": 10}, [], 5),
        ({"status": "passed", "q": "library"}, [G40], 1),
    ],
)
def test_list_filters_paging(
    api: TestClient, params: dict[str, Any], expected: list[UUID], total: int
) -> None:
    body = listing(api, **params)
    assert ids(body) == expected
    assert body["total"] == total
    assert body["limit"] == params.get("limit", 20) and body["offset"] == params.get("offset", 0)
    assert body["counts"] == {"new": 6, "saved": 1, "passed": 1}


@pytest.mark.db
def test_list_hidden_past_follows_q(api: TestClient) -> None:
    assert listing(api, q="water")["hidden_past"] == 1
    assert listing(api, q="cascade")["hidden_past"] == 0


@pytest.mark.db
@pytest.mark.parametrize(
    ("params", "parameter"),
    [
        ({"sort": "bogus"}, "sort"),
        ({"status": "deleted"}, "status"),
        ({"q": ""}, "q"),
        ({"q": "x" * 101}, "q"),
        ({"deadline_within_days": 0}, "deadline_within_days"),
        ({"deadline_within_days": 366}, "deadline_within_days"),
        ({"deadline_within_days": "soon"}, "deadline_within_days"),
        ({"include_past": "maybe"}, "include_past"),
        ({"limit": 0}, "limit"),
        ({"limit": 101}, "limit"),
        ({"offset": -1}, "offset"),
    ],
)
def test_invalid_query(api: TestClient, params: dict[str, Any], parameter: str) -> None:
    body = problem(api.get("/v1/grants", params=params), 422, "invalid_query")
    assert body["detail"] == parameter
    assert set(body) == {"type", "title", "status", "code", "detail"}


# --- AC3 ---------------------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.parametrize(
    ("grant_id", "urgency", "days_left", "band"),
    [
        (G80, "past", -3, "strong"),
        (G62, "urgent", 6, "good"),
        (G77, "soon", 18, "strong"),
        (G88, "later", 116, "strong"),
        (G74, "rolling", None, "good"),
        (G48, "unknown", None, "weak"),
    ],
)
def test_derived_urgency_and_band(
    api: TestClient, grant_id: UUID, urgency: str, days_left: int | None, band: str
) -> None:
    detail = api.get(f"/v1/grants/{grant_id}").json()
    assert (detail["urgency"], detail["days_left"], detail["fit_band"]) == (
        urgency,
        days_left,
        band,
    )
    listed = listing(api, include_past=True, limit=100)
    card = next(i for i in listed["items"] if UUID(i["grant_id"]) == grant_id)
    assert (card["urgency"], card["days_left"], card["fit_band"]) == (urgency, days_left, band)


def test_derivation_boundaries() -> None:
    assert [grants.urgency(d, None) for d in (-1, 0, 7, 8, 21, 22)] == [
        "past",
        "urgent",
        "urgent",
        "soon",
        "soon",
        "later",
    ]
    assert grants.urgency(None, "Ongoing") == "rolling"
    assert grants.urgency(None, "Open until funds run out") == "rolling"
    assert grants.urgency(None, None) == "unknown"
    assert [grants.fit_band(s) for s in (100, 75, 74, 55, 54, 0)] == [
        "strong",
        "strong",
        "good",
        "good",
        "weak",
        "weak",
    ]
    assert grants.days_left(date(2026, 11, 8), TODAY) == 1
    assert grants.domain("https://WWW.Example.org:8443/a?b") == "example.org"
    assert grants.domain("https://sub.www.example.org/") == "sub.www.example.org"
    assert grants._today() in {datetime.now(UTC).date(), date.today()}


# --- AC4 ---------------------------------------------------------------------------------------


def test_reason_citation_parsing() -> None:
    known = {"c1", "c2", "c3"}
    cases = [
        ("Matches mission [c1][c3]", "Matches mission", ["c1", "c3"], False),
        ("Spaced markers [c1] [c2] ", "Spaced markers", ["c1", "c2"], False),
        ("No markers at all", "No markers at all", [], True),
        ("Unknown marker [c9]", "Unknown marker", [], True),
        ("One known one unknown [c2][c9]", "One known one unknown", ["c2"], True),
        ("Repeated [c1][c1]", "Repeated", ["c1"], False),
        ("Mid-text [c1] marker stays", "Mid-text [c1] marker stays", [], True),
        ("Mid [c2] and trailing [c3]", "Mid [c2] and trailing", ["c3"], False),
        ("", "", [], True),
    ]
    for raw, text, citation_ids, unverified in cases:
        item = grants.parse_cited(raw, known)
        assert (item.text, item.citation_ids, item.unverified) == (text, citation_ids, unverified)

    assert grants.summary_markers("Funds care [c1] in WA. [c2][c8]", known) == (
        "Funds care in WA.",
        ["c1", "c2"],
    )
    cites = [_cite(1, "Awards of up to $75,000 per year"), _cite(2, "Applications are due May 1")]
    assert grants.first_quoting(cites, "up to $75,000 PER year") == "c1"
    assert grants.first_quoting(cites, "Applications due May 1") == "c2"
    assert grants.first_quoting(cites, "due June 1") is None
    assert grants.first_quoting(cites, None) is None


@pytest.mark.db
def test_list_and_detail_keep_every_item(api: TestClient) -> None:
    detail = api.get(f"/v1/grants/{G77}").json()
    assert [r["text"] for r in detail["reasons"]] == ["Housing", "Made-up source", "Two", "Fourth"]
    assert [r["unverified"] for r in detail["reasons"]] == [False, True, False, False]
    assert detail["reasons"][2]["citation_ids"] == ["c2", "c1"]
    assert [c["unverified"] for c in detail["concerns"]] == [False, True, True, False]
    card = next(i for i in listing(api)["items"] if UUID(i["grant_id"]) == G77)
    assert [r["text"] for r in card["reasons"]] == ["Housing", "Made-up source", "Two"]
    assert [c["text"] for c in card["concerns"]] == ["Small staff", "One", "Two"]
    assert [c["citation_id"] for c in card["citations"]] == ["c1", "c2"]
    weak = api.get(f"/v1/grants/{G48}").json()
    assert weak["reasons"] == [{"text": "No markers here", "citation_ids": [], "unverified": True}]


# --- AC5 ---------------------------------------------------------------------------------------


@pytest.mark.db
def test_save_pass_reset_idempotent(api: TestClient, migrated_db: str) -> None:
    before = api.get(f"/v1/grants/{G88}").json()
    url = f"/v1/grants/{G88}"

    saved = api.post(f"{url}/save")
    assert saved.json() == {
        "grant_id": str(G88),
        "status": "saved",
        "previous_status": "new",
        "changed": True,
    }
    first = db_row(migrated_db, G88)
    assert first["status_changed_at"] is not None and first["status_changed_by"] is not None
    again = api.post(f"{url}/save").json()
    assert (again["changed"], again["previous_status"]) == (False, "saved")
    assert db_row(migrated_db, G88)["status_changed_at"] == first["status_changed_at"]
    assert listing(api)["counts"] == {"new": 5, "saved": 2, "passed": 1}

    passed = api.post(f"{url}/pass", json={"reason": "too_small"}).json()
    assert (passed["status"], passed["previous_status"], passed["changed"]) == (
        "passed",
        "saved",
        True,
    )
    row = db_row(migrated_db, G88)
    assert (row["pass_reason"], row["pass_reason_text"]) == ("too_small", None)
    assert api.post(f"{url}/pass", json={"reason": "other"}).json()["changed"] is False
    assert db_row(migrated_db, G88)["pass_reason"] == "too_small"

    reset = api.post(f"{url}/reset").json()
    assert (reset["status"], reset["previous_status"], reset["changed"]) == ("new", "passed", True)
    assert db_row(migrated_db, G88)["pass_reason"] is None
    assert api.post(f"{url}/reset").json()["changed"] is False

    assert api.post(f"{url}/pass").json()["changed"] is True
    assert api.post(f"{url}/reset").status_code == 200
    assert api.post(f"{url}/pass", json={}).json()["changed"] is True
    assert api.post(f"{url}/reset").status_code == 200

    after = api.get(url).json()
    assert after == before
    for path in ("save", "pass", "reset"):
        problem(api.post(f"/v1/grants/{uuid4()}/{path}"), 404, "grant_not_found")


@pytest.mark.db
@pytest.mark.parametrize(
    ("body", "ok"),
    [
        ({"reason": "not_a_fit"}, True),
        ({"reason": "deadline_too_soon"}, True),
        ({"reason": "not_eligible"}, True),
        ({"reason": "other", "reason_text": "Board said no"}, True),
        ({"reason": "other", "reason_text": "x" * 300}, True),
        ({"reason": "other"}, True),
        ({"reason": "bogus"}, False),
        ({"reason": "too_small", "reason_text": "too little"}, False),
        ({"reason_text": "no reason given"}, False),
        ({"reason": "other", "reason_text": "x" * 301}, False),
        ({"reason": "other", "note": "extra field"}, False),
        ({"reason": 3}, False),
        ([], False),
    ],
)
def test_pass_reason_validation(api: TestClient, migrated_db: str, body: Any, ok: bool) -> None:
    response = api.post(f"/v1/grants/{G62}/pass", json=body)
    if ok:
        assert response.status_code == 200, response.text
        row = db_row(migrated_db, G62)
        assert (row["status"], row["pass_reason"], row["pass_reason_text"]) == (
            "passed",
            body["reason"],
            body.get("reason_text"),
        )
    else:
        problem(response, 422, "invalid_reason")
        assert db_row(migrated_db, G62)["status"] == "new"


@pytest.mark.db
def test_pass_rejects_malformed_json(api: TestClient) -> None:
    response = api.post(
        f"/v1/grants/{G62}/pass", content=b"{not json", headers={"content-type": "application/json"}
    )
    problem(response, 422, "invalid_reason")


# --- AC6 ---------------------------------------------------------------------------------------


@pytest.mark.db
def test_detail_and_not_found(api: TestClient) -> None:
    detail = api.get(f"/v1/grants/{G88}")
    assert detail.status_code == 200
    assert detail.json() == mock("grants.get/ok")["body"]
    rolling = api.get(f"/v1/grants/{G74}").json()
    assert rolling["eligibility_summary"] is None and rolling["found_by_job_id"] is None
    assert rolling["view_original_url"] == rolling["url"]
    assert (rolling["amount_citation_id"], rolling["deadline_citation_id"]) == (None, None)
    for missing in (uuid4(), "not-a-uuid"):
        body = problem(api.get(f"/v1/grants/{missing}"), 404, "grant_not_found")
        assert body == mock("grants.get/not_found")["body"]


# --- AC7 ---------------------------------------------------------------------------------------


@pytest.mark.db
def test_requires_session(hope_api: TestClient) -> None:
    gid = uuid4()
    for response in (
        hope_api.get("/v1/grants"),
        hope_api.get("/v1/grants", params={"sort": "bogus"}),
        hope_api.get(f"/v1/grants/{gid}"),
        hope_api.post(f"/v1/grants/{gid}/save"),
        hope_api.post(f"/v1/grants/{gid}/pass", json={"reason": "too_small"}),
        hope_api.post(f"/v1/grants/{gid}/reset"),
    ):
        problem(response, 401, "not_signed_in")
    hope_api.cookies.set("hope_session", "forged")
    problem(hope_api.get("/v1/grants"), 401, "not_signed_in")


# --- AC8 ---------------------------------------------------------------------------------------


def _scenario(api: TestClient, name: str) -> Any:
    if name == "grants.list/new":
        return api.get("/v1/grants")
    if name == "grants.list/saved":
        api.post(f"/v1/grants/{G88}/save")
        return api.get("/v1/grants", params={"status": "saved"})
    if name == "grants.list/empty":
        return api.get("/v1/grants", params={"q": "nothing matches this"})
    if name == "grants.list/invalid_query":
        return api.get("/v1/grants", params={"sort": "bogus"})
    if name == "grants.get/ok":
        return api.get(f"/v1/grants/{G88}")
    if name == "grants.get/not_found":
        return api.get(f"/v1/grants/{uuid4()}")
    if name == "grants.save/ok":
        return api.post(f"/v1/grants/{G88}/save")
    if name == "grants.save/not_found":
        return api.post(f"/v1/grants/{uuid4()}/save")
    if name == "grants.pass/ok":
        return api.post(f"/v1/grants/{G88}/pass", json=mock("grants.pass/request"))
    if name == "grants.pass/invalid_reason":
        return api.post(f"/v1/grants/{G88}/pass", json={"reason": "bogus"})
    if name == "grants.reset/ok":
        api.post(f"/v1/grants/{G88}/save")
        return api.post(f"/v1/grants/{G88}/reset")
    raise AssertionError(name)


SCENARIOS = [
    "grants.list/new",
    "grants.list/saved",
    "grants.list/empty",
    "grants.list/invalid_query",
    "grants.get/ok",
    "grants.get/not_found",
    "grants.save/ok",
    "grants.save/not_found",
    "grants.pass/ok",
    "grants.pass/invalid_reason",
    "grants.reset/ok",
]


@pytest.mark.db
@pytest.mark.parametrize("name", SCENARIOS)
def test_matches_contract_mocks(api: TestClient, name: str) -> None:
    expected = mock(name)
    response = _scenario(api, name)
    assert response.status_code == expected["status"], (name, response.text)
    body = response.json()
    assert shape(body) == shape(expected["body"]), name
    if "content-type" in expected["headers"]:
        assert response.headers["content-type"] == expected["headers"]["content-type"]
        assert body == expected["body"]
    if name.startswith(("grants.save/ok", "grants.pass/ok", "grants.reset/ok")):
        assert body == expected["body"]
    if name in ("grants.list/new", "grants.list/saved"):
        mocked = {i["grant_id"]: i for i in expected["body"]["items"]}
        for item in body["items"]:
            assert isinstance(item["amount_max"] or {"amount_minor": 0}, dict)
            if item["amount_max"]:
                assert type(item["amount_max"]["amount_minor"]) is int
            if item["grant_id"] in mocked:
                assert item == mocked[item["grant_id"]]
        assert set(mocked) <= {i["grant_id"] for i in body["items"]}


def test_every_w4_mock_is_covered() -> None:
    found = {str(p.relative_to(MOCKS).with_suffix("")) for p in MOCKS.glob("*/*.json")}
    assert found == {*SCENARIOS, "grants.pass/request"}


# --- AC9 ---------------------------------------------------------------------------------------

_SQL_WORDS = ("select ", "insert ", "update ", "delete ", " from ", " where ", "returning")


def test_router_has_no_sql_or_model_calls() -> None:
    tree = ast.parse(GRANTS_PY.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported |= {f"{node.module}.{a.name}" for a in node.names}
        elif isinstance(node, ast.Attribute):
            assert node.attr not in {"execute", "executemany", "fetchone", "fetchall"}, node.attr
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = f" {node.value.lower()} "
            assert not any(w in text for w in _SQL_WORDS), node.value
    banned = ("hope_core.model_gateway", "hope_core.web", "hope_core.openai_provider", "openai")
    assert not [m for m in imported if m.startswith(banned) or m.endswith("ModelGateway")]
    assert "psycopg" not in imported
