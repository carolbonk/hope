from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from hope_core.settings import HopeSettings
from hope_core.web import RealWebTools, parse_search_response

FIXTURES = Path(__file__).parent / "fixtures" / "openai"
GRANT = "https://cascadecf.example.org/grants/rural-health-access-fund"


def raw() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "web_search_response.json").read_text())
    return data


def test_keeps_http_citations_dedupes_and_drops_fragments() -> None:
    results = parse_search_response(raw(), 8)
    assert [r.url for r in results] == [
        GRANT,
        "https://ncwhealthfoundation.example.org/community-mental-health-grants",
        "https://wafamilyhealth.example.org/grants/clinic-capacity",
    ]
    assert results[0].title == "Rural Health Access Fund"
    assert results[0].snippet == "The Rural Health Access Fund supports rural clinics."


def test_title_falls_back_to_domain() -> None:
    assert parse_search_response(raw(), 8)[1].title == "ncwhealthfoundation.example.org"


def test_caps_at_max_results() -> None:
    assert len(parse_search_response(raw(), 2)) == 2


def test_ignores_prose_and_non_message_items() -> None:
    prose_only = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "https://evil.example.org"}],
            }
        ]
    }
    assert parse_search_response(prose_only, 8) == []
    assert parse_search_response({"output": [{"type": "web_search_call"}]}, 8) == []
    assert parse_search_response({}, 8) == []


def test_snippet_is_capped() -> None:
    text = "x" * 1000
    note = {
        "type": "url_citation",
        "url": "https://a.example.org",
        "title": "A",
        "start_index": 0,
        "end_index": 1000,
    }
    data = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": text, "annotations": [note]}],
            }
        ]
    }
    assert len(parse_search_response(data, 8)[0].snippet) == 300


def test_real_search_request_and_validation() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.url.path == "/v1/responses"
        return httpx.Response(200, json=raw())

    tools = RealWebTools(
        HopeSettings(openai_api_key="sk-test"), openai_transport=httpx.MockTransport(handler)
    )
    assert len(tools.search("  rural clinic grants  ", 2)) == 2
    assert seen[0]["tools"] == [{"type": "web_search"}]
    assert seen[0]["input"] == "Find web pages for: rural clinic grants"
    with pytest.raises(ValueError):
        tools.search("   ")
    with pytest.raises(ValueError):
        tools.search("x" * 201)
    with pytest.raises(ValueError):
        tools.search("grants", 11)
