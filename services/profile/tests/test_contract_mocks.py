"""AC13: every H1 route answers with the keys and value types of `contracts/mocks/w2/**`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.db
MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks" / "w2"


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
    for header, value in expected["headers"].items():
        if header == "etag":
            assert response.headers[header].strip('"').isdigit(), name
        else:
            assert response.headers[header] == value, name
    if "code" in expected["body"]:
        assert body["code"] == expected["body"]["code"], name


def test_responses_match_mocks(signed_in: Any) -> None:
    form = mock("profile.put/request")
    same(signed_in.get("/v1/profile"), "profile.get/not_found")
    same(signed_in.put("/v1/profile", json=form), "profile.put/created")
    same(signed_in.get("/v1/profile"), "profile.get/ok")
    same(signed_in.put("/v1/profile", json=form), "profile.put/if_match_required")
    same(
        signed_in.put("/v1/profile", json=form, headers={"If-Match": '"9"'}),
        "profile.put/version_conflict",
    )
    bad = json.loads(json.dumps(form))
    bad["basics"]["ein"] = "00-3917265"
    invalid = signed_in.put("/v1/profile", json=bad, headers={"If-Match": '"1"'})
    same(invalid, "profile.put/validation_error")
    assert invalid.json()["errors"] == mock("profile.put/validation_error")["body"]["errors"]
    changed = json.loads(json.dumps(form))
    changed["mission"]["values"] = ["Community-led", "Bilingual by default"]
    same(
        signed_in.put("/v1/profile", json=changed, headers={"If-Match": '"1"'}),
        "profile.put/ok",
    )
    same(
        signed_in.patch(
            "/v1/profile", json=mock("profile.patch/request"), headers={"If-Match": '"2"'}
        ),
        "profile.patch/ok",
    )
    same(
        signed_in.patch(
            "/v1/profile", json=mock("profile.patch/request"), headers={"If-Match": '"2"'}
        ),
        "profile.patch/version_conflict",
    )
    same(signed_in.get("/v1/profile/ntee-codes", params={"q": "clinic"}), "ntee.search/ok")
    same(signed_in.get("/v1/profile/ntee-codes", params={"q": "zzzqqq"}), "ntee.search/empty")
    suggest = mock("ntee.suggest/request")
    same(signed_in.post("/v1/profile/ntee-suggestions", json=suggest), "ntee.suggest/ok")
    for _ in range(9):
        signed_in.post("/v1/profile/ntee-suggestions", json=suggest)
    same(signed_in.post("/v1/profile/ntee-suggestions", json=suggest), "ntee.suggest/rate_limited")


def test_every_w2_mock_is_covered() -> None:
    found = {str(p.relative_to(MOCKS).with_suffix("")) for p in MOCKS.glob("*/*.json")}
    assert found == {
        "ntee.search/empty",
        "ntee.search/ok",
        "ntee.suggest/ok",
        "ntee.suggest/rate_limited",
        "ntee.suggest/request",
        "profile.get/not_found",
        "profile.get/ok",
        "profile.patch/ok",
        "profile.patch/request",
        "profile.patch/version_conflict",
        "profile.put/created",
        "profile.put/if_match_required",
        "profile.put/ok",
        "profile.put/request",
        "profile.put/validation_error",
        "profile.put/version_conflict",
    }
