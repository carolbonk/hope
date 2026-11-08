"""Start reading a saved grant's requirements once, so the workspace opens with them ready."""

from __future__ import annotations

import logging
from uuid import UUID

from hope_core import jobs, store
from hope_core.db import connect, tenant_tx

from hope_pillar.api.applications import REQUIREMENTS_KIND, latest_requirements, run_requirements

log = logging.getLogger(__name__)

ENABLED = True


def start_requirements_once(tenant_id: UUID, application_id: UUID, actor: UUID) -> UUID | None:
    """Start the requirements job unless this application ever had one or has requirements.

    Best effort: never raises, so a failure here can't fail the save that called it."""
    if not ENABLED:
        return None
    try:
        started = _queue(tenant_id, application_id, actor)
    except Exception:
        log.warning("could not queue requirements for %s", application_id, exc_info=True)
        return None
    if started is None:
        return None
    job_id, url = started
    try:
        return jobs.start_job(
            REQUIREMENTS_KIND,
            run_requirements,
            application_id,
            url,
            job_id=job_id,
            created_by=actor,
        )
    except Exception:
        log.warning("could not start reading requirements for %s", application_id, exc_info=True)
        _undo(tenant_id, application_id, job_id)
        return None


def _queue(tenant_id: UUID, application_id: UUID, actor: UUID) -> tuple[UUID, str] | None:
    with connect() as conn, tenant_tx(conn, tenant_id) as tx:
        # Same lock as the manual "Read the funder's pages" route, so the two can't race.
        tx.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))", (f"requirements:{application_id}",)
        )
        if store.latest_job(tx, REQUIREMENTS_KIND, str(application_id)) or latest_requirements(
            tx, application_id
        ):
            return None
        tx.execute(
            "SELECT g.url FROM applications a JOIN grant_candidates g USING (grant_id)"
            " WHERE a.application_id = %s",
            (application_id,),
        )
        row = tx.fetchone()
        if row is None:
            return None
        job = store.create_job(tx, REQUIREMENTS_KIND, str(application_id), actor)
        tx.execute(
            "UPDATE applications SET questions_status = 'reading' WHERE application_id = %s",
            (application_id,),
        )
        return job.job_id, str(row["url"])


def _undo(tenant_id: UUID, application_id: UUID, job_id: UUID) -> None:
    """A job that never started must not leave the workspace stuck on "reading"."""
    try:
        jobs.finish(job_id, error="Could not start the job")
        with connect() as conn, tenant_tx(conn, tenant_id) as tx:
            tx.execute(
                "UPDATE applications SET questions_status = 'unread'"
                " WHERE application_id = %s AND questions_status = 'reading'",
                (application_id,),
            )
    except Exception:
        log.warning("could not clean up requirements job %s", job_id, exc_info=True)
