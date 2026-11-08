"""`GET /v1/me`: who is signed in, and whether onboarding is complete (decided by code)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from hope_core import store
from hope_core.auth import Principal, get_principal
from hope_core.db import connect, tenant_tx
from hope_core.schemas import AgencyProfile, MeView
from hope_core.settings import get_settings

router = APIRouter(prefix="/v1", tags=["me"])


def onboarding_complete(profile: AgencyProfile | None) -> bool:
    return bool(profile and profile.mission.mission_statement.strip() and profile.programs)


@router.get("/me")
def me(principal: Annotated[Principal, Depends(get_principal)]) -> MeView:
    settings = get_settings()
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        profile = store.get_profile(tx, settings.agency_id)
    return MeView(
        user_id=principal.user_id,
        email=principal.email,
        display_name=principal.display_name,
        agency_id=settings.agency_id,
        onboarding_complete=onboarding_complete(profile),
    )
