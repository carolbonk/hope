from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from hope_core.migrate import apply_migrations
from hope_core.settings import get_settings
from hope_core.testing.factories import TENANT_A, TENANT_B
from hope_core.topics import Topic
from hope_pillar.dlq import InMemoryDeadLetterSink
from hope_pillar.kafka import KafkaConfig
from hope_pillar.outbox import OutboxRelay
from hope_pillar.pillar import KafkaPostgresPillar

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
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        for tenant in (TENANT_A, TENANT_B):
            conn.execute(
                "INSERT INTO tenants (tenant_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (tenant, f"tenant-{tenant}"),
            )
    yield ADMIN_URL


@pytest.fixture(scope="session")
def kafka_bootstrap() -> str:
    from confluent_kafka.admin import AdminClient

    bootstrap = get_settings().kafka_bootstrap
    try:
        AdminClient({"bootstrap.servers": bootstrap}).list_topics(timeout=3)
    except Exception:
        pytest.skip(
            "Kafka/Redpanda not reachable; run `docker compose -f infra/docker-compose.yml up -d`"
        )
    return bootstrap


@pytest.fixture
def kafka_pillar(
    migrated_db: str, kafka_bootstrap: str
) -> Iterator[tuple[KafkaPostgresPillar, InMemoryDeadLetterSink]]:
    """A pillar on isolated topics with a background relay that only sees this test's rows."""
    kafka = KafkaConfig(kafka_bootstrap, topic_prefix=f"test-{uuid4().hex[:8]}.")
    kafka.ensure_topics([*Topic, *(t.dlq for t in Topic)])
    settings = get_settings()
    with psycopg.connect(migrated_db) as conn:
        row = conn.execute("SELECT coalesce(max(outbox_id), 0) FROM outbox").fetchone()
    relay = OutboxRelay(kafka, settings.database_system_url, min_outbox_id=row[0] if row else 0)
    stop = threading.Event()
    thread = threading.Thread(target=relay.run_forever, args=(stop, 0.05), daemon=True)
    thread.start()
    sink = InMemoryDeadLetterSink()
    pillar = KafkaPostgresPillar(kafka=kafka, dead_letters=sink, idle_timeout=3.0, poll_timeout=0.2)
    yield pillar, sink
    stop.set()
    thread.join(5)
