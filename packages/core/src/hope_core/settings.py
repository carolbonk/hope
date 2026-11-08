"""Environment configuration shared by every service (prefix HOPE_)."""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict


class HopeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HOPE_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://hope_app:hope_app@localhost:5432/hope"
    database_system_url: str = "postgresql://hope_system:hope_system@localhost:5432/hope"
    database_admin_url: str = "postgresql://hope:hope@localhost:5432/hope"
    kafka_bootstrap: str = "localhost:19092"
    redis_url: str = "redis://localhost:6379/0"
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "hope-artifacts"
    s3_access_key: str = "hope"
    s3_secret_key: str = "hopehope"
    model_provider: str = "mock"

    # Hackathon (H0): one tenant and one agency, chosen by configuration only.
    tenant_id: UUID = UUID("00000000-0000-4000-8000-000000000001")
    agency_id: UUID = UUID("2c3d4e5f-6a7b-4c8d-9e0f-a1b2c3d4e5f6")
    session_secret: str = "dev-only-session-secret-change-me"
    invite_code: str | None = None
    cookie_secure: bool = True
    web_origin: str = "http://localhost:3000"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_search_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"
    jobs_inline: bool = False


@lru_cache
def get_settings() -> HopeSettings:
    return HopeSettings()
