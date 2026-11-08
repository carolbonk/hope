"""H3 grants API: listing, derived fields, citations, save / pass / reset and the W4 contract."""

from __future__ import annotations

import ast
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from hope_core import store
from hope_core.db import connect, tenant_tx
from hope_core.money import Money
from hope_core.schemas import GrantCandidate
from hope_core.settings import get_settings
from hope_pillar.api import grants

INVITE = "test-invite-code-0123456789"  # set by the hope_api fixture
TODAY = date(2026, 11, 7)
MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks" / "w4"
GRANTS_PY = Path(grants.__file__)


def mock(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / f"{name}.json").read_text())
    return data


def problem(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body: dict[str, Any] = response.json()
    assert body["code"] == code and body["status"] == status
    return body


def with_markers(item: dict[str, Any]) -> str:
    return item["text"] + (
        " " + "".join(f"[{c}]" for c in item["citation_ids"]) if item["citation_ids"] else ""
    )


def from_mock(card: dict[str, Any], **overrides: Any) -> GrantCandidate:
    """Rebuild the stored candidate behind a W4 mock card (markers back on the text)."""
    data = {k: card[k] for k in GrantCandidate.model_fields if k in card}
    data["fit_reasons"] = [with_markers(r) for r in card["reasons"]]
    data["concerns"] = [with_markers(c) for c in card["concerns"]]
    data.update(overrides)
    return GrantCandidate.model_validate(data)


def built(name: str, score: int, days: int | None, minute: int, **overrides: Any) -> GrantCandidate:
    data: dict[str, Any] = {
        "grant_id": uuid4(),
        "title": f"{name} Grant",
        "funder": f"{name} Foundation",
        "url": f"https://www.{name.lower()}.example.org/grant",
        "summary": f"Support for {name.lower()} programs.",
        "deadline": TODAY + timedelta(days=days) if days is not None else None,
        "deadline_text": f"Due in {days} days" if days is not None else None,
        "fit_score": score,
        "fit_reasons": [f"Matches {name}"],
        "discovered_at": datetime(2026, 11, 7, 15, minute, tzinfo=UTC),
    }
    data.update(overrides)
    return GrantCandidate.model_validate(data)


def seed_rows() -> dict[str, GrantCandidate]:
    detail = mock("grants.get/ok")["body"]
    first, second = mock("grants.list/new")["body"]["items"]
    return {
        "A": from_mock(
            detail,
            summary=detail["summary"] + " [c1]",
            eligibility_summary=detail["eligibility_summary"],
            found_by_job_id=detail["found_by_job_id"],
        ),
        "B": from_mock(second, discovered_at=datetime(2026, 11, 7, 14, 3, tzinfo=UTC)),
        "C": built("Urgent", 62, 6, 10, amount_text="Up to $20,000"),
        "D": built("Weak", 48, None, 20, deadline_text="Spring 2027"),
        "E": built(
            "Soon",
            77,
            18,
            30,
            amount_max=Money(amount_minor=2_500_000),
            fit_reasons=["Serves your county [c1][c9]", "Second", "Third", "Fourth"],
            citations=[first["citations"][0]],
        ),
        "F": built("Saved", 70, 40, 40, status="saved"),
        "G": built("Passed", 40, -10, 50, status="passed"),
        "H": built("Past", 80, -3, 55),
    }


@pytest.fixture
def api(hope_api: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(grants, "_today", lambda: TODAY)
    response = hope_api.post(
        "/v1/auth/signup",
        json={
            "email": "grants@riverbend.example.org",
            "password": "long-enough-pw",
            "display_name": "Grants",
            "invite_code": INVITE,
        },
    )
    assert response.status_code == 201, response.text
    return hope_api


@pytest.fixture
def seeded(api: TestClient, migrated_db: str) -> dict[str, GrantCandidate]:
    rows = seed_rows()
    with psycopg.connect(migrated_db) as conn:
        conn.execute(
            "INSERT INTO jobs (job_id, tenant_id, kind) VALUES (%s, %s, 'discovery')",
            (rows["A"].found_by_job_id, get_settings().tenant_id),
        )
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        for row in rows.values():
            store.upsert_candidate(tx, row)
    return rows


def ids(body: dict[str, Any], rows: dict[str, GrantCandidate]) -> list[str]:
    names = {str(g.grant_id): name for name, g in rows.items()}
    return [names[item["grant_id"]] for item in body["items"]]


@pytest.mark.db
def test_list_sorts_counts_hidden_past(api: TestClient, seeded: dict[str, GrantCandidate]) -> None:
    expected = {
        "fit": ["A", "E", "B", "C", "D"],
        "deadline": ["C", "E", "A", "B", "D"],
        "amount": ["A", "B", "E", "C", "D"],
        "newest": ["E", "D", "C", "B", "A"],
    }
    for sort, order in expected.items():
        body = api.get("/v1/grants", params={"sort": sort}).json()
        assert ids(body, seeded) == order, sort
        assert body["total"] == 5 and body["hidden_past"] == 1
        assert body["counts"] == {"new": 6, "saved": 1, "passed": 1}
        assert (body["limit"], body["offset"]) == (20, 0)
    default = api.get("/v1/grants").json()
    assert ids(default, seeded) == expected["fit"]


@pytest.mark.db
@pytest.mark.parametrize(
    ("params", "expected", "total", "hidden_past"),
    [
        ({"q": "DENTAL"}, ["A"], 1, 0),
        ({"q": " crcf.example "}, ["B"], 1, 0),
        ({"q": "soon foundation"}, ["E"], 1, 0),
        ({"deadline_within_days": "7"}, ["C"], 1, 1),
        ({"deadline_within_days": "30"}, ["E", "C"], 2, 1),
        ({"include_past": "true"}, ["A", "H", "E", "B", "C", "D"], 6, 0),
        ({"include_past": "true", "deadline_within_days": "7"}, ["C"], 1, 0),
        ({"limit": "2"}, ["A", "E"], 5, 1),
        ({"limit": "2", "offset": "4"}, ["D"], 5, 1),
        ({"offset": "9"}, [], 5, 1),
        ({"status": "saved"}, ["F"], 1, 0),
        ({"status": "passed"}, ["G"], 1, 0),
        ({"status": "new", "limit": "1"}, ["A"], 5, 1),
    ],
)
def test_list_filters_paging(
    api: TestClient,
    seeded: dict[str, GrantCandidate],
    params: dict[str, str],
    expected: list[str],
    total: int,
    hidden_past: int,
) -> None:
    body = api.get("/v1/grants", params=params).json()
    assert ids(body, seeded) == expected
    assert body["total"] == total and body["hidden_past"] == hidden_past
    assert body["counts"] == {"new": 6, "saved": 1, "passed": 1}
    assert body["limit"] == int(params.get("limit", 20))
    assert body["offset"] == int(params.get("offset", 0))


@pytest.mark.db
@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("status", "archived"),
        ("sort", "random"),
        ("q", ""),
        ("q", "   "),
        ("q", "x" * 101),
        ("deadline_within_days", "0"),
        ("deadline_within_days", "366"),
        ("deadline_within_days", "soon"),
        ("include_past", "maybe"),
        ("limit", "0"),
        ("limit", "101"),
        ("offset", "-1"),
        ("offset", "1.5"),
        ("offset", "9" * 5000),
    ],
)
def test_invalid_query(api: TestClient, param: str, value: str) -> None:
    body = problem(api.get("/v1/grants", params={param: value}), 422, "invalid_query")
    assert body["detail"] == param


