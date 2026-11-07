import os
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from hope_core.migrate import apply_migrations
from hope_core.schemas.hitl import Gate
from hope_core.schemas.lifecycle import OpportunityState as S
from hope_core.testing.factories import TENANT_A
from hope_workflow.contracts import ApprovalRecord, ProjectionRow
from hope_workflow.postgres import PostgresApprovalStore, PostgresProjectionStore

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("HOPE_DATABASE_ADMIN_URL", "postgresql://hope:hope@localhost:5432/hope")
APP_URL = "postgresql://hope_app:hope_app@localhost:5432/hope"


@pytest.fixture(scope="module")
def seeded() -> Iterator[tuple[str, str]]:
    try:
        psycopg.connect(ADMIN_URL, connect_timeout=2).close()
    except psycopg.OperationalError:
        pytest.skip(
            "Postgres not reachable; run `docker compose -f infra/docker-compose.yml up -d`"
        )
    apply_migrations(ADMIN_URL)
    agency_id, opportunity_id = str(uuid4()), str(uuid4())
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO tenants (tenant_id, name) VALUES (%s, 'a') ON CONFLICT DO NOTHING",
            (TENANT_A,),
        )
        conn.execute(
            "INSERT INTO agencies (agency_id, tenant_id, legal_name) VALUES (%s, %s, 'x')",
            (agency_id, TENANT_A),
        )
        conn.execute(
            "INSERT INTO opportunities (opportunity_id, source_system, source_id, title)"
            " VALUES (%s, 'grants_gov', %s, 't')",
            (opportunity_id, opportunity_id),
        )
    yield agency_id, opportunity_id


def test_approval_records_are_idempotent_appends(seeded: tuple[str, str]) -> None:
    record = ApprovalRecord(
        approval_id=uuid4(),
        tenant_id=TENANT_A,
        workflow_id=f"wf-{uuid4()}",
        gate=Gate.BUDGET_SIGNOFF,
        decision="approve",
        artifact_hash="sha256:abc",
        decided_by="user:bob",
        decided_at=datetime.now(UTC),
    )
    store = PostgresApprovalStore(APP_URL)
    store.append(record)
    store.append(record)
    with psycopg.connect(ADMIN_URL) as conn:
        rows = conn.execute(
            "SELECT gate, decided_by FROM approvals WHERE workflow_id = %s", (record.workflow_id,)
        ).fetchall()
    assert rows == [("HITL-2", "user:bob")]


def test_projection_upsert_keeps_scores(seeded: tuple[str, str]) -> None:
    agency_id, opportunity_id = seeded
    store = PostgresProjectionStore(APP_URL)
    base = ProjectionRow(
        tenant_id=TENANT_A,
        opportunity_id=opportunity_id,
        agency_id=agency_id,
        state=S.RECOMMENDED,
        workflow_id="wf",
        composite_score=82.5,
        recommendation="pursue",
    )
    store.upsert(base)
    store.upsert(base.model_copy(update={"state": S.PLANNING, "composite_score": None}))
    with psycopg.connect(ADMIN_URL) as conn:
        row = conn.execute(
            "SELECT state, composite_score, recommendation FROM tenant_opportunity"
            " WHERE opportunity_id = %s",
            (opportunity_id,),
        ).fetchone()
    assert row is not None and row[0] == "Planning" and float(row[1]) == 82.5 and row[2] == "pursue"
