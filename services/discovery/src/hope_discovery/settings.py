"""Discovery limits (`HOPE_DISCOVERY_*`)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DiscoverySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HOPE_DISCOVERY_", env_file=".env", extra="ignore")

    min_queries: int = 5
    max_queries: int = 8
    results_per_query: int = 8
    max_candidate_urls: int = 30
    max_detail_fetches_per_page: int = 1
    max_detail_fetches: int = 15
    page_chars_to_llm: int = 12_000
    max_llm_calls: int = 90
    max_tokens: int = 450_000
    job_timeout_s: int = 300
    fetch_concurrency: int = 4
    known_url_days: int = 7
    min_classify_confidence: float = 0.6
    daily_limit: int = 20
    tz: str = "America/New_York"


@lru_cache
def get_discovery_settings() -> DiscoverySettings:
    return DiscoverySettings()