@pytest.mark.db
@pytest.mark.parametrize(
    ("name", "days_left", "urgency", "band"),
    [
        ("H", -3, "past", "strong"),
        ("C", 6, "urgent", "good"),
        ("E", 18, "soon", "strong"),
        ("A", 116, "later", "strong"),
        ("B", None, "rolling", "good"),
        ("D", None, "unknown", "weak"),
    ],
)
def test_derived_urgency_and_band(
    api: TestClient,
    seeded: dict[str, GrantCandidate],
    name: str,
    days_left: int | None,
    urgency: str,
    band: str,
) -> None:
    body = api.get(f"/v1/grants/{seeded[name].grant_id}").json()
    assert (body["days_left"], body["urgency"], body["fit_band"]) == (days_left, urgency, band)
    listed = api.get("/v1/grants", params={"include_past": "true"}).json()["items"]
    card = next(c for c in listed if c["grant_id"] == body["grant_id"])
    assert (card["days_left"], card["urgency"], card["fit_band"]) == (days_left, urgency, band)


def test_derived_thresholds() -> None:
    assert [grants.fit_band(s) for s in (100, 75, 74, 55, 54, 0)] == [
        "strong",
        "strong",
        "good",
        "good",
        "weak",
        "weak",
    ]

    def day(days: int) -> date:
        return TODAY + timedelta(days=days)

    assert grants.urgency(day(days=-1), None, TODAY) == "past"
    assert grants.urgency(TODAY, None, TODAY) == "urgent"
    assert grants.urgency(day(days=7), None, TODAY) == "urgent"
    assert grants.urgency(day(days=8), None, TODAY) == "soon"
    assert grants.urgency(day(days=21), None, TODAY) == "soon"
    assert grants.urgency(day(days=22), None, TODAY) == "later"
    assert grants.urgency(None, "Ongoing", TODAY) == "rolling"
    assert grants.urgency(None, "Open until funds run out", TODAY) == "rolling"
    assert grants.urgency(None, None, TODAY) == "unknown"
    assert grants.domain("https://www.example.org/x?y=1") == "example.org"
    assert grants.domain("https://sub.www.example.org") == "sub.www.example.org"


