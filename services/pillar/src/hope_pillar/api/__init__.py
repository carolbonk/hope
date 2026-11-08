"""FastAPI app for the hackathon API: `uvicorn hope_pillar.api:app`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from hope_core import jobs, store
from hope_core.settings import get_settings
from hope_profile.api import router as profile_router

from hope_pillar.api import auth, discovery, errors, grants, me
from hope_pillar.api.deps import Services

log = logging.getLogger(__name__)

# Pillar-owned routers, each with its own OpenAPI snapshot.
ROUTERS: dict[str, APIRouter] = {
    "auth": auth.router,
    "me": me.router,
    "discovery": discovery.router,
    "grants": grants.router,
}


def bootstrap() -> None:
    """Create the configured tenant and agency, and fail jobs a previous process left running."""
    settings = get_settings()
    try:
        store.ensure_tenant(settings.database_system_url, settings.tenant_id, settings.agency_id)
        interrupted = jobs.fail_interrupted_jobs()
    except psycopg.OperationalError as exc:
        log.warning("database unavailable at startup: %s", exc)
        return
    if interrupted:
        log.info("marked %d interrupted jobs failed", interrupted)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    bootstrap()
    yield


def create_app(services: Services | None = None, *, legacy: bool = False) -> FastAPI:
    """The hackathon API. `legacy=True` also mounts the earlier pillar routes (their tests only)."""
    app = FastAPI(title="Hope API", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[get_settings().web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "If-Match"],
    )
    errors.install(app)
    if legacy:
        from hope_pillar.api.routes import router as legacy_router

        app.state.services = services or Services.from_settings()
        app.include_router(legacy_router)
    for router in ROUTERS.values():
        app.include_router(router)
    app.include_router(profile_router, prefix="/v1")
    return app


app = create_app()
