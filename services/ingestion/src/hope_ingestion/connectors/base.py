"""Connector SDK contract (blueprint 6.1)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from hope_core.money import Money
from hope_core.schemas.common import Contract
from hope_core.schemas.grant_opportunity import SourceSystem
from pydantic import Field

from hope_ingestion.http import RateLimitPolicy, RetryPolicy


class Cursor(Contract):
    """Resume point for incremental discovery. Persisted in `connector_cursors`."""

    position: int = 0
    etag: str | None = None
    updated_since: datetime | None = None


class SavedSearch(Contract):
    keywords: list[str] = []
    aln: list[str] = []
    agencies: list[str] = []
    eligibilities: list[str] = []
    statuses: list[Literal["forecasted", "posted", "closed", "archived"]] = ["forecasted", "posted"]
    page_size: int = Field(25, ge=1, le=1000)
    max_records: int | None = None


class ArtifactRef(Contract):
    url: str
    filename: str | None = None
    media_type: str | None = None
    description: str | None = None


class RawRecord(Contract):
    source_system: SourceSystem
    source_id: str
    revision: int = 0
    url: str | None = None
    metadata: dict[str, Any] = {}
    cursor: Cursor = Cursor()


class ConnectorHealth(Contract):
    source_system: SourceSystem
    ok: bool
    configured: bool = True
    detail: str | None = None


@runtime_checkable
class SourceConnector(Protocol):
    source_system: SourceSystem
    rate_limit: RateLimitPolicy
    retry: RetryPolicy

    def discover(self, cursor: Cursor, query: SavedSearch) -> Iterator[RawRecord]: ...

    def fetch_artifacts(self, record: RawRecord) -> list[ArtifactRef]: ...

    def download(self, ref: ArtifactRef) -> bytes: ...

    def facts(self, record: RawRecord) -> SourceFacts | None: ...

    def health(self) -> ConnectorHealth: ...


class SourceFacts(Contract):
    """Structured metadata a source API states directly. Parsed by code, never by a model, and
    used to enrich or cross-check what A2 extracts from the documents (blueprint 8.5)."""

    title: str | None = None
    funder_name: str | None = None
    funder_type: Literal[
        "federal",
        "state",
        "local",
        "private_foundation",
        "community_foundation",
        "corporate",
        "other",
    ] = "other"
    funder_timezone: str | None = None
    aln: list[str] = []
    contact_email: str | None = None
    summary: str | None = None
    application_due: datetime | None = None
    application_due_has_time: bool = False
    award_ceiling: Money | None = None
    award_floor: Money | None = None
    total_program_funding: Money | None = None
    expected_awards: int | None = None
    cost_share_required: bool | None = None
    applicant_types: list[str] = []
    quotes: dict[str, str] = Field(default_factory=dict, description="field -> verbatim source")
