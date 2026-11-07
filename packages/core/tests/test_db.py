from uuid import uuid4

import psycopg
import pytest
from hope_core.db import connect, tenant_tx
from hope_core.testing.factories import TENANT_A, TENANT_B

pytestmark = pytest.mark.db

APP_URL = "postgresql://hope_app:hope_app@localhost:5432/hope"


def _seed(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as conn:
        for tenant in (TENANT_A, TENANT_B):
            conn.execute(
                "INSERT INTO tenants (tenant_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (tenant, f"tenant-{tenant}"),
            )


def test_rls_isolates_tenants(migrated_db: str) -> None:
    _seed(migrated_db)
    name = f"agency-{uuid4()}"
    with connect(APP_URL) as conn:
        with tenant_tx(conn, TENANT_A) as cur:
            cur.execute(
                "INSERT INTO agencies (tenant_id, legal_name) VALUES (%s, %s)", (TENANT_A, name)
            )
        with tenant_tx(conn, TENANT_B) as cur:
            cur.execute("SELECT count(*) AS n FROM agencies WHERE legal_name = %s", (name,))
            assert cur.fetchone() == {"n": 0}
        with tenant_tx(conn, TENANT_A) as cur:
            cur.execute("SELECT count(*) AS n FROM agencies WHERE legal_name = %s", (name,))
            assert cur.fetchone() == {"n": 1}
        with pytest.raises(psycopg.errors.InsufficientPrivilege), tenant_tx(conn, TENANT_B) as cur:
            cur.execute(
                "INSERT INTO agencies (tenant_id, legal_name) VALUES (%s, %s)", (TENANT_A, name)
            )


def test_no_tenant_means_no_rows(migrated_db: str) -> None:
    _seed(migrated_db)
    with connect(APP_URL) as conn:
        assert conn.execute("SELECT count(*) AS n FROM tenants").fetchone() == {"n": 0}


def test_approvals_and_audit_are_append_only_and_chained(migrated_db: str) -> None:
    _seed(migrated_db)
    with connect(APP_URL) as conn:
        with tenant_tx(conn, TENANT_A) as cur:
            for action in ("approve", "approve"):
                cur.execute(
                    "INSERT INTO audit_log (tenant_id, actor, action, subject)"
                    " VALUES (%s, 'u1', %s, 'wf')",
                    (TENANT_A, action),
                )
            cur.execute(
                "SELECT prev_hash, hash FROM audit_log WHERE tenant_id = %s"
                " ORDER BY audit_id DESC LIMIT 2",
                (TENANT_A,),
            )
            latest, previous = cur.fetchall()
            assert latest["prev_hash"] == previous["hash"]
        with pytest.raises(psycopg.errors.RaiseException), tenant_tx(conn, TENANT_A) as cur:
            cur.execute("DELETE FROM audit_log WHERE tenant_id = %s", (TENANT_A,))


def test_ledger_check_rejects_non_engine_producer(migrated_db: str) -> None:
    _seed(migrated_db)
    with (
        connect(APP_URL) as conn,
        pytest.raises(psycopg.errors.CheckViolation),
        tenant_tx(conn, TENANT_A) as cur,
    ):
        cur.execute(
            "INSERT INTO budget_ledgers"
            " (ledger_id, tenant_id, engine_version, ledger, content_hash)"
            " VALUES (%s, %s, 'v', '{\"computed_by\": \"llm\"}', 'h')",
            (str(uuid4()), TENANT_A),
        )
