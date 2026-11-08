"""`seed()`: the demo profile (Riverbend Community Health Alliance), saved once."""

from __future__ import annotations

import json
import os
from pathlib import Path

from hope_core.db import connect
from hope_core.settings import get_settings

from hope_profile.api import _PILLAR
from hope_profile.onboarding import ProfileForm, form_to_profile
from hope_profile.repository import ProfileNotFoundError, ProfileRepository

DEMO_ACTOR = "demo@hope.org"
DEMO_FORM = (
    Path(__file__).resolve().parents[4] / "contracts/mocks/w2/profile.put/request.json"
)  # the one copy of the demo form


def seed(form_path: Path = DEMO_FORM) -> bool:
    """Save the demo form unless the agency already has a profile or `HOPE_DEMO_FRESH=1`."""
    if os.environ.get("HOPE_DEMO_FRESH") == "1":
        return False
    settings = get_settings()
    with connect() as conn:
        repo = ProfileRepository(conn, _PILLAR)
        try:
            repo.current(settings.tenant_id, settings.agency_id)
            return False
        except ProfileNotFoundError:
            pass
        form = ProfileForm.model_validate(json.loads(form_path.read_text(encoding="utf-8")))
        data = form_to_profile(form, None, settings)
        repo.save_direct(settings.tenant_id, settings.agency_id, data, DEMO_ACTOR, 0)
    return True
