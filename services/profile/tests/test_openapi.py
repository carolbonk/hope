from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI
from hope_profile.api import router

SNAPSHOT = Path(__file__).parent / "snapshots" / "openapi.json"


def test_profile_router_snapshot() -> None:
    app = FastAPI(title="Hope API: profile", version="0.1.0")
    app.include_router(router, prefix="/v1")
    current = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_SNAPSHOTS"):
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(current)
    assert current == SNAPSHOT.read_text(), "run UPDATE_SNAPSHOTS=1 uv run pytest to refresh"
