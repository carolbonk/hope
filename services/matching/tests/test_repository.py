from uuid import uuid4

import psycopg
import pytest
from hope_core.db import connect
from hope_core.testing.factories import TENANT_A, TENANT_B
from hope_matching.config import MatchingConfig, Thresholds
from hope_matching.recommender import build_matrix
from hope_matching.repository import latest_matrix, load_config, save_config, save_matrix
from hope_matching.testing import NOW, profile

pytestmark = pytest.mark.db

APP_URL = "postgresql://hope_app:hope_app@localhost:5432/hope"


def test_config_and_matrix_round_trip_with_rls(migrated_db: str) -> None:
    p = profile(agency_id=uuid4())
    with psycopg.connect(migrated_db, autocommit=True) as conn:
        for tenant in (TENANT_A, TENANT_B):
            conn.execute(
                "INSERT INTO tenants (tenant_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (tenant, f"tenant-{tenant}"),
            )
        conn.execute(
            "INSERT INTO agencies (agency_id, tenant_id, legal_name) VALUES (%s, %s, 'x')",
            (p.agency_id, TENANT_A),
        )
    config = MatchingConfig(thresholds=Thresholds(pursue=80), strategic_keywords=["stem"])
    matrix = build_matrix(p, [], config, generated_at=NOW)
    with connect(APP_URL) as conn:
        save_config(conn, TENANT_A, config)
        assert load_config(conn, TENANT_A) == config
        assert load_config(conn, TENANT_B) == MatchingConfig()
        assert save_matrix(conn, TENANT_A, matrix).startswith("sha256:")
        assert latest_matrix(conn, TENANT_A, p.agency_id) == matrix
        assert latest_matrix(conn, TENANT_B, p.agency_id) is None
        with pytest.raises(psycopg.errors.RaiseException), conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_A),))
            conn.execute("DELETE FROM opportunity_matrices")
