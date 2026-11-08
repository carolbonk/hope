from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from hope_core.settings import get_settings

INVITE = "test-invite-code-0123456789"  # set by the hope_api fixture

pytestmark = pytest.mark.db


def signup(client: TestClient, **overrides: Any) -> Any:
    body = {
        "email": "dana@riverbend.example.org",
        "password": "correct-horse-battery",
        "display_name": "Dana Okafor",
        "invite_code": INVITE,
    }
    body.update(overrides)
    return client.post("/v1/auth/signup", json=body)


def problem(response: Any, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code and body["status"] == status
    assert set(body) >= {"type", "title", "status", "code"}


def test_signup_login_me_logout(hope_api: TestClient) -> None:
    created = signup(hope_api)
    assert created.status_code == 201
    user = created.json()["user"]
    assert set(user) == {"user_id", "email", "display_name"}
    assert hope_api.get("/v1/me").json()["email"] == "dana@riverbend.example.org"

    out = hope_api.post("/v1/auth/logout")
    assert out.status_code == 204 and out.content == b""
    assert "hope_session" not in hope_api.cookies
    problem(hope_api.get("/v1/me"), 401, "not_signed_in")

    login = hope_api.post(
        "/v1/auth/login",
        json={"email": "DANA@riverbend.example.org", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200 and login.json()["user"] == user
    assert hope_api.get("/v1/me").status_code == 200


def test_invalid_credentials_are_indistinguishable(hope_api: TestClient) -> None:
    signup(hope_api)
    hope_api.cookies.clear()
    wrong_pw = hope_api.post(
        "/v1/auth/login", json={"email": "dana@riverbend.example.org", "password": "nope-nope-nope"}
    )
    wrong_email = hope_api.post(
        "/v1/auth/login", json={"email": "who@else.org", "password": "correct-horse-battery"}
    )
    problem(wrong_pw, 401, "invalid_credentials")
    problem(wrong_email, 401, "invalid_credentials")
    assert wrong_pw.json() == wrong_email.json()
    assert "set-cookie" not in wrong_pw.headers


def test_not_signed_in(hope_api: TestClient) -> None:
    problem(hope_api.get("/v1/me"), 401, "not_signed_in")
    hope_api.cookies.set("hope_session", "forged.token.value")
    problem(hope_api.get("/v1/me"), 401, "not_signed_in")


@pytest.mark.parametrize("code", ["", "wrong-code-0123456789", INVITE + "x"])
def test_signup_closed_with_configured_code(hope_api: TestClient, code: str) -> None:
    problem(signup(hope_api, invite_code=code), 403, "signup_closed")
    problem(signup(hope_api, invite_code=code, password="short"), 403, "signup_closed")


@pytest.mark.parametrize("configured", [None, "", "too-short"])
def test_signup_closed_without_configured_code(
    hope_api: TestClient, monkeypatch: pytest.MonkeyPatch, configured: str | None
) -> None:
    if configured is None:
        monkeypatch.delenv("HOPE_INVITE_CODE")
    else:
        monkeypatch.setenv("HOPE_INVITE_CODE", configured)
    get_settings.cache_clear()
    problem(signup(hope_api, invite_code=configured or ""), 403, "signup_closed")


def test_weak_password(hope_api: TestClient) -> None:
    response = signup(hope_api, password="1234567")
    problem(response, 422, "weak_password")
    assert response.json()["errors"] == [
        {"field": "password", "code": "weak_password", "message": "Use at least 8 characters."}
    ]


def test_email_taken(hope_api: TestClient) -> None:
    assert signup(hope_api).status_code == 201
    problem(signup(hope_api, email="Dana@Riverbend.example.org"), 409, "email_taken")


def test_validation_errors_are_problems(hope_api: TestClient) -> None:
    response = signup(hope_api, email="not-an-email")
    problem(response, 422, "validation_failed")
    assert response.json()["errors"][0]["field"] == "email"


def test_cookie_flags(hope_api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    cookie = signup(hope_api).headers["set-cookie"]
    assert cookie.startswith("hope_session=")
    for flag in ("HttpOnly", "SameSite=lax", "Secure", "Path=/", "Max-Age=1209600"):
        assert flag.lower() in cookie.lower()

    monkeypatch.setenv("HOPE_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    insecure = hope_api.post(
        "/v1/auth/login",
        json={"email": "dana@riverbend.example.org", "password": "correct-horse-battery"},
    ).headers["set-cookie"]
    assert "secure" not in insecure.lower() and "httponly" in insecure.lower()


def test_cors_allows_only_web_origin(hope_api: TestClient) -> None:
    allowed = hope_api.options(
        "/v1/me",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    denied = hope_api.options(
        "/v1/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in denied.headers


def test_cors_exposes_etag_to_the_web_origin(hope_api: TestClient) -> None:
    response = hope_api.get("/v1/me", headers={"Origin": "http://localhost:3000"})
    exposed = response.headers.get("access-control-expose-headers", "").lower()
    assert "etag" in exposed


def test_missing_session_secret_is_a_clear_503(
    hope_api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOPE_SESSION_SECRET", "")  # empty overrides a local .env
    get_settings.cache_clear()
    response = signup(hope_api)
    problem(response, 503, "server_misconfigured")
    assert "HOPE_SESSION_SECRET" in response.json()["title"]

    monkeypatch.setenv("HOPE_SESSION_SECRET", "test-session-secret-0123456789")
    get_settings.cache_clear()
    assert signup(hope_api).status_code == 201, "the failed attempt created no account"


def test_open_login_creates_new_emails_only(
    hope_api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    login = {"email": "New@Example.org", "password": "x"}
    problem(hope_api.post("/v1/auth/login", json=login), 401, "invalid_credentials")

    monkeypatch.setenv("HOPE_OPEN_LOGIN", "true")
    get_settings.cache_clear()
    first = hope_api.post("/v1/auth/login", json=login)
    assert first.status_code == 200, first.text
    assert first.json()["user"]["email"] == "new@example.org"
    assert hope_api.get("/v1/me").json()["email"] == "new@example.org"

    hope_api.cookies.clear()
    again = hope_api.post("/v1/auth/login", json={"email": "new@example.org", "password": "x"})
    assert again.json()["user"] == first.json()["user"]
    hope_api.cookies.clear()
    wrong = {"email": "new@example.org", "password": "other"}
    problem(hope_api.post("/v1/auth/login", json=wrong), 401, "invalid_credentials")
    bad = {"email": "not-an-email", "password": "x"}
    problem(hope_api.post("/v1/auth/login", json=bad), 401, "invalid_credentials")
