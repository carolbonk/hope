"""The profile router's OpenAPI (legacy enterprise routes + H1 `/v1/profile`) is pinned."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI
from hope_profile.api import router

SNAPSHOT = Path(__file__).parent / "snapshots" / "openapi.json"


def test_openapi_snapshot() -> None:
    app = FastAPI(title="Hope API: profile", version="0.1.0")
    app.include_router(router, prefix="/v1")
    current = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_SNAPSHOTS"):
        SNAPSHOT.write_text(current)
    assert current == SNAPSHOT.read_text(), "run UPDATE_SNAPSHOTS=1 uv run pytest to refresh"
    paths = json.loads(current)["paths"]
    assert {"/v1/profile", "/v1/profile/ntee-codes", "/v1/profile/ntee-suggestions"} <= set(paths)
    assert set(paths["/v1/profile"]) == {"get", "put", "patch"}
