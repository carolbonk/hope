"""Grants.gov public REST connector: `search2` for discovery, `fetchOpportunity` for detail.

API reference: https://www.grants.gov/api/common/search2 and
https://www.grants.gov/api/common/fetchopportunity (no authentication required).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from hope_core.money import Money
from hope_core.schemas.grant_opportunity import SourceSystem

from hope_ingestion.connectors.base import (
    ArtifactRef,
    ConnectorHealth,
    Cursor,
    RawRecord,
    SavedSearch,
    SourceFacts,
)
from hope_ingestion.http import PoliteClient, RateLimitPolicy, RetryPolicy
from hope_ingestion.settings import IngestionSettings

GRANTS_GOV_TZ = "America/New_York"
DETAIL_URL = "https://www.grants.gov/search-results-detail/{id}"
DOCUMENT_SUFFIXES = (".pdf", ".docx", ".doc", ".html", ".htm", ".xml", ".txt")


class GrantsGovError(RuntimeError):
    pass


def _join(values: list[str]) -> str:
    return "|".join(values)


def _money(value: Any) -> Money | None:
    """Grants.gov sends amounts as digit strings and uses "0" or "" for unspecified."""
    text = str(value or "").replace(",", "").strip()
    if not re.fullmatch(r"\d+(\.\d{1,2})?", text) or float(text) == 0:
        return None
    return Money.from_decimal(text)


def _due_date(synopsis: dict[str, Any]) -> datetime | None:
    raw = synopsis.get("responseDateStr")
    if not raw:
        return None
    parsed = datetime.strptime(str(raw), "%Y-%m-%d-%H-%M-%S")
    return parsed.replace(tzinfo=ZoneInfo(GRANTS_GOV_TZ))


def facts_from_detail(detail: dict[str, Any]) -> SourceFacts:
    synopsis: dict[str, Any] = detail.get("synopsis") or {}
    alns = detail.get("cfdas") or detail.get("alns") or []
    agency = synopsis.get("agencyName") or (detail.get("agencyDetails") or {}).get("agencyName")
    quotes = {
        key: f"{key}: {synopsis[key]}"
        for key in ("responseDate", "awardCeiling", "awardFloor", "estimatedFunding")
        if synopsis.get(key) not in (None, "")
    }
    due = _due_date(synopsis)
    awards = str(synopsis.get("numberOfAwards") or "")
    return SourceFacts(
        title=detail.get("opportunityTitle"),
        funder_name=str(agency).strip() if agency else None,
        funder_type="federal",
        funder_timezone=GRANTS_GOV_TZ,
        aln=[str(a.get("cfdaNumber") or a.get("alnNumber")) for a in alns],
        contact_email=synopsis.get("agencyContactEmail") or None,
        summary=synopsis.get("synopsisDesc"),
        application_due=due,
        application_due_has_time=bool(due and (due.hour, due.minute) != (0, 0)),
        award_ceiling=_money(synopsis.get("awardCeiling")),
        award_floor=_money(synopsis.get("awardFloor")),
        total_program_funding=_money(synopsis.get("estimatedFunding")),
        expected_awards=int(awards) if awards.isdigit() else None,
        cost_share_required=synopsis.get("costSharing"),
        applicant_types=[str(t["description"]) for t in synopsis.get("applicantTypes") or []],
        quotes=quotes,
    )


class GrantsGovConnector:
    source_system: SourceSystem = "grants_gov"

    def __init__(
        self,
        client: httpx.Client | None = None,
        settings: IngestionSettings | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        self.settings = settings or IngestionSettings()
        self.rate_limit = RateLimitPolicy(rate_per_sec=self.settings.grants_gov_rate_per_sec)
        self.retry = retry or RetryPolicy()
        self.http = PoliteClient(
            client or httpx.Client(timeout=30.0, follow_redirects=True),
            self.rate_limit,
            self.retry,
        )

    def _post(self, operation: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.settings.grants_gov_base_url}/v1/api/{operation}"
        payload: dict[str, Any] = self.http.request("POST", url, json=body).json()
        if payload.get("errorcode", 0) != 0:
            raise GrantsGovError(f"{operation}: {payload.get('msg')}")
        data: dict[str, Any] = payload.get("data") or {}
        return data

    def search(self, query: SavedSearch, start: int = 0, rows: int | None = None) -> dict[str, Any]:
        return self._post(
            "search2",
            {
                "rows": rows or query.page_size,
                "startRecordNum": start,
                "keyword": " ".join(query.keywords),
                "oppStatuses": _join(list(query.statuses)),
                "aln": _join(query.aln),
                "agencies": _join(query.agencies),
                "eligibilities": _join(query.eligibilities),
            },
        )

    def fetch_opportunity(self, opportunity_id: int | str) -> dict[str, Any]:
        return self._post("fetchOpportunity", {"opportunityId": int(opportunity_id)})

    def discover(self, cursor: Cursor, query: SavedSearch) -> Iterator[RawRecord]:
        start, seen = cursor.position, 0
        while True:
            page = self.search(query, start)
            hits: list[dict[str, Any]] = page.get("oppHits") or []
            for hit in hits:
                detail = self.fetch_opportunity(hit["id"])
                start += 1
                seen += 1
                yield RawRecord(
                    source_system="grants_gov",
                    source_id=str(hit["number"]),
                    revision=int(detail.get("revision") or 0),
                    url=DETAIL_URL.format(id=hit["id"]),
                    metadata=detail,
                    cursor=Cursor(position=start),
                )
                if query.max_records is not None and seen >= query.max_records:
                    return
            if not hits or start >= int(page.get("hitCount") or 0):
                return

    def fetch_artifacts(self, record: RawRecord) -> list[ArtifactRef]:
        refs: list[ArtifactRef] = []
        for folder in record.metadata.get("synopsisAttachmentFolders") or []:
            for att in folder.get("synopsisAttachments") or []:
                refs.append(
                    ArtifactRef(
                        url=self.settings.grants_gov_attachment_url.format(attachment_id=att["id"]),
                        filename=att.get("fileName"),
                        media_type=att.get("mimeType"),
                        description=folder.get("folderType"),
                    )
                )
        link = (record.metadata.get("synopsis") or {}).get("fundingDescLinkUrl")
        if link and str(link).lower().endswith(DOCUMENT_SUFFIXES):
            refs.append(ArtifactRef(url=str(link), description="Full Announcement"))
        return refs

    def facts(self, record: RawRecord) -> SourceFacts:
        return facts_from_detail(record.metadata)

    def download(self, ref: ArtifactRef) -> bytes:
        return self.http.request("GET", ref.url).content

    def health(self) -> ConnectorHealth:
        try:
            self.search(SavedSearch(), rows=1)
        except Exception as exc:
            return ConnectorHealth(source_system="grants_gov", ok=False, detail=str(exc))
        return ConnectorHealth(source_system="grants_gov", ok=True)
