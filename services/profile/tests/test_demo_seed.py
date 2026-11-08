"""AC11: the demo seed creates the profile once and skips with HOPE_DEMO_FRESH=1."""

from __future__ import annotations

from typing import Any

import pytest
from hope_core.settings import get_settings
from hope_profile import demo

pytestmark = pytest.mark.db


def test_seed_idempotent_and_fresh_flag(hope_api: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOPE_DEMO_FRESH", "1")
    assert demo.seed() is None
    monkeypatch.delenv("HOPE_DEMO_FRESH")
    created = demo.seed()
    assert created is not None and created.version == 1
    assert created.recorded_by == "demo@hope.org"
    assert created.profile.legal.legal_name == "Riverbend Community Health Alliance"
    assert created.profile.agency_id == get_settings().agency_id
    assert demo.seed() is None
    from hope_profile.api import get_profile_repository  # noqa: F401  (route uses the same repo)

    settings = get_settings()
    from hope_core.db import connect
    from hope_profile.api import get_pillar
    from hope_profile.repository import ProfileRepository

    with connect() as conn:
        latest = ProfileRepository(conn, get_pillar()).latest(
            settings.tenant_id, settings.agency_id
        )
    assert latest is not None and latest.version == 1
