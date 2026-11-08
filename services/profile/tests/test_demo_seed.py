from __future__ import annotations

from typing import Any

import psycopg
import pytest
from hope_core.settings import get_settings
from hope_profile import demo

pytestmark = pytest.mark.db


def versions(url: str) -> int:
    with psycopg.connect(url) as conn:
        row = conn.execute(
            "SELECT count(*) FROM agency_profile_versions WHERE agency_id = %s",
            (get_settings().agency_id,),
        ).fetchone()
    return int(row[0]) if row else 0


def test_seed_idempotent_and_fresh_flag(
    hope_api: Any, migrated_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOPE_DEMO_FRESH", "1")
    assert demo.seed() is False and versions(migrated_db) == 0
    monkeypatch.delenv("HOPE_DEMO_FRESH")
    assert demo.seed() is True and versions(migrated_db) == 1
    assert demo.seed() is False and versions(migrated_db) == 1
