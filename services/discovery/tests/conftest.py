from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from hope_core import store
from hope_core.migrate import apply_migrations
from hope_core.model_gateway import MockProvider, ModelGateway, RunBudget
from hope_core.settings import get_settings
from hope_discovery import mock
from hope_discovery.agent import DiscoveryAgent
from hope_discovery.demo import DEMO_REQUEST, demo_profile
from hope_discovery.mock import ScriptedWeb
from hope_discovery.settings import DiscoverySettings

ADMIN_URL = os.environ.get("HOPE_DATABASE_ADMIN_URL", "postgresql://hope:hope@localhost:5432/hope")
NOW = datetime(2026, 11, 8, 14, 0, tzinfo=UTC)

Override = dict[type, Callable[..., dict[str, Any]]]


def make_provider(overrides: Override | None = None) -> MockProvider:
    provider = mock.register(MockProvider())
    for model, responder in (overrides or {}).items():
        provider.register(model, responder)
    return provider


@pytest.fixture
def run_agent() -> Callable[..., tuple[mock.MemoryRepo, Any]]:
    """Run the agent on the demo profile and request; returns (repo, result or exception)."""

    def run(
        web: Any = None,
        overrides: Override | None = None,
        repo: mock.MemoryRepo | None = None,
        clock: Callable[[], float] | None = None,
        budget: RunBudget | None = None,
        **settings: Any,
    ) -> tuple[mock.MemoryRepo, Any]:
        repo = repo or mock.MemoryRepo(demo_profile(), *DEMO_REQUEST)
        agent = DiscoveryAgent(
            repo,
            ModelGateway([make_provider(overrides)]),
            web or ScriptedWeb(),
            DiscoverySettings(**({"fetch_concurrency": 1} | settings)),
            now=lambda: NOW,
            budget=budget,
            **({"clock": clock} if clock else {}),
        )
        try:
            return repo, agent.run(uuid4())
        except Exception as exc:
            return repo, exc

    return run


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


@pytest.fixture
def clean_db(migrated_db: str) -> Iterator[str]:
    """The configured tenant with no jobs, candidates or profile."""
    get_settings.cache_clear()
    s = get_settings()
    store.ensure_tenant(migrated_db, s.tenant_id, s.agency_id)

    def wipe() -> None:
        with psycopg.connect(migrated_db) as conn:
            for table in ("grant_candidates", "jobs"):
                conn.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (s.tenant_id,))
            conn.execute("DELETE FROM agency_profile_versions WHERE agency_id = %s", (s.agency_id,))

    wipe()
    yield migrated_db
    wipe()
