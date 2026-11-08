"""Typed store for the hackathon tables (H0 section 5).

Every function takes `tx`, a cursor from `hope_core.db.tenant_tx`; the tenant comes from RLS
(`current_tenant()`), never from a parameter.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.hackathon import (
    CandidateStatus,
    DiscoveryJob,
    DiscoveryProgress,
    GrantCandidate,
    JobStatus,
)
from hope_core.settings import get_settings

Tx = psycopg.Cursor[dict[str, Any]]
CandidateSort = Literal["fit", "deadline", "newest"]


class UserRecord(BaseModel):
    user_id: UUID
    tenant_id: UUID
    email: str
    password_hash: str
    display_name: str
    created_at: datetime


class JobRecord(BaseModel):
    job_id: UUID
    tenant_id: UUID
    kind: str
    subject_id: str | None
    status: JobStatus
    progress: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    created_by: UUID | None
    started_at: datetime
    finished_at: datetime | None

    def as_discovery_job(self, queries: list[str] | None = None) -> DiscoveryJob:
        return DiscoveryJob(
            job_id=self.job_id,
            status=self.status,
            queries=queries or [],
            progress=DiscoveryProgress.model_validate(self.progress),
            error=self.error,
            started_at=self.started_at,
            finished_at=self.finished_at,
        )


# --- users -----------------------------------------------------------------------------------


def create_user(tx: Tx, email: str, password_hash: str, display_name: str) -> UserRecord:
    tx.execute(
        "INSERT INTO users (tenant_id, email, password_hash, display_name)"
        " VALUES (current_tenant(), %s, %s, %s) RETURNING *",
        (email.strip(), password_hash, display_name),
    )
    return UserRecord.model_validate(tx.fetchone())


def get_user(tx: Tx, user_id: UUID | str) -> UserRecord | None:
    tx.execute("SELECT * FROM users WHERE user_id = %s", (str(user_id),))
    row = tx.fetchone()
    return UserRecord.model_validate(row) if row else None


def get_user_by_email(tx: Tx, email: str) -> UserRecord | None:
    tx.execute("SELECT * FROM users WHERE email = %s", (email.strip(),))
    row = tx.fetchone()
    return UserRecord.model_validate(row) if row else None


# --- profile ---------------------------------------------------------------------------------


def get_profile(tx: Tx, agency_id: UUID | str | None = None) -> AgencyProfile | None:
    """The current profile version of `agency_id` (default: the configured agency)."""
    tx.execute(
        "SELECT profile FROM agency_profile_versions WHERE agency_id = %s"
        " ORDER BY version DESC LIMIT 1",
        (str(agency_id or get_settings().agency_id),),
    )
    row = tx.fetchone()
    return AgencyProfile.model_validate(row["profile"]) if row else None


# --- jobs ------------------------------------------------------------------------------------


def create_job(
    tx: Tx, kind: str, subject_id: str | None = None, created_by: UUID | str | None = None
) -> JobRecord:
    tx.execute(
        "INSERT INTO jobs (tenant_id, kind, subject_id, created_by)"
        " VALUES (current_tenant(), %s, %s, %s) RETURNING *",
        (kind, subject_id, str(created_by) if created_by else None),
    )
    return JobRecord.model_validate(tx.fetchone())


def update_job_progress(
    tx: Tx,
    job_id: UUID | str,
    progress: BaseModel | dict[str, Any],
    *,
    status: JobStatus = "running",
) -> None:
    data = progress.model_dump(mode="json") if isinstance(progress, BaseModel) else progress
    tx.execute(
        "UPDATE jobs SET progress = %s, status = %s, heartbeat_at = now() WHERE job_id = %s",
        (Jsonb(data), status, str(job_id)),
    )


def claim_job(tx: Tx, job_id: UUID | str, kind: str) -> bool:
    """Atomically move a `queued` job of `kind` to `running`; False if someone else claimed it."""
    tx.execute(
        "UPDATE jobs SET status = 'running', heartbeat_at = now()"
        " WHERE job_id = %s AND kind = %s AND status = 'queued' RETURNING job_id",
        (str(job_id), kind),
    )
    return tx.fetchone() is not None


def heartbeat_job(tx: Tx, job_id: UUID | str) -> None:
    tx.execute(
        "UPDATE jobs SET heartbeat_at = now() WHERE job_id = %s AND status = 'running'",
        (str(job_id),),
    )


def finish_job(
    tx: Tx,
    job_id: UUID | str,
    *,
    result: BaseModel | dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    data = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
    tx.execute(
        "UPDATE jobs SET status = %s, result = %s, error = %s, finished_at = now()"
        " WHERE job_id = %s",
        (
            "failed" if error is not None else "done",
            Jsonb(data) if data is not None else None,
            error,
            str(job_id),
        ),
    )


def get_job(tx: Tx, job_id: UUID | str) -> JobRecord | None:
    tx.execute("SELECT * FROM jobs WHERE job_id = %s", (str(job_id),))
    row = tx.fetchone()
    return JobRecord.model_validate(row) if row else None


def latest_job(tx: Tx, kind: str, subject_id: str | None = None) -> JobRecord | None:
    tx.execute(
        "SELECT * FROM jobs WHERE kind = %s AND subject_id IS NOT DISTINCT FROM %s"
        " ORDER BY started_at DESC LIMIT 1",
        (kind, subject_id),
    )
    row = tx.fetchone()
    return JobRecord.model_validate(row) if row else None


def list_jobs(tx: Tx, kind: str, limit: int = 20) -> list[JobRecord]:
    tx.execute(
        "SELECT * FROM jobs WHERE kind = %s ORDER BY started_at DESC LIMIT %s", (kind, limit)
    )
    return [JobRecord.model_validate(r) for r in tx.fetchall()]


def fail_interrupted_jobs(
    tx: Tx, message: str = "Interrupted by restart", stale_after_seconds: int = 120
) -> int:
    """Fail `running` jobs whose heartbeat is stale; jobs live in another process are kept."""
    tx.execute(
        "UPDATE jobs SET status = 'failed', error = %s, finished_at = now()"
        " WHERE status = 'running'"
        " AND (heartbeat_at IS NULL OR heartbeat_at < now() - make_interval(secs => %s))",
        (message, stale_after_seconds),
    )
    return tx.rowcount


# --- grant candidates ------------------------------------------------------------------------

_CANDIDATE_FIELDS = (
    "title",
    "funder",
    "summary",
    "amount_text",
    "amount_max",
    "deadline_text",
    "deadline",
    "eligibility_summary",
    "fit_score",
    "fit_reasons",
    "concerns",
    "citations",
    "found_by_job_id",
    "discovered_at",
)
_JSON_FIELDS = {"amount_max", "fit_reasons", "concerns", "citations"}
_SORTS: dict[str, str] = {
    "fit": "fit_score DESC, discovered_at DESC",
    "deadline": "deadline ASC NULLS LAST, fit_score DESC",
    "newest": "discovered_at DESC",
}


def _candidate(row: dict[str, Any]) -> GrantCandidate:
    return GrantCandidate.model_validate(
        {k: v for k, v in row.items() if k in GrantCandidate.model_fields}
    )


def upsert_candidate(tx: Tx, candidate: GrantCandidate) -> GrantCandidate:
    """Insert by URL; on a URL conflict update the fields but keep `grant_id` and `status`."""
    data = candidate.model_dump(mode="json")
    values = [Jsonb(data[f]) if f in _JSON_FIELDS else data[f] for f in _CANDIDATE_FIELDS]
    cols = ", ".join(_CANDIDATE_FIELDS)
    updates = ", ".join(f"{f} = EXCLUDED.{f}" for f in _CANDIDATE_FIELDS)
    tx.execute(
        f"INSERT INTO grant_candidates (tenant_id, grant_id, url, status, {cols})"
        f" VALUES (current_tenant(), %s, %s, %s, {', '.join(['%s'] * len(values))})"
        f" ON CONFLICT (tenant_id, url) DO UPDATE SET {updates} RETURNING *",
        (data["grant_id"], data["url"], data["status"], *values),
    )
    row = tx.fetchone()
    assert row is not None
    return _candidate(row)


def get_candidate(tx: Tx, grant_id: UUID | str) -> GrantCandidate | None:
    tx.execute("SELECT * FROM grant_candidates WHERE grant_id = %s", (str(grant_id),))
    row = tx.fetchone()
    return _candidate(row) if row else None


def list_candidates(
    tx: Tx,
    status: CandidateStatus | None = None,
    sort: CandidateSort = "fit",
    limit: int = 50,
    offset: int = 0,
    job_id: UUID | str | None = None,
) -> list[GrantCandidate]:
    order = _SORTS[sort]
    tx.execute(
        "SELECT * FROM grant_candidates"
        " WHERE (%(status)s::text IS NULL OR status = %(status)s)"
        " AND (%(job)s::uuid IS NULL OR found_by_job_id = %(job)s)"
        f" ORDER BY {order}, grant_id LIMIT %(limit)s OFFSET %(offset)s",
        {
            "status": status,
            "job": str(job_id) if job_id else None,
            "limit": limit,
            "offset": offset,
        },
    )
    return [_candidate(r) for r in tx.fetchall()]


def count_candidates(tx: Tx) -> dict[str, int]:
    tx.execute("SELECT status, count(*) AS n FROM grant_candidates GROUP BY status")
    counts = {"new": 0, "saved": 0, "passed": 0}
    for row in tx.fetchall():
        counts[row["status"]] = row["n"]
    return counts


def set_candidate_status(
    tx: Tx,
    grant_id: UUID | str,
    status: CandidateStatus,
    *,
    reason: str | None = None,
    reason_text: str | None = None,
    actor: UUID | str | None = None,
) -> GrantCandidate | None:
    passed = status == "passed"
    tx.execute(
        "UPDATE grant_candidates SET status = %s, status_changed_at = now(),"
        " status_changed_by = %s, pass_reason = %s, pass_reason_text = %s"
        " WHERE grant_id = %s RETURNING *",
        (
            status,
            str(actor) if actor else None,
            reason if passed else None,
            reason_text if passed else None,
            str(grant_id),
        ),
    )
    row = tx.fetchone()
    return _candidate(row) if row else None


# --- bootstrap (system role) -----------------------------------------------------------------


def ensure_tenant(
    url: str, tenant_id: UUID, agency_id: UUID | None = None, legal_name: str = "Our nonprofit"
) -> None:
    """Idempotently create the configured tenant (and agency) as `hope_system` or admin."""
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (tenant_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (str(tenant_id), "Hope"),
        )
        if agency_id is not None:
            cur.execute(
                "INSERT INTO agencies (agency_id, tenant_id, legal_name) VALUES (%s, %s, %s)"
                " ON CONFLICT DO NOTHING",
                (str(agency_id), str(tenant_id), legal_name),
            )
