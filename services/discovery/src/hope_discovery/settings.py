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
    min_fit_score: int = 40  # below this a grant is not worth a nonprofit's time
    max_award_budget_ratio: int = 10  # larger "awards" are program totals
    daily_limit: int = 20
    grantsgov_per_query: int = 2  # federal notices added to each web search (Grants.gov API)
    grantsgov_max: int = 6  # per run; 0 turns Grants.gov off
    tz: str = "America/New_York"


@lru_cache
def get_discovery_settings() -> DiscoverySettings:
    return DiscoverySettings()
