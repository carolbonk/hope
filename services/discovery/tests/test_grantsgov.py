from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from hope_core.web import FetchError, SearchResult
from hope_discovery.grantsgov import DETAIL, GrantsGovWeb, keywords, opportunity_id
from hope_discovery.mock import ORAL, ScriptedWeb
from hope_discovery.settings import DiscoverySettings

FIXTURES = Path(__file__).parent / "fixtures" / "grantsgov"
OPP = DETAIL + "358864"


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return data


class Api:
    """Grants.gov `search2` / `fetchOpportunity` from fixtures; records each request body."""

    def __init__(self, status: int = 200, search: dict[str, Any] | None = None) -> None:
        self.status = status
        self.search = _load("search.json") if search is None else search
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append((request.url.path, body))
        if self.status != 200:
            return httpx.Response(self.status)
        if request.url.path.endswith("/search2"):
            return httpx.Response(200, json=self.search | {"token": "secret-token"})
        if body["opportunityId"] == 358864:
            return httpx.Response(200, json=_load("opportunity.json"))
        return httpx.Response(200, json={"errorcode": 0, "data": {"forecast": {}}})


def _web(api: Api, base: Any = None, **settings: Any) -> GrantsGovWeb:
    return GrantsGovWeb(
        base or ScriptedWeb(hits=[]),
        DiscoverySettings(**settings),
        transport=httpx.MockTransport(api),
    )


def test_keywords_keep_the_topic() -> None:
    assert keywords("rural oral health grants Washington 2027") == "rural oral health Washington"
    assert keywords("grant funding for nonprofits") == ""


def test_opportunity_id_only_for_notice_urls() -> None:
    assert opportunity_id("https://grants.gov/search-results-detail/358864") == "358864"
    assert opportunity_id(OPP + "/") == "358864"
    assert opportunity_id("https://grants.gov/search-results-detail/358864?x=1") is None
    assert opportunity_id("https://evil.example/search-results-detail/1") is None


def test_search_puts_posted_nonprofit_notices_before_web_hits() -> None:
    api = Api()
    web = _web(api, ScriptedWeb(hits=[ORAL]))
    hits = web.search("rural oral health grants 2027")
    assert [h.url for h in hits] == [OPP, DETAIL + "357524", ORAL]
    path, body = api.calls[0]
    assert path == "/v1/api/search2"
    assert body == {
        "keyword": "rural oral health",
        "oppStatuses": "posted",
        "eligibilities": "12|13|25|99",
        "fundingInstruments": "G|CA",
        "rows": 2,
    }
    assert "secret-token" not in repr(hits)


def test_search_respects_the_run_cap_and_off_switch() -> None:
    api = Api()
    web = _web(api, grantsgov_per_query=2, grantsgov_max=3)
    assert len(web.search("oral health")) == 2
    assert len(web.search("dental care")) == 1
    assert web.search("mobile clinics") == []
    assert len(api.calls) == 2
    off = Api()
    assert _web(off, grantsgov_max=0).search("oral health") == []
    assert off.calls == []


@pytest.mark.parametrize(
    "api", [Api(status=503), Api(search={"errorcode": 1, "msg": "bad"}), Api(search={})]
)
def test_search_ignores_a_grants_gov_failure(api: Api) -> None:
    assert [h.url for h in _web(api, ScriptedWeb(hits=[ORAL])).search("oral health")] == [ORAL]


def test_search_survives_a_web_failure_when_grants_gov_answers() -> None:
    web = _web(Api(), ScriptedWeb(fail_all=True))
    assert [h.url for h in web.search("oral health")][:1] == [OPP]
    with pytest.raises(RuntimeError):
        _web(Api(status=503), ScriptedWeb(fail_all=True)).search("oral health")


def test_fetch_renders_the_notice_as_labelled_lines() -> None:
    page = _web(Api()).fetch(OPP)
    assert page.url == page.final_url == OPP
    assert page.title.endswith("| Grants.gov")
    lines = page.text.splitlines()
    assert lines[1] == "Funder: National Institutes of Health."
    assert "Awards: up to $300,000 per award." in lines
    assert "Deadline: Applications due November 16, 2028." in lines
    assert "<" not in page.text


def test_fetch_passes_other_urls_to_the_web_and_refuses_forecasts() -> None:
    base = ScriptedWeb()
    web = _web(Api(), base)
    assert web.fetch(ORAL).url == ORAL and base.fetched == [ORAL]
    with pytest.raises(FetchError) as forecast:
        web.fetch(DETAIL + "1")
    assert forecast.value.code == "unsupported_content_type"
    with pytest.raises(FetchError) as down:
        _web(Api(status=500)).fetch(OPP)
    assert down.value.code == "network"


def test_agent_saves_a_grants_gov_notice_with_code_parsed_facts(run_agent: Any) -> None:
    web = GrantsGovWeb(
        ScriptedWeb(hits=[]),
        DiscoverySettings(grantsgov_max=1),
        transport=httpx.MockTransport(Api()),
    )
    repo, _ = run_agent(web=web)
    grant = repo.candidates["https://grants.gov/search-results-detail/358864"]
    assert grant.amount_max is not None and grant.amount_max.amount_minor == 30_000_000
    assert grant.deadline == date(2028, 11, 16)
    assert grant.funder == "National Institutes of Health"


def test_search_result_shape() -> None:
    (hit, *_) = _web(Api()).search("oral health")
    assert isinstance(hit, SearchResult) and hit.title.startswith("Community-Based")
