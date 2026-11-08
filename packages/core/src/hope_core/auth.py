"""Single-tenant session auth (H0 section 1): Argon2 passwords, signed `hope_session` cookie."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from hope_core import store
from hope_core.db import connect, tenant_tx
from hope_core.settings import HopeSettings, get_settings

COOKIE_NAME = "hope_session"
SESSION_MAX_AGE = 14 * 24 * 3600
_hasher = PasswordHasher()


@dataclass(frozen=True)
class Principal:
    tenant_id: UUID
    user_id: UUID
    email: str
    display_name: str


class ProblemException(HTTPException):
    """An `application/problem+json` error with a machine-readable `code`."""

    def __init__(
        self, status: int, code: str, title: str, errors: list[dict[str, str]] | None = None
    ) -> None:
        super().__init__(status_code=status, detail=title)
        self.code = code
        self.title = title
        self.errors = errors

    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": "about:blank",
            "title": self.title,
            "status": self.status_code,
            "code": self.code,
        }
        if self.errors is not None:
            body["errors"] = self.errors
        return body


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def _serializer(settings: HopeSettings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="hope-session")


def make_session_token(user_id: UUID, settings: HopeSettings | None = None) -> str:
    return _serializer(settings or get_settings()).dumps({"user_id": str(user_id)})


def read_session_token(token: str, settings: HopeSettings | None = None) -> UUID | None:
    try:
        data = _serializer(settings or get_settings()).loads(token, max_age=SESSION_MAX_AGE)
        return UUID(str(data["user_id"]))
    except (BadSignature, KeyError, TypeError, ValueError):
        return None


def not_signed_in() -> ProblemException:
    return ProblemException(401, "not_signed_in", "Sign in to continue")


def get_principal(request: Request) -> Principal:
    """FastAPI dependency: the signed-in user, or 401 `not_signed_in`."""
    settings = get_settings()
    token = request.cookies.get(COOKIE_NAME)
    user_id = read_session_token(token, settings) if token else None
    if user_id is None:
        raise not_signed_in()
    with connect() as conn, tenant_tx(conn, settings.tenant_id) as tx:
        user = store.get_user(tx, user_id)
    if user is None:
        raise not_signed_in()
    return Principal(settings.tenant_id, user.user_id, user.email, user.display_name)
