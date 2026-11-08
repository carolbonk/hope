from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from hope_core import store
from hope_core.settings import get_settings
from hope_discovery import demo, repo

pytestmark = pytest.mark.db


def test_seed_offline_idempotent(clean_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOPE_OPENAI_API_KEY", "sk-not-used")
    get_settings.cache_clear()
    job_id = demo.seed()
    assert job_id is not None
    assert demo.seed() is None

    job = repo.with_tx(lambda tx: store.get_job(tx, job_id))
    assert job is not None and job.status == "done"
    assert job.started_at < datetime.now(UTC) - timedelta(days=1, hours=23)
    run = repo.with_tx(lambda tx: repo.get_run(tx, job_id))
    assert run is not None and len(run["queries"]) == 6
    assert run["counts"]["pages_read"] == 7 and run["counts"]["skipped_expired"] == 1
    assert run["counts"]["skipped_not_grant"] == 2 and run["counts"]["failed_pages"] == 1

    pairs = repo.with_tx(lambda tx: repo.job_candidates(tx, job_id))
    got = {c.title: c for c, _ in pairs}
    oral = got["Rural Oral Health Access Grant 2027"]
    assert (oral.funder, oral.fit_score, oral.deadline) == (
        "Cascade Health Foundation",
        88,
        date(2027, 3, 3),
    )
    assert oral.amount_max is not None and oral.amount_max.amount_minor == 7_500_000
    chw = got["Community Health Worker Training Grants"]
    assert chw.fit_score == 71 and chw.deadline is not None
    assert chw.amount_max is not None and chw.amount_max.amount_minor == 4_000_000
    mobile = got["Mobile Health Equipment Fund"]
    assert mobile.fit_score == 54 and mobile.deadline is None and mobile.deadline_text == "Rolling"
    assert all(c.discovered_at < datetime.now(UTC) - timedelta(days=1) for c in got.values())
    get_settings.cache_clear()
