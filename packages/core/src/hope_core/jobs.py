"""Background job runner (H0 section 8): a thread pool inside the API process."""

from __future__ import annotations

import logging
import threading
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
HEARTBEAT_SECONDS = 15.0
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
        target = job_id or store.create_job(tx, kind, created_by=created_by).job_id
        if not store.claim_job(tx, target, kind):
            raise ValueError(f"job {job_id} is not a queued {kind!r} job")
        return target

    claimed = _with_tx(_claim)
    if get_settings().jobs_inline:
        _run(claimed, fn, args)
    else:
        _pool.submit(_run, claimed, fn, args)
    return claimed


def fail_interrupted_jobs() -> int:
    """Jobs whose worker stopped heartbeating (crash, restart) are marked failed."""
    return _with_tx(store.fail_interrupted_jobs)


def start_stale_sweeper(interval: float = 60.0) -> threading.Event:
    """Keep failing stale jobs while the API runs, so a crash just before a restart still ends.

    Set the returned event to stop the sweeper."""
    stop = threading.Event()

    def _sweep() -> None:
        while not stop.wait(interval):
            try:
                if failed := fail_interrupted_jobs():
                    log.info("marked %d interrupted jobs failed", failed)
            except Exception:
                log.warning("stale job sweep failed", exc_info=True)

    threading.Thread(target=_sweep, daemon=True, name="hope-job-sweeper").start()
    return stop


def _heartbeat(job_id: UUID, stop: threading.Event) -> None:
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            _with_tx(lambda tx: store.heartbeat_job(tx, job_id))
        except Exception:
            log.warning("heartbeat for job %s failed", job_id, exc_info=True)


def _run(job_id: UUID, fn: Callable[..., JobResult], args: tuple[Any, ...]) -> None:
    token = _current_job.set(job_id)
    stop = threading.Event()
    threading.Thread(target=_heartbeat, args=(job_id, stop), daemon=True).start()
    try:
        result = fn(*args)
    except Exception as exc:
        log.exception("job %s failed", job_id)
        message = (str(exc).strip().splitlines() or [type(exc).__name__])[0][:300]
        finish(job_id, error=message)
    else:
        finish(job_id, result=result)
    finally:
        stop.set()
        _current_job.reset(token)


def _with_tx[R](fn: Callable[[store.Tx], R]) -> R:
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        return fn(tx)
