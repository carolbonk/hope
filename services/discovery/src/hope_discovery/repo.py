"""Discovery persistence: `discovery_runs`, `discovery_job_events` and the reads the API needs."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from hope_core import store
from hope_core.db import connect, tenant_tx
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.hackathon import DiscoveryProgress, GrantCandidate, JobStatus
from hope_core.settings import get_settings
from hope_core.store import Tx
from psycopg.types.json import Jsonb

KIND = "discovery"


def with_tx[R](fn: Callable[[Tx], R]) -> R:
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        return fn(tx)


# --- writes (inside a caller's transaction) ----------------------------------------------------


def lock(tx: Tx) -> None:
    tx.execute("SELECT pg_advisory_xact_lock(hashtext('hope:discovery'))")


def active_job_id(tx: Tx) -> UUID | None:
    tx.execute(
        "SELECT job_id FROM jobs WHERE kind = %s AND status IN ('queued','running')"
        " ORDER BY started_at DESC LIMIT 1",
        (KIND,),
    )
    row = tx.fetchone()
    return UUID(str(row["job_id"])) if row else None


def jobs_since(tx: Tx, since: datetime) -> int:
    tx.execute("SELECT count(*) AS n FROM jobs WHERE kind = %s AND started_at >= %s", (KIND, since))
    row = tx.fetchone()
    return int(row["n"]) if row else 0


def insert_run(
    tx: Tx,
    job_id: UUID,
    focus_keywords: list[str],
    location: str | None,
    profile_version: int | None,
    created_by: UUID,
) -> None:
    tx.execute(
        "INSERT INTO discovery_runs"
        " (job_id, tenant_id, focus_keywords, location, profile_version, created_by)"
        " VALUES (%s, current_tenant(), %s, %s, %s, %s)",
        (str(job_id), focus_keywords, location, profile_version, str(created_by)),
    )


def add_event(tx: Tx, job_id: UUID, kind: str, text: str, **fields: Any) -> int:
    cols = ["query", "url", "grant_id", "is_new", "result_count"]
    values = [str(fields[c]) if c == "grant_id" and fields.get(c) else fields.get(c) for c in cols]
    tx.execute(
        "INSERT INTO discovery_job_events"
        f" (job_id, tenant_id, seq, kind, text, {', '.join(cols)})"
        " SELECT %s, current_tenant(),"
        "  COALESCE((SELECT max(seq) FROM discovery_job_events WHERE job_id = %s), 0) + 1,"
        "  %s, %s, %s, %s, %s, %s, %s RETURNING seq",
        (str(job_id), str(job_id), kind, text[:300], *values),
    )
    row = tx.fetchone()
    assert row is not None
    return int(row["seq"])


def set_queries(tx: Tx, job_id: UUID, queries: list[str]) -> None:
    tx.execute("UPDATE discovery_runs SET queries = %s WHERE job_id = %s", (queries, str(job_id)))


def set_counts(tx: Tx, job_id: UUID, counts: dict[str, int]) -> None:
    tx.execute(
        "UPDATE discovery_runs SET counts = %s WHERE job_id = %s", (Jsonb(counts), str(job_id))
    )


def known_urls(tx: Tx, urls: Iterable[str], since: datetime) -> set[str]:
    tx.execute(
        "SELECT url FROM grant_candidates WHERE url = ANY(%s) AND discovered_at >= %s",
        (list(urls), since),
    )
    return {str(r["url"]) for r in tx.fetchall()}


def url_exists(tx: Tx, url: str) -> bool:
    tx.execute("SELECT 1 FROM grant_candidates WHERE url = %s", (url,))
    return tx.fetchone() is not None


def shift_back(tx: Tx, job_id: UUID, delta: timedelta) -> None:
    """Demo seed: move one run (job, events, run row, its candidates) into the past."""
    jid = str(job_id)
    tx.execute(
        "UPDATE jobs SET started_at = started_at - %s, finished_at = finished_at - %s,"
        " heartbeat_at = heartbeat_at - %s WHERE job_id = %s",
        (delta, delta, delta, jid),
    )
    tx.execute(
        "UPDATE discovery_runs SET created_at = created_at - %s WHERE job_id = %s", (delta, jid)
    )
    tx.execute("UPDATE discovery_job_events SET at = at - %s WHERE job_id = %s", (delta, jid))
    tx.execute(
        "UPDATE grant_candidates SET discovered_at = discovered_at - %s WHERE found_by_job_id = %s",
        (delta, jid),
    )


# --- reads -------------------------------------------------------------------------------------


def get_run(tx: Tx, job_id: UUID | str) -> dict[str, Any] | None:
    tx.execute("SELECT * FROM discovery_runs WHERE job_id = %s", (str(job_id),))
    row: dict[str, Any] | None = tx.fetchone()
    return row


def list_events(tx: Tx, job_id: UUID | str, since_seq: int = 0) -> list[dict[str, Any]]:
    tx.execute(
        "SELECT * FROM discovery_job_events WHERE job_id = %s AND seq > %s ORDER BY seq",
        (str(job_id), since_seq),
    )
    rows: list[dict[str, Any]] = tx.fetchall()
    return rows


def last_seq(tx: Tx, job_id: UUID | str) -> int:
    tx.execute(
        "SELECT COALESCE(max(seq), 0) AS n FROM discovery_job_events WHERE job_id = %s",
        (str(job_id),),
    )
    row = tx.fetchone()
    return int(row["n"]) if row else 0


def job_candidates(tx: Tx, job_id: UUID | str) -> list[tuple[GrantCandidate, bool]]:
    """Candidates saved by this run's `candidate` events, joined to their current rows."""
    tx.execute(
        "SELECT DISTINCT ON (e.grant_id) e.grant_id, e.is_new, e.seq FROM discovery_job_events e"
        " WHERE e.job_id = %s AND e.kind = 'candidate' AND e.grant_id IS NOT NULL"
        " ORDER BY e.grant_id, e.seq",
        (str(job_id),),
    )
    events = sorted(tx.fetchall(), key=lambda r: int(r["seq"]))
    out = []
    for ev in events:
        candidate = store.get_candidate(tx, ev["grant_id"])
        if candidate is not None:
            out.append((candidate, bool(ev["is_new"])))
    return out


