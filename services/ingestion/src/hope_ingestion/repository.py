"""Persistence for public, cross-tenant ingestion data. Postgres writes go through
`hope_system` (HOPE_DATABASE_SYSTEM_URL); `hope_app` can only read these tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, cast
from uuid import UUID

import psycopg
from hope_core.db import connect
from hope_core.envelope import DataClassification
from hope_core.hashing import content_hash
from hope_core.schemas.grant_opportunity import GrantOpportunity
from hope_core.settings import get_settings
from psycopg.types.json import Jsonb

from hope_ingestion.artifacts import StoredArtifact
from hope_ingestion.connectors.base import Cursor


@dataclass(frozen=True)
class StoredVersion:
    opportunity_id: UUID
    version: int
    amendment_seq: int
    normalized: dict[str, Any]
    content_hash: str


class OpportunityRepository(Protocol):
    def latest(self, source_system: str, source_id: str) -> StoredVersion | None: ...

    def save(self, opportunity: GrantOpportunity) -> StoredVersion: ...

    def save_signature(self, opportunity_id: UUID, num_perm: int, values: list[int]) -> None: ...

    def signatures(self) -> list[tuple[UUID, list[int]]]: ...


@dataclass
class InMemoryOpportunityRepository:
    versions: dict[tuple[str, str], list[StoredVersion]] = field(default_factory=dict)
    minhash: dict[UUID, list[int]] = field(default_factory=dict)

    def latest(self, source_system: str, source_id: str) -> StoredVersion | None:
        history = self.versions.get((source_system, source_id))
        return history[-1] if history else None

    def save(self, opportunity: GrantOpportunity) -> StoredVersion:
        history = self.versions.setdefault(
            (opportunity.source.system, opportunity.source.source_id), []
        )
        stored = StoredVersion(
            opportunity_id=history[0].opportunity_id if history else opportunity.opportunity_id,
            version=len(history) + 1,
            amendment_seq=opportunity.source.amendment_seq,
            normalized=opportunity.model_dump(mode="json"),
            content_hash=content_hash(opportunity),
        )
        history.append(stored)
        return stored

    def save_signature(self, opportunity_id: UUID, num_perm: int, values: list[int]) -> None:
        self.minhash[opportunity_id] = values

    def signatures(self) -> list[tuple[UUID, list[int]]]:
        return list(self.minhash.items())


Row = dict[str, Any]


class PostgresIngestionStore:
    """OpportunityRepository + ArtifactIndex + connector cursors on Postgres."""

    def __init__(self, url: str | None = None) -> None:
        self.url = url or get_settings().database_system_url

    def _conn(self) -> psycopg.Connection[dict[str, object]]:
        return connect(self.url)

    def latest(self, source_system: str, source_id: str) -> StoredVersion | None:
        with self._conn() as conn:
            row = cast(
                Row | None,
                conn.execute(
                    "SELECT v.opportunity_id, v.version, v.amendment_seq, v.normalized,"
                    " v.content_hash FROM opportunities o JOIN opportunity_versions v"
                    " ON v.opportunity_id = o.opportunity_id AND v.version = o.current_version"
                    " WHERE o.source_system = %s AND o.source_id = %s",
                    (source_system, source_id),
                ).fetchone(),
            )
        return StoredVersion(**row) if row else None

    def save(self, opportunity: GrantOpportunity) -> StoredVersion:
        due = opportunity.deadlines.application_due
        with self._conn() as conn, conn.transaction():
            row = cast(
                Row,
                conn.execute(
                    "INSERT INTO opportunities (opportunity_id, source_system, source_id, title,"
                    " application_due) VALUES (%s, %s, %s, %s, %s)"
                    " ON CONFLICT (source_system, source_id) DO UPDATE SET"
                    " current_version = opportunities.current_version + 1,"
                    " title = EXCLUDED.title, application_due = EXCLUDED.application_due"
                    " RETURNING opportunity_id, current_version",
                    (
                        opportunity.opportunity_id,
                        opportunity.source.system,
                        opportunity.source.source_id,
                        opportunity.title,
                        due.value if due else None,
                    ),
                ).fetchone(),
            )
            stored = opportunity.model_copy(update={"opportunity_id": row["opportunity_id"]})
            normalized = stored.model_dump(mode="json")
            digest = content_hash(stored)
            conn.execute(
                "INSERT INTO opportunity_versions (opportunity_id, version, amendment_seq,"
                " normalized, content_hash) VALUES (%s, %s, %s, %s, %s)",
                (
                    row["opportunity_id"],
                    row["current_version"],
                    opportunity.source.amendment_seq,
                    Jsonb(normalized),
                    digest,
                ),
            )
        return StoredVersion(
            row["opportunity_id"],
            row["current_version"],
            opportunity.source.amendment_seq,
            normalized,
            digest,
        )

    def save_signature(self, opportunity_id: UUID, num_perm: int, values: list[int]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO opportunity_minhash (opportunity_id, num_perm, hashvalues)"
                " VALUES (%s, %s, %s) ON CONFLICT (opportunity_id) DO UPDATE SET"
                " num_perm = EXCLUDED.num_perm, hashvalues = EXCLUDED.hashvalues,"
                " updated_at = now()",
                (opportunity_id, num_perm, values),
            )

    def signatures(self) -> list[tuple[UUID, list[int]]]:
        with self._conn() as conn:
            rows = cast(
                list[Row],
                conn.execute(
                    "SELECT opportunity_id, hashvalues FROM opportunity_minhash"
                ).fetchall(),
            )
        return [(r["opportunity_id"], list(r["hashvalues"])) for r in rows]

    def find(self, sha256: str, tenant_id: UUID | None) -> StoredArtifact | None:
        with self._conn() as conn:
            row = cast(
                Row | None,
                conn.execute(
                    "SELECT artifact_id::text, sha256, storage_uri, media_type FROM artifacts"
                    " WHERE sha256 = %s AND tenant_id IS NOT DISTINCT FROM %s LIMIT 1",
                    (sha256, tenant_id),
                ).fetchone(),
            )
        return StoredArtifact(size=-1, **row) if row else None

    def insert(
        self,
        artifact: StoredArtifact,
        tenant_id: UUID | None,
        classification: DataClassification,
    ) -> StoredArtifact:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO artifacts (artifact_id, tenant_id, sha256, storage_uri, media_type,"
                " classification) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (
                    artifact.artifact_id,
                    tenant_id,
                    artifact.sha256,
                    artifact.storage_uri,
                    artifact.media_type,
                    classification,
                ),
            )
        return self.find(artifact.sha256, tenant_id) or artifact

    def quarantine(self, sha256: str, reason: str, source_ref: str | None) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO artifact_quarantine (sha256, reason, source_ref) VALUES (%s, %s, %s)",
                (sha256, reason, source_ref),
            )

    def get_cursor(self, source_system: str, search_key: str) -> Cursor:
        with self._conn() as conn:
            row = cast(
                Row | None,
                conn.execute(
                    "SELECT cursor FROM connector_cursors WHERE source_system = %s"
                    " AND search_key = %s",
                    (source_system, search_key),
                ).fetchone(),
            )
        return Cursor.model_validate(row["cursor"]) if row else Cursor()

    def put_cursor(self, source_system: str, search_key: str, cursor: Cursor) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO connector_cursors (source_system, search_key, cursor)"
                " VALUES (%s, %s, %s) ON CONFLICT (source_system, search_key) DO UPDATE SET"
                " cursor = EXCLUDED.cursor, updated_at = now()",
                (source_system, search_key, Jsonb(cursor.model_dump(mode="json"))),
            )
