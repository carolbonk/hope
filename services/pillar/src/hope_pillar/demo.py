"""`hope-demo-seed`: the demo tenant, agency and user, then each service's idempotent seed."""

from __future__ import annotations

import importlib

from hope_core import store
from hope_core.auth import hash_password
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
        if store.get_user_by_email(tx, DEMO_EMAIL) is not None:
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


def main() -> None:
    settings = get_settings()
    store.ensure_tenant(
        settings.database_system_url, settings.tenant_id, settings.agency_id, DEMO_AGENCY
    )
    created = seed_user()
    ran = run_service_seeds()
    state = "created" if created else "already present"
    print(f"demo user {DEMO_EMAIL} {state}; seeds: {', '.join(ran) or 'none'}")