def test_reason_citation_parsing() -> None:
    known = {"c1", "c2", "c3"}
    parse = grants.cited_item
    assert parse("Funds dental care [c1][c3]", known).model_dump() == {
        "text": "Funds dental care",
        "citation_ids": ["c1", "c3"],
        "unverified": False,
    }
    assert parse("Spaced markers [c2] [c1] ", known).citation_ids == ["c2", "c1"]
    unknown = parse("Serves your county [c1][c9]", known)
    assert (unknown.text, unknown.citation_ids, unknown.unverified) == (
        "Serves your county",
        ["c1"],
        True,
    )
    bare = parse("Award size fits your budget", known)
    assert (bare.text, bare.citation_ids, bare.unverified) == (
        "Award size fits your budget",
        [],
        True,
    )
    middle = parse("See [c1] for details", known)
    assert (middle.text, middle.citation_ids, middle.unverified) == (
        "See [c1] for details",
        [],
        True,
    )
    only_unknown = parse("Unknown [c7]", known)
    assert (only_unknown.text, only_unknown.citation_ids, only_unknown.unverified) == (
        "Unknown",
        [],
        True,
    )


@pytest.mark.db
def test_reasons_on_list_and_detail(api: TestClient, seeded: dict[str, GrantCandidate]) -> None:
    gid = str(seeded["E"].grant_id)
    card = next(c for c in api.get("/v1/grants").json()["items"] if c["grant_id"] == gid)
    assert [r["text"] for r in card["reasons"]] == ["Serves your county", "Second", "Third"]
    assert card["reasons"][0] == {
        "text": "Serves your county",
        "citation_ids": ["c1"],
        "unverified": True,
    }
    assert [c["citation_id"] for c in card["citations"]] == ["c1"]
    detail = api.get(f"/v1/grants/{gid}").json()
    assert [r["text"] for r in detail["reasons"]] == [
        "Serves your county",
        "Second",
        "Third",
        "Fourth",
    ]
    assert all(r["unverified"] for r in detail["reasons"][1:])


