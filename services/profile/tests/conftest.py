from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from hope_core.db import connect
from hope_core.migrate import apply_migrations
from hope_core.pillar import InMemoryPillar
from hope_core.testing.factories import TENANT_A, TENANT_B
from hope_profile.repository import Conn, ProfileRepository

ADMIN_URL = os.environ.get("HOPE_DATABASE_ADMIN_URL", "postgresql://hope:hope@localhost:5432/hope")
APP_URL = os.environ.get("HOPE_DATABASE_URL", "postgresql://hope_app:hope_app@localhost:5432/hope")


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[str]:
    try:
        psycopg.connect(ADMIN_URL, connect_timeout=2).close()
    except psycopg.OperationalError:
        pytest.skip(
            "Postgres not reachable; run `docker compose -f infra/docker-compose.yml up -d`"
        )
    apply_migrations(ADMIN_URL)
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        for tenant in (TENANT_A, TENANT_B):
            conn.execute(
                "INSERT INTO tenants (tenant_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (tenant, f"tenant-{tenant}"),
            )
    yield ADMIN_URL


@pytest.fixture
def conn(migrated_db: str) -> Iterator[Conn]:
    with connect(APP_URL) as connection:
        yield connection


@pytest.fixture
def pillar() -> InMemoryPillar:
    return InMemoryPillar()


@pytest.fixture
def repo(conn: Conn, pillar: InMemoryPillar) -> ProfileRepository:
    return ProfileRepository(conn, pillar)


INVITE = "test-invite-code-0123456789"
SIGNUP = {
    "email": "dana@riverbend.example.org",
    "password": "correct-horse-battery",
    "display_name": "Dana Okafor",
    "invite_code": INVITE,
}


@pytest.fixture
def hope_api(migrated_db: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """The hackathon API (H0 app) with an empty profile and users table, not signed in."""
    from fastapi.testclient import TestClient
    from hope_core import store
    from hope_core.settings import get_settings
    from hope_pillar.api import create_app
    from hope_profile import api as profile_api
    from hope_profile.ntee import RateLimiter

    monkeypatch.setenv("HOPE_INVITE_CODE", INVITE)
    monkeypatch.setenv("HOPE_SESSION_SECRET", "test-session-secret-0123456789")
    monkeypatch.delenv("HOPE_OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    store.ensure_tenant(migrated_db, settings.tenant_id, settings.agency_id)
    with psycopg.connect(migrated_db) as admin:
        for table in ("grant_candidates", "jobs", "users"):
            admin.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (settings.tenant_id,))
        admin.execute(
            "DELETE FROM agency_profile_versions WHERE agency_id = %s", (settings.agency_id,)
        )
        admin.execute(
            "DELETE FROM profile_change_proposals WHERE agency_id = %s", (settings.agency_id,)
        )
    app = create_app()
    limiter = RateLimiter()
    app.dependency_overrides[profile_api.get_rate_limiter] = lambda: limiter
    with TestClient(app, base_url="https://testserver") as client:
        yield client
    get_settings.cache_clear()


@pytest.fixture
def signed_in(hope_api: Any) -> Any:
    response = hope_api.post("/v1/auth/signup", json=SIGNUP)
    assert response.status_code == 201, response.text
    return hope_api
