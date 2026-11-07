import psycopg
import pytest
from hope_budget.engine import BudgetEngine
from hope_budget.store import LedgerIntegrityError, load_ledger, save_ledger
from hope_budget.testing import line, sample_context, sample_lines
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


def test_ledger_round_trip_and_immutability(migrated_db: str) -> None:
    _seed(migrated_db)
    trips = str(len(migrated_db) + id(object()) % 997)  # unique ledger per run
    ledger = BudgetEngine(sample_context()).compute(
        [*sample_lines(), line("x", "travel", "erp:travel:mileage-trip", trips)]
    )
    with connect(APP_URL) as conn:
        with tenant_tx(conn, TENANT_A) as cur:
            save_ledger(cur, TENANT_A, ledger)
            save_ledger(cur, TENANT_A, ledger)  # idempotent
        with tenant_tx(conn, TENANT_A) as cur:
            assert load_ledger(cur, ledger.ledger_id) == ledger
        with tenant_tx(conn, TENANT_B) as cur:
            assert load_ledger(cur, ledger.ledger_id) is None
        with pytest.raises(psycopg.errors.RaiseException), tenant_tx(conn, TENANT_A) as cur:
            cur.execute(
                "UPDATE budget_ledgers SET engine_version = 'x' WHERE ledger_id = %s",
                (ledger.ledger_id,),
            )


def test_refuses_unsealed_ledger(migrated_db: str) -> None:
    ledger = BudgetEngine(sample_context()).compute(sample_lines())
    forged = ledger.model_copy(
        update={"totals": ledger.totals.model_copy(update={"request_minor": 1})}
    )
    with (
        connect(APP_URL) as conn,
        tenant_tx(conn, TENANT_A) as cur,
        pytest.raises(LedgerIntegrityError),
    ):
        save_ledger(cur, TENANT_A, forged)
