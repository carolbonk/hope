from __future__ import annotations

from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from hope_core.settings import get_settings
from hope_core.testing.factories import agency_profile
from hope_pillar.api.me import onboarding_complete
from psycopg.types.json import Jsonb

INVITE = "test-invite-code-0123456789"  # set by the hope_api fixture

pytestmark = pytest.mark.db


def signed_in(client: TestClient) -> None:
    response = client.post(
        "/v1/auth/signup",
        json={
            "email": "me@riverbend.example.org",
            "password": "long-enough",
            "display_name": "Me",
            "invite_code": INVITE,
        },
    )
    assert response.status_code == 201


def put_profile(admin_url: str, version: int, **overrides: Any) -> None:
    settings = get_settings()
    profile = agency_profile(
        settings.tenant_id, agency_id=settings.agency_id, version=version, **overrides
    )
    with psycopg.connect(admin_url) as conn:
        conn.execute(
            "INSERT INTO agency_profile_versions"
            " (agency_id, tenant_id, version, profile, recorded_by)"
            " VALUES (%s, %s, %s, %s, 'test')",
            (
                settings.agency_id,
                settings.tenant_id,
                version,
                Jsonb(profile.model_dump(mode="json")),
            ),
        )


def test_me_without_profile_is_not_onboarded(hope_api: TestClient) -> None:
    signed_in(hope_api)
    body = hope_api.get("/v1/me").json()
    assert body["agency_id"] == str(get_settings().agency_id)
    assert body["onboarding_complete"] is False
    assert set(body) == {"user_id", "email", "display_name", "agency_id", "onboarding_complete"}


def test_onboarding_needs_mission_and_program(hope_api: TestClient, migrated_db: str) -> None:
    signed_in(hope_api)
    base = agency_profile()
    put_profile(migrated_db, 1, programs=[])
    assert hope_api.get("/v1/me").json()["onboarding_complete"] is False
    put_profile(migrated_db, 2, mission=base.mission.model_copy(update={"mission_statement": "  "}))
    assert hope_api.get("/v1/me").json()["onboarding_complete"] is False
    put_profile(migrated_db, 3)
    assert hope_api.get("/v1/me").json()["onboarding_complete"] is True


def test_onboarding_complete_rule() -> None:
    profile = agency_profile()
    assert profile.programs and profile.mission.mission_statement
    assert onboarding_complete(profile) is True
    assert onboarding_complete(None) is False
    assert onboarding_complete(profile.model_copy(update={"programs": []})) is False
