"""`hope-demo-seed`: the demo tenant, agency and user, then each service's idempotent seed."""

from __future__ import annotations

import importlib
import re
import secrets
from pathlib import Path

from hope_core import store
from hope_core.auth import hash_password, verify_password
from hope_core.db import connect, tenant_tx
from hope_core.settings import get_settings

DEMO_EMAIL = "demo@hope.org"
DEMO_PASSWORD = "hope-demo"
DEMO_NAME = "Dana Okafor"
DEMO_AGENCY = "Riverbend Community Health Alliance"
# Run in this order; a module that doesn't exist yet (before H1/H2 land) is skipped.
SEED_MODULES = ("hope_profile.demo", "hope_discovery.demo")


def seed_user() -> bool:
    settings = get_settings()
    with connect() as conn, tenant_tx(conn, settings.tenant_id) as tx:
        user = store.get_user_by_email(tx, DEMO_EMAIL)
        if user is not None:
            if not verify_password(user.password_hash, DEMO_PASSWORD):
                store.set_password_hash(tx, user.user_id, hash_password(DEMO_PASSWORD))
            return False
        store.create_user(tx, DEMO_EMAIL, hash_password(DEMO_PASSWORD), DEMO_NAME)
    return True


def run_service_seeds() -> list[str]:
    ran = []
    for name in SEED_MODULES:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name != name:
                raise
            continue
        module.seed()
        ran.append(name)
    return ran


def ensure_env(name: str, value: str, env_file: Path = Path(".env")) -> str | None:
    """Write `name=value` to `.env` when it has no value for `name`; returns what was written."""
    text = env_file.read_text() if env_file.exists() else ""
    if re.search(rf"^{name}=\S", text, re.MULTILINE):
        return None
    text = re.sub(rf"^{name}=.*\n?", "", text, flags=re.MULTILINE)
    if text and not text.endswith("\n"):
        text += "\n"
    env_file.write_text(f"{text}{name}={value}\n")
    return value


def ensure_invite_code(env_file: Path = Path(".env")) -> str | None:
    return ensure_env("HOPE_INVITE_CODE", secrets.token_urlsafe(16), env_file)


def main() -> None:
    ensure_env("HOPE_SESSION_SECRET", secrets.token_urlsafe(32))
    code = ensure_invite_code()
    if code:
        print(f"wrote HOPE_INVITE_CODE to .env; share it to let others sign up: {code}")
    get_settings.cache_clear()
    settings = get_settings()
    store.ensure_tenant(
        settings.database_system_url, settings.tenant_id, settings.agency_id, DEMO_AGENCY
    )
    created = seed_user()
    ran = run_service_seeds()
    state = "created" if created else "already present"
    print(f"demo user {DEMO_EMAIL} {state}; seeds: {', '.join(ran) or 'none'}")
