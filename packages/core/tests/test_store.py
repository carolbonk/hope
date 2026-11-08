from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from hope_core import store
from hope_core.db import connect, tenant_tx
from hope_core.money import Money
from hope_core.schemas import DiscoveryProgress, GrantCandidate
from hope_core.testing.factories import TENANT_A, TENANT_B, agency_profile
from psycopg.types.json import Jsonb

pytestmark = pytest.mark.db
APP_URL = "postgresql://hope_app:hope_app@localhost:5432/hope"
AGENCY_A = UUID("00000000-0000-4000-8000-0000000000aa")


@pytest.fixture
def conn(migrated_db: str) -> Iterator[psycopg.Connection[dict[str, object]]]:
    for tenant in (TENANT_A, TENANT_B):
        store.ensure_tenant(migrated_db, tenant)
    store.ensure_tenant(migrated_db, TENANT_A, AGENCY_A, "Riverbend")
    with psycopg.connect(migrated_db) as admin:
        admin.execute(
            "DELETE FROM grant_candidates WHERE tenant_id IN (%s, %s)", (TENANT_A, TENANT_B)
        )
        admin.execute("DELETE FROM jobs WHERE tenant_id IN (%s, %s)", (TENANT_A, TENANT_B))
        admin.execute("DELETE FROM users WHERE tenant_id IN (%s, %s)", (TENANT_A, TENANT_B))
    with connect(APP_URL) as c:
        yield c


def candidate(url: str, score: int = 70, **overrides: object) -> GrantCandidate:
    data: dict[str, object] = {
        "grant_id": uuid4(),
        "title": "Grant " + url[-1],
        "funder": "Funder",
        "url": url,
        "summary": "Summary.",
        "amount_max": Money(amount_minor=2_500_000),
        "fit_score": score,
        "discovered_at": datetime.now(UTC),
    }
    data.update(overrides)
    return GrantCandidate.model_validate(data)


def test_users_round_trip_and_email_is_case_insensitive(conn: psycopg.Connection) -> None:
    with tenant_tx(conn, TENANT_A) as tx:
        user = store.create_user(tx, "Dana@Riverbend.org", "hash", "Dana")
        assert store.get_user(tx, user.user_id) == user
        assert store.get_user_by_email(tx, "dana@riverbend.org") == user
    with pytest.raises(psycopg.errors.UniqueViolation), tenant_tx(conn, TENANT_A) as tx:
        store.create_user(tx, "DANA@riverbend.org", "hash", "Dana 2")


def test_get_profile_returns_current_version(conn: psycopg.Connection, migrated_db: str) -> None:
    with tenant_tx(conn, TENANT_A) as tx:
        tx.execute("DELETE FROM agency_profile_versions WHERE agency_id = %s", (AGENCY_A,))
        assert store.get_profile(tx, AGENCY_A) is None
        for version in (1, 2):
            profile = agency_profile(agency_id=AGENCY_A, version=version)
            tx.execute(
                "INSERT INTO agency_profile_versions (agency_id, tenant_id, version, profile,"
                " recorded_by) VALUES (%s, current_tenant(), %s, %s, 'test')",
                (AGENCY_A, version, Jsonb(profile.model_dump(mode="json"))),
            )
        current = store.get_profile(tx, AGENCY_A)
        assert current is not None and current.version == 2


def test_jobs_round_trip(conn: psycopg.Connection) -> None:
    with tenant_tx(conn, TENANT_A) as tx:
        job = store.create_job(tx, "discovery")
        assert job.status == "queued"
        store.update_job_progress(tx, job.job_id, DiscoveryProgress(queries_total=3, pages_read=2))
        running = store.get_job(tx, job.job_id)
        assert running is not None and running.status == "running"
        assert running.as_discovery_job().progress.pages_read == 2
        store.finish_job(tx, job.job_id, result={"counts": {"new": 1}})
        done = store.get_job(tx, job.job_id)
        assert done is not None and done.status == "done" and done.result == {"counts": {"new": 1}}
        later = store.create_job(tx, "discovery")
        store.finish_job(tx, later.job_id, error="boom")
        assert store.latest_job(tx, "discovery") == store.get_job(tx, later.job_id)
        assert [j.job_id for j in store.list_jobs(tx, "discovery", 10)] == [
            later.job_id,
            job.job_id,
        ]
        assert store.latest_job(tx, "discovery", subject_id="x") is None


def test_upsert_keeps_status_on_url_conflict(conn: psycopg.Connection) -> None:
    url = "https://funder.example.org/grant-1"
    with tenant_tx(conn, TENANT_A) as tx:
        first = store.upsert_candidate(tx, candidate(url, 60))
        store.set_candidate_status(tx, first.grant_id, "saved")
        again = store.upsert_candidate(tx, candidate(url, 90, title="Renamed"))
        assert again.grant_id == first.grant_id
        assert again.status == "saved" and again.fit_score == 90 and again.title == "Renamed"
        assert store.get_candidate(tx, first.grant_id) == again


def test_list_and_count_candidates(conn: psycopg.Connection) -> None:
    with tenant_tx(conn, TENANT_A) as tx:
        job = store.create_job(tx, "discovery")
        made = [
            store.upsert_candidate(
                tx, candidate(f"https://f.example.org/g{i}", 50 + i, found_by_job_id=job.job_id)
            )
            for i in range(5)
        ]
        store.set_candidate_status(tx, made[0].grant_id, "saved")
        passed = store.set_candidate_status(
            tx, made[1].grant_id, "passed", reason="not_eligible", reason_text="Outside area"
        )
        assert passed is not None and passed.status == "passed"
        counts = store.count_candidates(tx)
        assert counts == {"new": 3, "saved": 1, "passed": 1}
        for status, n in counts.items():
            assert len(store.list_candidates(tx, status)) == n  # type: ignore[arg-type]
        by_fit = store.list_candidates(tx, "new", "fit", limit=2)
        assert [c.fit_score for c in by_fit] == [54, 53]
        assert [c.fit_score for c in store.list_candidates(tx, "new", "fit", 2, 2)] == [52]
        assert len(store.list_candidates(tx, job_id=job.job_id)) == 5
        tx.execute(
            "SELECT pass_reason FROM grant_candidates WHERE grant_id = %s", (made[1].grant_id,)
        )
        assert tx.fetchone() == {"pass_reason": "not_eligible"}


def test_rls_blocks_other_tenant(conn: psycopg.Connection) -> None:
    with tenant_tx(conn, TENANT_A) as tx:
        user = store.create_user(tx, "a@a.org", "hash", "A")
        job = store.create_job(tx, "discovery")
        grant = store.upsert_candidate(tx, candidate("https://f.example.org/rls"))
    with tenant_tx(conn, TENANT_B) as tx:
        assert store.get_user(tx, user.user_id) is None
        assert store.get_job(tx, job.job_id) is None
        assert store.get_candidate(tx, grant.grant_id) is None
        assert store.count_candidates(tx) == {"new": 0, "saved": 0, "passed": 0}
        assert store.set_candidate_status(tx, grant.grant_id, "saved") is None
