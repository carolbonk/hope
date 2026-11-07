"""SAM.gov Entity Management API (v3) registration check (blueprint 6.1).

API reference: https://open.gsa.gov/api/entity-api/. Needs `HOPE_SAM_API_KEY`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from hope_ingestion.connectors.base import ConnectorHealth
from hope_ingestion.contracts import EXPIRY_WARNING_DAYS, EntityRegistrationCheck
from hope_ingestion.http import PoliteClient, RateLimitPolicy, RetryPolicy
from hope_ingestion.settings import IngestionSettings


class SamNotConfiguredError(RuntimeError):
    pass


def _date(value: Any) -> date | None:
    return date.fromisoformat(str(value)) if value else None


def registration_check(uei: str, payload: dict[str, Any], today: date) -> EntityRegistrationCheck:
    entities: list[dict[str, Any]] = payload.get("entityData") or []
    if not entities:
        return EntityRegistrationCheck(uei=uei, found=False, active=False, blocks_federal=True)
    reg: dict[str, Any] = entities[0].get("entityRegistration") or {}
    expires = _date(reg.get("registrationExpirationDate"))
    days_left = (expires - today).days if expires else None
    status = str(reg.get("registrationStatus") or "")
    excluded = str(reg.get("exclusionStatusFlag") or "").upper() in ("D", "Y")
    active = status == "Active" and (days_left is None or days_left >= 0)
    return EntityRegistrationCheck(
        uei=uei,
        found=True,
        legal_business_name=reg.get("legalBusinessName"),
        registration_status=status or None,
        registration_expiration_date=expires,
        days_until_expiry=days_left,
        expiry_warning_days=next(
            (
                d
                for d in sorted(EXPIRY_WARNING_DAYS)
                if days_left is not None and 0 <= days_left <= d
            ),
            None,
        ),
        exclusion_flagged=excluded,
        active=active,
        blocks_federal=not active or excluded,
    )


class SamGovClient:
    source_system = "sam_gov"

    def __init__(
        self,
        client: httpx.Client | None = None,
        settings: IngestionSettings | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        self.settings = settings or IngestionSettings()
        self.rate_limit = RateLimitPolicy(rate_per_sec=self.settings.sam_rate_per_sec)
        self.http = PoliteClient(
            client or httpx.Client(timeout=30.0), self.rate_limit, retry or RetryPolicy()
        )

    @property
    def configured(self) -> bool:
        return bool(self.settings.sam_api_key)

    def check_entity(self, uei: str, today: date | None = None) -> EntityRegistrationCheck:
        if not self.settings.sam_api_key:
            raise SamNotConfiguredError("set HOPE_SAM_API_KEY to check SAM.gov registrations")
        response = self.http.request(
            "GET",
            f"{self.settings.sam_base_url}/entity-information/v3/entities",
            params={"ueiSAM": uei, "includeSections": "entityRegistration"},
            headers={"X-Api-Key": self.settings.sam_api_key, "Accept": "application/json"},
        )
        return registration_check(uei, response.json(), today or date.today())

    def health(self) -> ConnectorHealth:
        if not self.configured:
            return ConnectorHealth(
                source_system="sam_gov", ok=False, configured=False, detail="no HOPE_SAM_API_KEY"
            )
        return ConnectorHealth(source_system="sam_gov", ok=True)