@pytest.mark.db
def test_save_pass_reset_idempotent(
    api: TestClient, seeded: dict[str, GrantCandidate], migrated_db: str
) -> None:
    gid = str(seeded["A"].grant_id)

    def columns() -> tuple[Any, ...]:
        with psycopg.connect(migrated_db) as conn:
            row = conn.execute(
                "SELECT status, status_changed_at, pass_reason, pass_reason_text, status_changed_by"
                " FROM grant_candidates WHERE grant_id = %s",
                (gid,),
            ).fetchone()
        assert row is not None
        return tuple(row)

    def change(action: str, **kwargs: Any) -> dict[str, Any]:
        response = api.post(f"/v1/grants/{gid}/{action}", **kwargs)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    before = api.get(f"/v1/grants/{gid}").json()
    assert change("save") == {
        "grant_id": gid,
        "status": "saved",
        "previous_status": "new",
        "changed": True,
    }
    saved = columns()
    assert saved[0] == "saved" and saved[4] is not None
    assert change("save")["changed"] is False
    assert columns() == saved

    assert change("pass", json={"reason": "too_small"}) == {
        "grant_id": gid,
        "status": "passed",
        "previous_status": "saved",
        "changed": True,
    }
    assert columns()[2:4] == ("too_small", None)
    passed = columns()
    assert change("pass", json={"reason": "other", "reason_text": "x"})["changed"] is False
    assert columns() == passed

    assert change("reset") == {
        "grant_id": gid,
        "status": "new",
        "previous_status": "passed",
        "changed": True,
    }
    assert columns()[0] == "new" and columns()[2:4] == (None, None)
    assert change("reset")["changed"] is False
    assert change("pass")["status"] == "passed"
    assert change("reset")["previous_status"] == "passed"

    after = api.get(f"/v1/grants/{gid}").json()
    assert {k: v for k, v in after.items() if k != "status"} == {
        k: v for k, v in before.items() if k != "status"
    }
    for action in ("save", "pass", "reset"):
        problem(api.post(f"/v1/grants/{uuid4()}/{action}"), 404, "grant_not_found")
        problem(api.post(f"/v1/grants/not-a-uuid/{action}"), 404, "grant_not_found")


@pytest.mark.db
@pytest.mark.parametrize(
    "body",
    [
        {"reason": "bogus"},
        {"reason_text": "why"},
        {"reason": "too_small", "reason_text": "why"},
        {"reason": "other", "reason_text": "x" * 301},
        {"reason": "other", "extra": 1},
        ["not_a_fit"],
        "not json",
    ],
)
def test_pass_reason_validation(
    api: TestClient, seeded: dict[str, GrantCandidate], body: Any
) -> None:
    gid = str(seeded["A"].grant_id)
    content = body if isinstance(body, str) else json.dumps(body)
    response = api.post(
        f"/v1/grants/{gid}/pass", content=content, headers={"content-type": "application/json"}
    )
    problem(response, 422, "invalid_reason")
    assert api.get(f"/v1/grants/{gid}").json()["status"] == "new"


