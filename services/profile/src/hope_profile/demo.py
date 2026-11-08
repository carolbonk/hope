"""Demo seed for the profile, called first by `hope-demo-seed`. Idempotent: it does nothing once
the agency has a version, and nothing with `HOPE_DEMO_FRESH=1` (so onboarding can be shown).
The demo form is the W2 contract mock, so there is one copy of it."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from hope_core.db import connect
from hope_core.settings import get_settings

from hope_profile.api import get_pillar
from hope_profile.onboarding import ProfileForm, form_to_profile
from hope_profile.repository import ProfileRepository, ProfileVersion

DEMO_ACTOR = "demo@hope.org"
_MOCK = Path("contracts/mocks/w2/profile.put/request.json")


def demo_form_path() -> Path:
    for root in (Path.cwd(), *Path(__file__).resolve().parents):
        if (root / _MOCK).is_file():
            return root / _MOCK
    raise FileNotFoundError(_MOCK)


def demo_form() -> ProfileForm:
    return ProfileForm.model_validate(json.loads(demo_form_path().read_text()))


def seed() -> ProfileVersion | None:
    """The created version, or None when skipped or already seeded."""
    if os.environ.get("HOPE_DEMO_FRESH") == "1":
        return None
    settings = get_settings()
    with connect() as conn:
        repo = ProfileRepository(conn, get_pillar())
        if repo.latest(settings.tenant_id, settings.agency_id) is not None:
            return None
        data = form_to_profile(
            demo_form(),
            None,
            tenant_id=settings.tenant_id,
            agency_id=settings.agency_id,
            now=datetime.now(UTC),
        )
        return repo.save_direct(settings.tenant_id, settings.agency_id, data, DEMO_ACTOR, None)
