from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest
from hope_core import store
from hope_core.db import connect, tenant_tx
from hope_core.settings import get_settings
from hope_discovery import demo_grants
from hope_discovery.demo_grants import NCW_YOUTH, TITLE_X, YOUTH_TREATMENT, grant_id
from hope_pillar import demo_bids
from hope_pillar.api.bids import _load
from hope_pillar.demo import seed_user

pytestmark = pytest.mark.db


def test_demo_bids_seed_once_at_three_points(migrated_db: str) -> None:
    settings = get_settings()
    store.ensure_tenant(migrated_db, settings.tenant_id, settings.agency_id)
    seed_user()
    with connect() as conn, tenant_tx(conn, settings.tenant_id) as tx:
        demo_grants.seed_grants(tx, datetime.now().astimezone().date())
        ids = [grant_id(tx, u) for u in demo_bids.BIDS]
        tx.execute("DELETE FROM applications WHERE grant_id = ANY(%s)", (ids,))
    assert demo_bids.seed() is True
    assert demo_bids.seed() is False

    with connect() as conn, tenant_tx(conn, settings.tenant_id) as tx:
        views = {}
        for url in (TITLE_X, NCW_YOUTH, YOUTH_TREATMENT):
            gid = grant_id(tx, url)
            tx.execute("SELECT application_id FROM applications WHERE grant_id = %s", (gid,))
            row = tx.fetchone()
            assert row is not None
            views[url] = _load(tx, UUID(str(row["application_id"])))
            grant = store.get_candidate(tx, gid) if gid else None
            assert grant is not None and grant.status == "saved"

    prep, prep_app, _ = views[TITLE_X]
    assert prep.phase == "preparing" and prep_app.stage == "drafting"
    statuses = {i.status for i in prep.items}
    assert statuses == {"missing", "working", "ready"}
    assert {i.owner is None for i in prep.items} == {True, False}
    assert 0 < prep.ready < prep.total and prep.blocker_list

    final, final_app, _ = views[NCW_YOUTH]
    assert final.phase == "final_reviewed" and final_app.stage == "ready"
    assert final.ready == final.total and not final.blocker_list
    assert all(
        i.status == "ready" and i.review is not None and not i.review.stale for i in final.items
    )

    sent, sent_app, _ = views[YOUTH_TREATMENT]
    assert sent.phase == "submitted" and sent_app.stage == "submitted"
    assert sent.submission is not None and "demo" in sent.submission.receipt
    assert all(i.review is not None and not i.review.stale for i in sent.items)
