"""Environment configuration shared by every service (prefix HOPE_)."""

from __future__ import annotations

from functools import lru_cache

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


@lru_cache
def get_settings() -> HopeSettings:
    return HopeSettings()
