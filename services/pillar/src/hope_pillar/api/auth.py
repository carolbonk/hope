"""Sign-up (invite code only), login and logout with the `hope_session` cookie (H0 section 1)."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Response, status
from hope_core import store
from hope_core.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    ProblemException,
    hash_password,
    make_session_token,
    require_session_secret,
    verify_password,
)
from hope_core.db import connect, tenant_tx
from hope_core.schemas import UserView
from hope_core.settings import HopeSettings, get_settings
from pydantic import BaseModel, Field

from hope_pillar.accounts import EMAIL_PATTERN, MIN_PASSWORD, EmailTaken, create_user, weak_password

router = APIRouter(prefix="/v1/auth", tags=["auth"])

MIN_INVITE_CODE = 16


class SignupBody(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=EMAIL_PATTERN)
    password: str = Field(max_length=1024)
    display_name: str = Field(min_length=1, max_length=200)
    invite_code: str = Field(default="", max_length=200)


class LoginBody(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class UserOut(BaseModel):
    user: UserView


def _view(user: store.UserRecord) -> UserView:
    return UserView(user_id=user.user_id, email=user.email, display_name=user.display_name)


def _set_cookie(response: Response, user: store.UserRecord, settings: HopeSettings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        make_session_token(user.user_id, settings),
        max_age=SESSION_MAX_AGE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


def _invite_ok(given: str, settings: HopeSettings) -> bool:
    expected = settings.invite_code or ""
    if len(expected) < MIN_INVITE_CODE:
        return False
    return hmac.compare_digest(given.encode(), expected.encode())


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignupBody, response: Response) -> UserOut:
    settings = get_settings()
    require_session_secret(settings)
    if not _invite_ok(body.invite_code, settings):
        raise ProblemException(403, "signup_closed", "Sign-up is invite-only")
    if weak_password(body.password):
        raise ProblemException(
            422,
            "weak_password",
            "Password too short",
            [
                {
                    "field": "password",
                    "code": "weak_password",
                    "message": f"Use at least {MIN_PASSWORD} characters.",
                }
            ],
        )
    try:
        with connect() as conn, tenant_tx(conn, settings.tenant_id) as tx:
            user = create_user(tx, body.email, body.password, body.display_name)
    except EmailTaken as exc:
        raise ProblemException(409, "email_taken", "Email already registered") from exc
    _set_cookie(response, user, settings)
    return UserOut(user=_view(user))


_DUMMY_HASH = hash_password("not-a-real-password")


@router.post("/login")
def login(body: LoginBody, response: Response) -> UserOut:
    settings = get_settings()
    with connect() as conn, tenant_tx(conn, settings.tenant_id) as tx:
        user = store.get_user_by_email(tx, body.email)
    # Verify against a dummy hash for unknown emails so both failures cost the same.
    ok = verify_password(user.password_hash if user else _DUMMY_HASH, body.password)
    if user is None or not ok:
        raise ProblemException(401, "invalid_credentials", "Wrong email or password")
    _set_cookie(response, user, settings)
    return UserOut(user=_view(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=settings.cookie_secure
    )
