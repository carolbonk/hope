from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from hope_pillar.api import ROUTERS, app

SNAPSHOTS = Path(__file__).parent / "snapshots" / "openapi"


@pytest.mark.parametrize("name", sorted(ROUTERS))
def test_router_snapshots(name: str) -> None:
    single = FastAPI(title=f"Hope API: {name}", version="0.1.0")
    single.include_router(ROUTERS[name])
    current = json.dumps(single.openapi(), indent=2, sort_keys=True) + "\n"
    path = SNAPSHOTS / f"{name}.json"
    if os.environ.get("UPDATE_SNAPSHOTS"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(current)
    assert current == path.read_text(), "run UPDATE_SNAPSHOTS=1 uv run pytest to refresh"


def test_all_routers_mounted_and_legacy_routes_unmounted() -> None:
    paths = set(app.openapi()["paths"])
    assert {"/v1/auth/signup", "/v1/auth/login", "/v1/auth/logout", "/v1/me"} <= paths
    assert any(p.startswith("/v1/agencies") for p in paths), "profile router is mounted under /v1"
    assert not any(p.startswith(("/v1/opportunities", "/v1/packages", "/v1/hitl")) for p in paths)
