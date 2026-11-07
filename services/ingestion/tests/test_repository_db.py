from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest
from hope_core.money import Money
from hope_core.schemas.grant_opportunity import Source
from hope_core.testing.factories import grant_opportunity
from hope_ingestion.artifacts import ArtifactStore, InMemoryBlobStore
from hope_ingestion.connectors.base import Cursor
from hope_ingestion.repository import PostgresIngestionStore
from hope_ingestion.testing import RFP_PAGES, make_pdf

pytestmark = pytest.mark.db

SYSTEM_URL = "postgresql://hope_system:hope_system@localhost:5432/hope"
APP_URL = "postgresql://hope_app:hope_app@localhost:5432/hope"


def test_versions_minhash_and_cursor_roundtrip(migrated_db: str) -> None:
    store = PostgresIngestionStore(SYSTEM_URL)
    source = Source(system="grants_gov", source_id=f"TEST-{uuid4()}")
    first = grant_opportunity(source=source)
    v1 = store.save(first)
    amended = first.model_copy(
        update={
            "opportunity_id": uuid4(),
            "source": source.model_copy(update={"amendment_seq": 1}),
            "funding": first.funding.model_copy(update={"award_ceiling": Money.from_decimal("1")}),
        }
    )
    v2 = store.save(amended)
    assert (v1.version, v2.version) == (1, 2)
    assert v2.opportunity_id == v1.opportunity_id == first.opportunity_id
    latest = store.latest("grants_gov", source.source_id)
    assert latest is not None and latest.version == 2 and latest.amendment_seq == 1
    assert latest.normalized["opportunity_id"] == str(first.opportunity_id)

    store.save_signature(v1.opportunity_id, 4, [1, 2, 3, 4_294_967_295])
    assert (v1.opportunity_id, [1, 2, 3, 4_294_967_295]) in store.signatures()

    key = f"search-{uuid4()}"
    assert store.get_cursor("grants_gov", key) == Cursor()
    store.put_cursor("grants_gov", key, Cursor(position=25))
    assert store.get_cursor("grants_gov", key).position == 25


def test_public_artifact_rows_and_quarantine(migrated_db: str) -> None:
    store = PostgresIngestionStore(SYSTEM_URL)
    artifacts = ArtifactStore(InMemoryBlobStore(), store)
    data = make_pdf([[*RFP_PAGES[0], str(uuid4())]])
    first = artifacts.put(data, filename="rfp.pdf")
    again = artifacts.put(data)
    assert first.artifact_id == again.artifact_id
    with psycopg.connect(SYSTEM_URL) as conn:
        rows = conn.execute(
            "SELECT tenant_id, media_type FROM artifacts WHERE sha256 = %s", (first.sha256,)
        ).fetchall()
    assert rows == [(None, "application/pdf")]
    store.quarantine("deadbeef", "pdf_encrypted", "upload")


def test_hope_app_cannot_write_public_opportunity_data(migrated_db: str) -> None:
    with psycopg.connect(APP_URL) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("INSERT INTO connector_cursors (source_system, search_key) VALUES ('x', 'y')")
