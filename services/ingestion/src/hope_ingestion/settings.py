"""Ingestion-only settings (prefix HOPE_). Shared settings stay in hope_core.settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HOPE_", env_file=".env", extra="ignore")

    sam_api_key: str | None = None
    sam_base_url: str = "https://api.sam.gov"
    grants_gov_base_url: str = "https://api.grants.gov"
    grants_gov_attachment_url: str = (
        "https://apply07.grants.gov/grantsws/rest/opportunity/att/download/{attachment_id}"
    )
    grants_gov_rate_per_sec: float = 2.0
    sam_rate_per_sec: float = 1.0
