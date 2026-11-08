"""Accounts in the single tenant, shared by sign-up, the demo seed and `hope-create-user`."""

from __future__ import annotations

from uuid import UUID

import psycopg
from hope_core import store
from hope_core.auth import hash_password
from hope_core.store import Tx

MIN_PASSWORD = 8
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+$"


class EmailTaken(Exception):
    """An account with this email already exists."""


def weak_password(password: str) -> bool:
    return len(password) < MIN_PASSWORD


def create_user(tx: Tx, email: str, password: str, display_name: str) -> store.UserRecord:
    """Hash the password and insert the user; raises `EmailTaken` for a duplicate email."""
    try:
        return store.create_user(tx, email, hash_password(password), display_name.strip())
    except psycopg.errors.UniqueViolation as exc:
        raise EmailTaken(email) from exc


def set_password(tx: Tx, user_id: UUID, password: str) -> None:
    store.set_password_hash(tx, user_id, hash_password(password))
