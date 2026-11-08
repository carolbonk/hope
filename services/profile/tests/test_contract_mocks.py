from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.db

MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks" / "w2"
VOLATILE = {"updated_at"}


def mock(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / f"{name}.json").read_text())
    return data


def shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__ if value is not None else None


def assert_matches(response: Any, name: str, exact: bool = True) -> None:
    expected = mock(name)
    assert response.status_code == expected["status"], (name, response.text)
    for header, value in expected["headers"].items():
        if header == "content-type":
            assert response.headers[header].startswith(value)
        elif header == "etag":
            assert response.headers[header] == value
    body = response.json()
    want = expected["body"]
    if exact:
        assert {k: v for k, v in body.items() if k not in VOLATILE} == {
            k: v for k, v in want.items() if k not in VOLATILE
        }, name
    else:
        assert set(body) == set(want), name
        assert shape(body) == shape(want) or not want.get("items"), name


def test_responses_match_mocks(signed_in: Any) -> None:
    http = signed_in
    assert_matches(http.get("/v1/profile"), "profile.get/not_found")
    form = mock("profile.put/request")
    assert_matches(http.put("/v1/profile", json=form), "profile.put/created")
    assert_matches(http.put("/v1/profile", json=form), "profile.put/if_match_required")
    bad = {**form, "basics": {**form["basics"], "ein": "07-1234567"}}
    assert_matches(
        http.put("/v1/profile", json=bad, headers={"If-Match": '"1"'}),
        "profile.put/validation_error",
    )
    stale = http.put("/v1/profile", json=form, headers={"If-Match": '"9"'})
    assert stale.status_code == 409
    assert set(stale.json()) == set(mock("profile.put/version_conflict")["body"])
    patched = http.patch(
        "/v1/profile", json=mock("profile.patch/request"), headers={"If-Match": '"1"'}
    )
    assert patched.status_code == 200
    assert set(patched.json()) == set(mock("profile.patch/ok")["body"])
    got = http.get("/v1/profile")
    want = mock("profile.get/ok")["body"]
    assert {k: v for k, v in got.json().items() if k not in {"updated_at", "version"}} == {
        k: v for k, v in want.items() if k not in {"updated_at", "version"}
    }
    assert_matches(
        http.get("/v1/profile/ntee-codes", params={"q": "clinic"}), "ntee.search/ok", False
    )
    assert_matches(http.get("/v1/profile/ntee-codes", params={"q": "qqqq"}), "ntee.search/empty")
    suggested = http.post("/v1/profile/ntee-suggestions", json=mock("ntee.suggest/request"))
    assert suggested.status_code == 200
    assert shape(suggested.json()) == shape(mock("ntee.suggest/ok")["body"])
    assert [s["code"] for s in suggested.json()["suggestions"]] == ["E32", "F30"]
