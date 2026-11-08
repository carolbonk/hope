"""Every W1 response has the keys and value types of `contracts/mocks/w1/**`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

INVITE = "test-invite-code-0123456789"  # set by the hope_api fixture

pytestmark = pytest.mark.db
MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks" / "w1"


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
    body = response.json() if response.content else None
    assert shape(body) == shape(expected["body"]), name
    if expected["body"] and "code" in expected["body"]:
        assert body["code"] == expected["body"]["code"]
        assert response.headers["content-type"] == expected["headers"]["content-type"]


def test_w1_shapes(hope_api: TestClient) -> None:
    signup = mock("auth.signup/request") | {"invite_code": INVITE}
    login = mock("auth.login/request") | {"email": signup["email"], "password": signup["password"]}

    same(hope_api.get("/v1/me"), "me.get/signed_out")
    same(
        hope_api.post("/v1/auth/signup", json=signup | {"invite_code": "nope"}),
        "auth.signup/signup_closed",
    )
    same(
        hope_api.post("/v1/auth/signup", json=signup | {"password": "short"}),
        "auth.signup/weak_password",
    )
    same(hope_api.post("/v1/auth/signup", json=signup), "auth.signup/created")
    same(hope_api.post("/v1/auth/signup", json=signup), "auth.signup/email_taken")
    same(hope_api.get("/v1/me"), "me.get/not_onboarded")
    same(hope_api.post("/v1/auth/logout"), "auth.logout/ok")
    same(
        hope_api.post("/v1/auth/login", json=login | {"password": "wrong-password"}),
        "auth.login/invalid_credentials",
    )
    same(hope_api.post("/v1/auth/login", json=login), "auth.login/ok")


def test_every_w1_mock_is_covered() -> None:
    covered = {
        "auth.signup/request",
        "auth.signup/created",
        "auth.signup/signup_closed",
        "auth.signup/weak_password",
        "auth.signup/email_taken",
        "auth.login/request",
        "auth.login/ok",
        "auth.login/invalid_credentials",
        "auth.logout/ok",
        "me.get/signed_out",
        "me.get/not_onboarded",
        "me.get/onboarded",
    }
    found = {str(p.relative_to(MOCKS).with_suffix("")) for p in MOCKS.glob("*/*.json")}
    assert found == covered