def list_runs(tx: Tx, limit: int) -> list[dict[str, Any]]:
    tx.execute(
        "SELECT j.*, r.focus_keywords, r.location, r.counts AS run_counts"
        " FROM jobs j JOIN discovery_runs r USING (job_id)"
        " WHERE j.kind = %s ORDER BY j.started_at DESC LIMIT %s",
        (KIND, limit),
    )
    rows: list[dict[str, Any]] = tx.fetchall()
    return rows


# --- the agent's view of storage ---------------------------------------------------------------


class DiscoveryRepo(Protocol):
    def load_profile(self) -> AgencyProfile | None: ...
    def load_request(self, job_id: UUID) -> tuple[list[str], str | None]: ...
    def progress(self, job_id: UUID, progress: DiscoveryProgress, status: JobStatus) -> None: ...
    def event(self, job_id: UUID, kind: str, text: str, **fields: Any) -> int: ...
    def set_queries(self, job_id: UUID, queries: list[str]) -> None: ...
    def set_counts(self, job_id: UUID, counts: dict[str, int]) -> None: ...
    def known_urls(self, urls: list[str], since: datetime) -> set[str]: ...
    def url_exists(self, url: str) -> bool: ...
    def upsert(self, candidate: GrantCandidate) -> GrantCandidate: ...


class DbRepo:
    """One short `tenant_tx` per write, so the run panel sees each step as it happens."""

    def load_profile(self) -> AgencyProfile | None:
        return with_tx(store.get_profile)

    def load_request(self, job_id: UUID) -> tuple[list[str], str | None]:
        run = with_tx(lambda tx: get_run(tx, job_id))
        if run is None:
            return [], None
        return list(run["focus_keywords"] or []), run["location"]

    def progress(self, job_id: UUID, progress: DiscoveryProgress, status: JobStatus) -> None:
        with_tx(lambda tx: store.update_job_progress(tx, job_id, progress, status=status))

    def event(self, job_id: UUID, kind: str, text: str, **fields: Any) -> int:
        return with_tx(lambda tx: add_event(tx, job_id, kind, text, **fields))

    def set_queries(self, job_id: UUID, queries: list[str]) -> None:
        with_tx(lambda tx: set_queries(tx, job_id, queries))

    def set_counts(self, job_id: UUID, counts: dict[str, int]) -> None:
        with_tx(lambda tx: set_counts(tx, job_id, counts))

    def known_urls(self, urls: list[str], since: datetime) -> set[str]:
        return with_tx(lambda tx: known_urls(tx, urls, since))

    def url_exists(self, url: str) -> bool:
        return with_tx(lambda tx: url_exists(tx, url))

    def upsert(self, candidate: GrantCandidate) -> GrantCandidate:
        return with_tx(lambda tx: store.upsert_candidate(tx, candidate))
