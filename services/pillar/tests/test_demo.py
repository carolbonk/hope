from __future__ import annotations

from pathlib import Path

import pytest
from hope_core import store
from hope_core.auth import hash_password, verify_password
from hope_core.db import connect, tenant_tx
from hope_core.settings import get_settings
from hope_pillar.demo import (
    DEMO_EMAIL,
    DEMO_PASSWORD,
    ensure_env,
    ensure_invite_code,
    run_service_seeds,
    seed_user,
)


def test_invite_code_is_written_once(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("HOPE_INVITE_CODE=\nOTHER=1")
    code = ensure_invite_code(env)
    assert code and len(code) >= 16
    assert env.read_text() == f"OTHER=1\nHOPE_INVITE_CODE={code}\n"
    assert ensure_invite_code(env) is None


def test_session_secret_is_kept_once_written(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    assert ensure_env("HOPE_SESSION_SECRET", "first-secret-0123456789", env)
    assert ensure_env("HOPE_SESSION_SECRET", "second-secret-012345678", env) is None
    assert env.read_text() == "HOPE_SESSION_SECRET=first-secret-0123456789\n"


def test_service_seeds_skip_missing_modules() -> None:
    assert "hope_discovery.demo" in run_service_seeds()


@pytest.mark.db
def test_seed_user_restores_the_demo_password(migrated_db: str) -> None:
    settings = get_settings()
    store.ensure_tenant(migrated_db, settings.tenant_id, settings.agency_id)
    seed_user()
    with connect() as conn, tenant_tx(conn, settings.tenant_id) as tx:
        user = store.get_user_by_email(tx, DEMO_EMAIL)
        assert user is not None
        store.set_password_hash(tx, user.user_id, hash_password("some-other-password"))
    assert seed_user() is False
    with connect() as conn, tenant_tx(conn, settings.tenant_id) as tx:
        user = store.get_user_by_email(tx, DEMO_EMAIL)
    assert user is not None and verify_password(user.password_hash, DEMO_PASSWORD)
