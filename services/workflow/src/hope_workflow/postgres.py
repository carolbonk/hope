"""Postgres adapters for the approvals log and the tenant_opportunity projection (RLS-scoped)."""

from __future__ import annotations

from dataclasses import dataclass

from hope_core.db import connect, tenant_tx

from hope_workflow.contracts import ApprovalRecord, ProjectionRow


@dataclass
class PostgresApprovalStore:
    url: str | None = None

    def append(self, r: ApprovalRecord) -> None:
        with connect(self.url) as conn, tenant_tx(conn, r.tenant_id) as cur:
            cur.execute(
                "INSERT INTO approvals (approval_id, tenant_id, workflow_id, gate, decision,"
                " artifact_hash, decided_by, decided_at, comment)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (approval_id) DO NOTHING",
                (
                    r.approval_id,
                    r.tenant_id,
                    r.workflow_id,
                    r.gate.value,
                    r.decision,
                    r.artifact_hash,
                    r.decided_by,
                    r.decided_at,
                    r.comment,
                ),
            )


@dataclass
class PostgresProjectionStore:
    url: str | None = None

    def upsert(self, row: ProjectionRow) -> None:
        with connect(self.url) as conn, tenant_tx(conn, row.tenant_id) as cur:
            cur.execute(
                "INSERT INTO tenant_opportunity (tenant_id, opportunity_id, agency_id, state,"
                " workflow_id, composite_score, recommendation, internal_deadline)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (tenant_id, opportunity_id, agency_id) DO UPDATE SET"
                " state = EXCLUDED.state, workflow_id = EXCLUDED.workflow_id,"
                " composite_score = COALESCE(EXCLUDED.composite_score,"
                " tenant_opportunity.composite_score),"
                " recommendation = COALESCE(EXCLUDED.recommendation,"
                " tenant_opportunity.recommendation),"
                " internal_deadline = EXCLUDED.internal_deadline, updated_at = now()",
                (
                    row.tenant_id,
                    row.opportunity_id,
                    row.agency_id,
                    row.state.value,
                    row.workflow_id,
                    row.composite_score,
                    row.recommendation,
                    row.internal_deadline,
                ),
            )
