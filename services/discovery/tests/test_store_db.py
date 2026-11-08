from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
import pytest
from hope_core import store
from hope_core.model_gateway import MockProvider, ModelGateway
from hope_discovery import mock, repo
from hope_discovery.agent import DiscoveryAgent, grant_id_for
from hope_discovery.demo import DEMO_REQUEST, _DemoRepo, demo_profile
from hope_discovery.mock import ORAL, UNQUOTED
from hope_discovery.settings import DiscoverySettings

pytestmark = pytest.mark.db
CREATOR = UUID(int=1)


def run_once(**settings: Any) -> UUID:
    def create(tx: repo.Tx) -> UUID:
        job = store.create_job(tx, repo.KIND)
        repo.insert_run(tx, job.job_id, *DEMO_REQUEST, None, CREATOR)
        store.claim_job(tx, job.job_id, repo.KIND)
        job_id: UUID = job.job_id
        return job_id

    job_id = repo.with_tx(create)
    gateway = ModelGateway([mock.register(MockProvider())])
    agent = DiscoveryAgent(
        _DemoRepo(demo_profile()), gateway, mock.recorded_web(), DiscoverySettings(**settings)
    )
    result = agent.run(job_id)
    repo.with_tx(lambda tx: store.finish_job(tx, job_id, result=result))
    return job_id


def test_rerun_keeps_status_and_is_new(clean_db: str) -> None:
    first = run_once()
    events = repo.with_tx(lambda tx: repo.list_events(tx, first))
    saved = [e for e in events if e["kind"] == "candidate"]
    assert len(saved) == 3 and all(e["is_new"] for e in saved)
    oral = grant_id_for(ORAL)
    assert oral in {e["grant_id"] for e in saved}
    repo.with_tx(lambda tx: store.set_candidate_status(tx, oral, "saved"))

    skipped = run_once()
    run = repo.with_tx(lambda tx: repo.get_run(tx, skipped))
    assert run is not None and run["counts"]["skipped_known"] == 3

    second = run_once(known_url_days=0)
    events = repo.with_tx(lambda tx: repo.list_events(tx, second))
    saved = [e for e in events if e["kind"] == "candidate"]
    assert len(saved) == 3 and not any(e["is_new"] for e in saved)
    pairs = repo.with_tx(lambda tx: repo.job_candidates(tx, second))
    by_id = {c.grant_id: (c, is_new) for c, is_new in pairs}
    assert by_id[oral][0].status == "saved" and by_id[oral][1] is False
    assert by_id[oral][0].found_by_job_id == second
    run = repo.with_tx(lambda tx: repo.get_run(tx, second))
    assert run is not None and run["counts"]["candidates_updated"] == 3


def test_no_raw_page_text_persisted(clean_db: str) -> None:
    run_once()
    dump = []
    with psycopg.connect(clean_db) as conn:
        for table in ("jobs", "discovery_runs", "discovery_job_events", "grant_candidates"):
            rows = conn.execute(f"SELECT to_jsonb(t)::text FROM {table} t").fetchall()
            dump.extend(r[0] for r in rows)
    text = "\n".join(dump)
    assert "Rural Oral Health Access Grant 2027" in text
    for phrase in UNQUOTED:
        assert phrase not in text
