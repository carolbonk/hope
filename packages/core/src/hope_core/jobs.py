"""Background job runner (H0 section 8): a thread pool inside the API process."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from hope_core import store
from hope_core.db import connect, tenant_tx
from hope_core.settings import get_settings

log = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="hope-job")
_current_job: ContextVar[UUID | None] = ContextVar("hope_current_job", default=None)

JobResult = BaseModel | dict[str, Any] | None


def report(progress: BaseModel | dict[str, Any]) -> None:
    """Store progress for the job running in this thread."""
    job_id = _current_job.get()
    if job_id is None:
        raise RuntimeError("report() called outside a job")
    _with_tx(lambda tx: store.update_job_progress(tx, job_id, progress))


def finish(job_id: UUID, result: JobResult = None, error: str | None = None) -> None:
    def _finish(tx: store.Tx) -> None:
        job = store.get_job(tx, job_id)
        if job is not None and job.status in ("queued", "running"):
            store.finish_job(tx, job_id, result=result, error=error)

    _with_tx(_finish)


def start_job(
    kind: str,
    fn: Callable[..., JobResult],
    *args: Any,
    job_id: UUID | None = None,
    created_by: UUID | str | None = None,
) -> UUID:
    """Run `fn(*args)` as job `kind`; its return value is the job result."""

    def _claim(tx: store.Tx) -> UUID:
        if job_id is None:
            return store.create_job(tx, kind, created_by=created_by).job_id
        job = store.get_job(tx, job_id)
        if job is None or job.kind != kind or job.status != "queued":
            raise ValueError(f"job {job_id} is not a queued {kind!r} job")
        return job.job_id

    claimed = _with_tx(_claim)
    _with_tx(lambda tx: _mark_running(tx, claimed))
    if get_settings().jobs_inline:
        _run(claimed, fn, args)
    else:
        _pool.submit(_run, claimed, fn, args)
    return claimed


def fail_interrupted_jobs() -> int:
    """Startup hook: jobs left `running` by a previous process are marked failed."""
    return _with_tx(store.fail_interrupted_jobs)


def _mark_running(tx: store.Tx, job_id: UUID) -> None:
    tx.execute("UPDATE jobs SET status = 'running' WHERE job_id = %s", (str(job_id),))


def _run(job_id: UUID, fn: Callable[..., JobResult], args: tuple[Any, ...]) -> None:
    token = _current_job.set(job_id)
    try:
        result = fn(*args)
    except Exception as exc:
        log.exception("job %s failed", job_id)
        message = (str(exc).strip().splitlines() or [type(exc).__name__])[0][:300]
        finish(job_id, error=message)
    else:
        finish(job_id, result=result)
    finally:
        _current_job.reset(token)


def _with_tx[R](fn: Callable[[store.Tx], R]) -> R:
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        return fn(tx)
