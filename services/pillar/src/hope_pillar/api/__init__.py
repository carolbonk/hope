"""FastAPI app for the Grant Operations Pillar: `uvicorn hope_pillar.api:app`."""

from __future__ import annotations

from fastapi import FastAPI

from hope_pillar.api.deps import Services
from hope_pillar.api.routes import router


def create_app(services: Services | None = None) -> FastAPI:
    app = FastAPI(title="Hope Grant Operations Pillar", version="0.1.0")
    app.state.services = services or Services.from_settings()
    app.include_router(router)
    return app


app = create_app()
