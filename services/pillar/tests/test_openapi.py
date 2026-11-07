from __future__ import annotations

import json
import os
from pathlib import Path

from hope_pillar.api import app

SNAPSHOT = Path(__file__).parent / "snapshots" / "openapi.json"


def test_openapi_snapshot() -> None:
    current = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_SNAPSHOTS"):
        SNAPSHOT.write_text(current)
    assert current == SNAPSHOT.read_text(), "run UPDATE_SNAPSHOTS=1 uv run pytest to refresh"
