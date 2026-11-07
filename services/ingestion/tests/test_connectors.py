from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from hope_core.money import Money
from hope_ingestion.connectors import Cursor, SavedSearch, SourceConnector
from hope_ingestion.connectors.grants_gov import GrantsGovConnector, GrantsGovError
from hope_ingestion.connectors.sam_gov import SamGovClient, SamNotConfiguredError
from hope_ingestion.http import RetryPolicy
from hope_ingestion.settings import IngestionSettings

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return data


SEARCH = load_fixture("grants_gov/search2_youth_mentoring.json")
DETAIL = load_fixture("grants_gov/fetch_opportunity_364058.json")


def grants_gov(requests: list[dict[str, Any]]) -> GrantsGovConnector:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append({"path": request.url.path, **body})
        if request.url.path.endswith("/search2"):
            start = body["startRecordNum"]
            page = dict(SEARCH)
            page["data"] = dict(SEARCH["data"], hitCount=3)
            page["data"]["oppHits"] = SEARCH["data"]["oppHits"][start : start + body["rows"]]
            return httpx.Response(200, json=page)
        detail = json.loads(json.dumps(DETAIL))
        detail["data"]["id"] = body["opportunityId"]
        return httpx.Response(200, json=detail)

    return GrantsGovConnector(
        httpx.Client(transport=httpx.MockTransport(handler)),
        IngestionSettings(grants_gov_rate_per_sec=1000),
        RetryPolicy(max_attempts=1),
    )


def test_grants_gov_is_a_source_connector() -> None:
    assert isinstance(grants_gov([]), SourceConnector)


def test_discover_paginates_search2_and_fetches_detail() -> None:
    requests: list[dict[str, Any]] = []
    connector = grants_gov(requests)
    query = SavedSearch(keywords=["youth", "mentoring"], aln=["16.726"], page_size=2)
    records = list(connector.discover(Cursor(), query))
    assert [r.source_id for r in records] == [h["number"] for h in SEARCH["data"]["oppHits"]]
    assert records[-1].cursor.position == 3
    searches = [r for r in requests if r["path"].endswith("/search2")]
    assert [s["startRecordNum"] for s in searches] == [0, 2]
    assert searches[0]["keyword"] == "youth mentoring"
    assert searches[0]["oppStatuses"] == "forecasted|posted"
    assert searches[0]["aln"] == "16.726"


def test_discover_resumes_from_cursor_and_respects_max_records() -> None:
    requests: list[dict[str, Any]] = []
    records = list(grants_gov(requests).discover(Cursor(position=1), SavedSearch(max_records=1)))
    assert len(records) == 1
    assert requests[0]["startRecordNum"] == 1


def test_facts_from_recorded_detail() -> None:
    connector = grants_gov([])
    record = next(connector.discover(Cursor(), SavedSearch(max_records=1)))
    facts = connector.facts(record)
    assert facts.funder_type == "federal"
    assert facts.aln == ["16.726"]
    assert facts.award_ceiling == Money.from_decimal("2000000")
    assert facts.award_floor is None
    assert facts.total_program_funding == Money.from_decimal("16500000")
    assert facts.expected_awards == 15
    assert facts.application_due is not None
    assert facts.application_due.date() == date(2026, 11, 16)
    assert facts.application_due_has_time is False
    assert facts.cost_share_required is False
    assert "awardCeiling: 2000000" in facts.quotes.values()


def test_fetch_artifacts_lists_attachments_and_full_announcement() -> None:
    connector = grants_gov([])
    record = next(connector.discover(Cursor(), SavedSearch(max_records=1)))
    record.metadata["synopsisAttachmentFolders"] = [
        {
            "folderType": "Full Announcement",
            "synopsisAttachments": [
                {"id": 10190, "fileName": "nofo.pdf", "mimeType": "application/pdf"}
            ],
        }
    ]
    refs = connector.fetch_artifacts(record)
    assert refs[0].url.endswith("/att/download/10190")
    assert refs[0].filename == "nofo.pdf"
    assert refs[1].url == "https://www.ojp.gov/funding/docs/ojjdp-2026-172743.pdf"


def test_grants_gov_error_code_raises() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"errorcode": 1, "msg": "bad"})
        )
    )
    connector = GrantsGovConnector(client, IngestionSettings(grants_gov_rate_per_sec=1000))
    with pytest.raises(GrantsGovError):
        connector.search(SavedSearch())
    assert connector.health().ok is False


def sam(fixture: str, seen: list[httpx.Request]) -> SamGovClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=load_fixture(f"sam_gov/{fixture}"))

    return SamGovClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        IngestionSettings(sam_api_key="test-key", sam_rate_per_sec=1000),
    )


def test_sam_active_registration_with_expiry_warning() -> None:
    seen: list[httpx.Request] = []
    check = sam("entity_active.json", seen).check_entity("RV56IG5JM6G9", today=date(2027, 2, 1))
    assert check.active and not check.blocks_federal
    assert check.legal_business_name == "RIVERBEND YOUTH ALLIANCE"
    assert check.days_until_expiry == 37
    assert check.expiry_warning_days == 60
    assert seen[0].headers["X-Api-Key"] == "test-key"
    assert seen[0].url.params["ueiSAM"] == "RV56IG5JM6G9"
    assert seen[0].url.path == "/entity-information/v3/entities"


def test_sam_expired_and_missing_entities_block_federal() -> None:
    expired = sam("entity_expired.json", []).check_entity("ZQGGHJH74DW7", today=date(2026, 11, 7))
    assert expired.found and not expired.active and expired.blocks_federal
    missing = sam("entity_not_found.json", []).check_entity("NOPE", today=date(2026, 11, 7))
    assert not missing.found and missing.blocks_federal


def test_sam_requires_api_key() -> None:
    client = SamGovClient(settings=IngestionSettings(sam_api_key=None))
    assert client.health().configured is False
    with pytest.raises(SamNotConfiguredError):
        client.check_entity("RV56IG5JM6G9")
