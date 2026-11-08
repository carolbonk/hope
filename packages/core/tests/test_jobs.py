from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import psycopg
import pytest
from hope_core import jobs, store
from hope_core.db import connect, tenant_tx
from hope_core.schemas import DiscoveryProgress
from hope_core.settings import get_settings

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def inline(migrated_db: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[UUID]:
    monkeypatch.setenv("HOPE_JOBS_INLINE", "1")
    get_settings.cache_clear()
    tenant = get_settings().tenant_id
    store.ensure_tenant(migrated_db, tenant)
    with psycopg.connect(migrated_db) as admin:
        admin.execute("DELETE FROM grant_candidates WHERE tenant_id = %s", (tenant,))
        admin.execute("DELETE FROM jobs WHERE tenant_id = %s", (tenant,))
    yield tenant
    get_settings.cache_clear()


def job(job_id: UUID) -> store.JobRecord:
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        found = store.get_job(tx, job_id)
    assert found is not None
    return found


def count_jobs() -> int:
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        tx.execute("SELECT count(*) AS n FROM jobs")
        row = tx.fetchone()
    assert row is not None
    return int(row["n"])


def work(n: int) -> dict[str, Any]:
    jobs.report(DiscoveryProgress(queries_total=n, queries_done=n, current_step="Done"))
    return {"counts": {"new": n}}


def test_runs_inline_reports_progress_and_stores_result() -> None:
    job_id = jobs.start_job("discovery", work, 3)
    done = job(job_id)
    assert done.status == "done" and done.finished_at is not None
    assert done.progress["queries_done"] == 3
    assert done.result == {"counts": {"new": 3}}


def test_adopts_existing_job_id() -> None:
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        created = store.create_job(tx, "discovery")
    assert jobs.start_job("discovery", work, 1, job_id=created.job_id) == created.job_id
    assert count_jobs() == 1
    assert job(created.job_id).status == "done"
    with pytest.raises(ValueError):
        jobs.start_job("discovery", work, 1, job_id=created.job_id)  # no longer queued


def test_exception_marks_failed() -> None:
    def boom() -> None:
        raise RuntimeError("search quota exceeded\nTraceback line that must not leak")

    failed = job(jobs.start_job("discovery", boom))
    assert failed.status == "failed"
    assert failed.error == "search quota exceeded"


def test_fn_that_finishes_itself_is_not_overwritten() -> None:
    def self_finishing() -> None:
        with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
            tx.execute("SELECT job_id FROM jobs WHERE status = 'running'")
            row = tx.fetchone()
            assert row is not None
            store.finish_job(tx, row["job_id"], result={"own": True})

    assert job(jobs.start_job("discovery", self_finishing)).result == {"own": True}


def test_interrupted_jobs_fail_on_startup() -> None:
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        running = store.create_job(tx, "discovery")
        store.update_job_progress(tx, running.job_id, {"current_step": "Reading"})
        queued = store.create_job(tx, "discovery")
    assert jobs.fail_interrupted_jobs() == 1
    assert job(running.job_id).status == "failed"
    assert job(running.job_id).error == "Interrupted by restart"
    assert job(queued.job_id).status == "queued"