@pytest.mark.db
@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"reason": None},
        {"reason": "not_eligible"},
        {"reason": "other", "reason_text": "x" * 300},
    ],
)
def test_pass_accepts_valid_bodies(
    api: TestClient, seeded: dict[str, GrantCandidate], body: Any
) -> None:
    gid = str(seeded["C"].grant_id)
    response = api.post(f"/v1/grants/{gid}/pass", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "passed"


@pytest.mark.db
def test_detail_and_not_found(api: TestClient, seeded: dict[str, GrantCandidate]) -> None:
    expected = mock("grants.get/ok")["body"]
    body = api.get(f"/v1/grants/{seeded['A'].grant_id}").json()
    assert (body["amount_citation_id"], body["deadline_citation_id"]) == ("c5", "c6")
    assert body == expected
    problem(api.get(f"/v1/grants/{uuid4()}"), 404, "grant_not_found")
    problem(api.get("/v1/grants/not-a-uuid"), 404, "grant_not_found")


@pytest.mark.db
def test_requires_session(hope_api: TestClient) -> None:
    gid = uuid4()
    for method, path in [
        ("GET", "/v1/grants"),
        ("GET", f"/v1/grants/{gid}"),
        ("POST", f"/v1/grants/{gid}/save"),
        ("POST", f"/v1/grants/{gid}/pass"),
        ("POST", f"/v1/grants/{gid}/reset"),
    ]:
        problem(hope_api.request(method, path), 401, "not_signed_in")


def shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [shape(v) for v in value[:1]]
    return type(value).__name__


def compatible(actual: Any, expected: Any) -> bool:
    """Same keys and value types; `null` on either side matches any type (nullable fields)."""
    if "NoneType" in (actual, expected):
        return True
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and actual.keys() == expected.keys()
            and all(compatible(actual[k], expected[k]) for k in expected)
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and all(map(compatible, actual, expected))
    return bool(actual == expected)


SCENARIOS: list[tuple[str, str, str, Any, str | None]] = [
    # (mock, method, path ({A} = seeded grant), json body, setup action on {A})
    ("grants.list/new", "GET", "/v1/grants", None, None),
    ("grants.list/saved", "GET", "/v1/grants?status=saved&include_past=true", None, "save"),
    ("grants.list/empty", "GET", "/v1/grants?status=passed&q=nothing-matches", None, None),
    ("grants.list/invalid_query", "GET", "/v1/grants?sort=bogus", None, None),
    ("grants.get/ok", "GET", "/v1/grants/{A}", None, None),
    ("grants.get/not_found", "GET", "/v1/grants/{missing}", None, None),
    ("grants.save/ok", "POST", "/v1/grants/{A}/save", None, None),
    ("grants.save/not_found", "POST", "/v1/grants/{missing}/save", None, None),
    ("grants.pass/ok", "POST", "/v1/grants/{A}/pass", "grants.pass/request", None),
    ("grants.pass/invalid_reason", "POST", "/v1/grants/{A}/pass", {"reason": "nope"}, None),
    ("grants.reset/ok", "POST", "/v1/grants/{A}/reset", None, "save"),
]


@pytest.mark.db
@pytest.mark.parametrize(("name", "method", "path", "body", "setup"), SCENARIOS)
def test_matches_contract_mocks(
    api: TestClient,
    seeded: dict[str, GrantCandidate],
    name: str,
    method: str,
    path: str,
    body: Any,
    setup: str | None,
) -> None:
    gid = str(seeded["A"].grant_id)
    if setup:
        assert api.post(f"/v1/grants/{gid}/{setup}").status_code == 200
    url = path.format(A=gid, missing=uuid4())
    payload = mock(body) if isinstance(body, str) else body
    response = api.request(method, url, json=payload)
    expected = mock(name)
    assert response.status_code == expected["status"], response.text
    actual = response.json()
    assert compatible(shape(actual), shape(expected["body"])), (shape(actual), name)
    if "code" in expected["body"]:
        assert actual["code"] == expected["body"]["code"]
        assert actual.get("detail") == expected["body"].get("detail")
        assert response.headers["content-type"] == expected["headers"]["content-type"]
    if "items" in actual:
        for item in actual["items"]:
            amount = item["amount_max"]
            assert amount is None or isinstance(amount["amount_minor"], int)
    if "previous_status" in expected["body"]:
        assert actual == expected["body"] | {"grant_id": gid}


def test_every_w4_mock_is_covered() -> None:
    covered = {s[0] for s in SCENARIOS} | {"grants.pass/request"}
    found = {str(p.relative_to(MOCKS).with_suffix("")) for p in MOCKS.glob("*/*.json")}
    assert found == covered


SQL = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE)\b")
BANNED_MODULES = ("hope_core.web", "hope_core.model_gateway", "openai")


def test_router_has_no_sql_or_model_calls() -> None:
    tree = ast.parse(GRANTS_PY.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            modules = [a.name for a in node.names]
            if isinstance(node, ast.ImportFrom):
                modules = [node.module or "", *(f"{node.module}.{a.name}" for a in node.names)]
            for module in modules:
                assert not module.startswith(BANNED_MODULES), module
            assert all(a.name != "ModelGateway" for a in node.names)
        if isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            assert name not in {"ModelGateway", "execute", "executemany", "default_gateway"}
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert not SQL.search(node.value), node.value


@pytest.mark.db
def test_sort_amount_puts_non_usd_with_unknown(
    api: TestClient, seeded: dict[str, GrantCandidate]
) -> None:
    euro = built("Euro", 99, 30, 58, amount_max=Money(amount_minor=99_000_000, currency="EUR"))
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        store.upsert_candidate(tx, euro)
    body = api.get("/v1/grants", params={"sort": "amount"}).json()
    assert ids(body, {**seeded, "EUR": euro}) == ["A", "B", "E", "EUR", "C", "D"]
