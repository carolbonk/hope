"""Postgres persistence for tenant matching config and matrix snapshots (RLS via tenant_tx)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from hope_core.db import tenant_tx
from hope_core.hashing import content_hash
from hope_core.schemas.opportunity_matrix import OpportunityMatrix
from psycopg.types.json import Jsonb

from hope_matching.config import MatchingConfig

Conn = psycopg.Connection[dict[str, Any]]


def save_config(conn: Conn, tenant_id: UUID, config: MatchingConfig) -> None:
    with tenant_tx(conn, tenant_id) as cur:
        cur.execute(
            "INSERT INTO matching_tenant_config (tenant_id, config) VALUES (%s, %s)"
            " ON CONFLICT (tenant_id) DO UPDATE SET config = EXCLUDED.config, updated_at = now()",
            (tenant_id, Jsonb(config.model_dump(mode="json"))),
        )


def load_config(conn: Conn, tenant_id: UUID) -> MatchingConfig:
    with tenant_tx(conn, tenant_id) as cur:
        cur.execute("SELECT config FROM matching_tenant_config WHERE tenant_id = %s", (tenant_id,))
        row = cur.fetchone()
    return MatchingConfig.model_validate(row["config"]) if row else MatchingConfig()


def save_matrix(conn: Conn, tenant_id: UUID, matrix: OpportunityMatrix) -> str:
    digest = content_hash(matrix)
    with tenant_tx(conn, tenant_id) as cur:
        cur.execute(
            "INSERT INTO opportunity_matrices"
            " (tenant_id, agency_id, generated_at, model_version, matrix, content_hash)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (
                tenant_id,
                matrix.agency_id,
                matrix.generated_at,
                matrix.model_version,
                Jsonb(matrix.model_dump(mode="json")),
                digest,
            ),
        )
    return digest


def latest_matrix(conn: Conn, tenant_id: UUID, agency_id: UUID) -> OpportunityMatrix | None:
    with tenant_tx(conn, tenant_id) as cur:
        cur.execute(
            "SELECT matrix FROM opportunity_matrices WHERE agency_id = %s"
            " ORDER BY generated_at DESC, matrix_id DESC LIMIT 1",
            (agency_id,),
        )
        row = cur.fetchone()
    return OpportunityMatrix.model_validate(row["matrix"]) if row else None
