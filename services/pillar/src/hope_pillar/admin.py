"""`hope-create-user`: create an account (or reset its password) with direct DB access.

The password comes from a hidden prompt or `--password-stdin`, never from an argument,
and is never printed. Output is only the email and the user id."""

from __future__ import annotations

import argparse
import re
import sys
from getpass import getpass
from typing import NoReturn

from hope_core import store
from hope_core.db import connect, tenant_tx
from hope_core.settings import get_settings

from hope_pillar.accounts import (
    EMAIL_PATTERN,
    MIN_PASSWORD,
    EmailTaken,
    create_user,
    set_password,
    weak_password,
)

PROG = "hope-create-user"


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse echoes unknown arguments, which could be a password typed by mistake.
        if message.startswith("unrecognized arguments"):
            message = "unrecognized arguments (the password is never an argument; see --help)"
        super().error(message)


def _parser() -> argparse.ArgumentParser:
    # No abbreviations: `--password secret` must not be read as `--password-stdin`.
    parser = _Parser(
        prog=PROG, allow_abbrev=False, description="Create a Hope account in the tenant."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", help="display name (required for a new account)")
    parser.add_argument(
        "--password-stdin", action="store_true", help="read the password from stdin"
    )
    parser.add_argument(
        "--reset-password", action="store_true", help="set a new password for an existing account"
    )
    return parser


def _fail(message: str) -> None:
    sys.exit(f"{PROG}: {message}")


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    password = getpass("Password: ")
    if getpass("Repeat password: ") != password:
        _fail("the passwords don't match")
    return password


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    email = args.email.strip().lower()
    if len(email) > 320 or not re.fullmatch(EMAIL_PATTERN, email):
        _fail(f"not an email address: {email!r}")
    name = (args.name or "").strip()
    if not args.reset_password and not name:
        _fail("--name is required for a new account")
    if len(name) > 200:
        _fail("--name is longer than 200 characters")
    password = _read_password(args.password_stdin)
    if weak_password(password):
        _fail(f"use a password of at least {MIN_PASSWORD} characters")
    if len(password) > 1024:
        _fail("the password is longer than 1024 characters")

    settings = get_settings()
    store.ensure_tenant(settings.database_system_url, settings.tenant_id, settings.agency_id)
    try:
        with connect() as conn, tenant_tx(conn, settings.tenant_id) as tx:
            user = store.get_user_by_email(tx, email)
            if args.reset_password:
                if user is None:
                    _fail(f"no account for {email}; drop --reset-password to create it")
                    return
                set_password(tx, user.user_id, password)
            else:
                if user is not None:
                    _fail(f"{email} already has an account; use --reset-password to change it")
                user = create_user(tx, email, password, name)
    except EmailTaken:
        _fail(f"{email} already has an account; use --reset-password to change it")
        return
    print(f"{user.email} {user.user_id}")
