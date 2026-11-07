from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest
from hope_core.migrate import apply_migrations

ADMIN_URL = os.environ.get("HOPE_DATABASE_ADMIN_URL", "postgresql://hope:hope@localhost:5432/hope")


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[str]:
    try:
        psycopg.connect(ADMIN_URL, connect_timeout=2).close()
    except psycopg.OperationalError:
        pytest.skip(
            "Postgres not reachable; run `docker compose -f infra/docker-compose.yml up -d`"
        )
    apply_migrations(ADMIN_URL)
    yield ADMIN_URL
