from __future__ import annotations

import os
from collections.abc import Iterator

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
