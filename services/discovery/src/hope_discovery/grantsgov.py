"""Grants.gov as a second source for federal grants (H2 step 3).

Federal agency sites often refuse automated clients (bot protection), so their notices never reached
discovery. Grants.gov publishes the same notices through a public API (no key):
`POST https://api.grants.gov/v1/api/search2` and `.../fetchOpportunity`. `GrantsGovWeb` wraps the
normal `WebTools`: each search also asks Grants.gov for posted notices open to nonprofits (listed
first), and fetching a Grants.gov notice URL renders the API record as a plain `Label: value.` page.
The rest of the pipeline (extract, quote checks, code-parsed amount and deadline, fit) is unchanged.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import date
from typing import Any

import httpx
from hope_core.web import FetchError, Page, SearchResult, WebTools

from hope_discovery.settings import DiscoverySettings, get_discovery_settings

log = logging.getLogger(__name__)

API = "https://api.grants.gov/v1/api"
DETAIL = "https://www.grants.gov/search-results-detail/"
_DETAIL_RX = re.compile(r"^https://(?:www\.)?grants\.gov/search-results-detail/(\d{1,9})$")
NONPROFIT_ELIGIBILITY = "12|13|25|99"  # 501(c)(3), other nonprofits, others, unrestricted
INSTRUMENTS = "G|CA"  # grants and cooperative agreements
_FILLER = re.compile(
    r"\b(?:grants?|funding|funds?|nonprofits?|non-profit|organizations?|opportunit(?:y|ies)"
    r"|apply|applications?|open|for|in|and|the|of|to|20\d\d)\b",
    re.I,
)
_TAGS = re.compile(r"<[^>]+>")
TIMEOUT = 15.0


def keywords(query: str) -> str:
    """The topic words of a web query (`rural oral health grants 2027` → `rural oral health`)."""
    return " ".join(_FILLER.sub(" ", query).split())[:100]


def opportunity_id(url: str) -> str | None:
    m = _DETAIL_RX.match(url.rstrip("/"))
    return m.group(1) if m else None


def _plain(text: str) -> str:
    return " ".join(html.unescape(_TAGS.sub(" ", text)).split())


def _amount(value: Any) -> int:
    return int(value) if str(value or "").isdigit() else 0


def _response_date(synopsis: dict[str, Any]) -> date | None:
    raw = str(synopsis.get("responseDateStr") or "")  # "2028-11-16-00-00-00"
    try:
        return date(int(raw[:4]), int(raw[5:7]), int(raw[8:10]))
    except ValueError:
        return None


def render(record: dict[str, Any], url: str) -> Page:
    """A Grants.gov notice as page text. Only the API's own facts, one `Label: value.` per line."""
    syn = record.get("synopsis") or {}
    title = _plain(str(record.get("opportunityTitle") or "")).rstrip(".")
    number = str(record.get("opportunityNumber") or "")
    lines = [f"{title}.", f"Funder: {_plain(str(syn.get('agencyName') or 'Federal agency'))}."]
    lines.append(f"Grants.gov opportunity number: {number}." if number else "")
    if summary := _plain(str(syn.get("synopsisDesc") or ""))[:1500].rstrip("."):
        lines.append(f"Summary: {summary}.")
    ceiling, floor = _amount(syn.get("awardCeiling")), _amount(syn.get("awardFloor"))
    if ceiling and floor:
        lines.append(f"Awards: ${floor:,} to ${ceiling:,} per award.")
    elif ceiling:
        lines.append(f"Awards: up to ${ceiling:,} per award.")
    if due := _response_date(syn):
        lines.append(f"Deadline: Applications due {due:%B} {due.day}, {due.year}.")
    types = [
        _plain(str(t.get("description") or ""))
        for t in syn.get("applicantTypes") or []
        if isinstance(t, dict)
    ]
    if types:
        lines.append(f"Eligible applicants: {'; '.join(t for t in types if t)}.")
    if desc := _plain(str(syn.get("applicantEligibilityDesc") or ""))[:600].rstrip("."):
        lines.append(f"Eligibility: {desc}.")
    lines.append("How to apply: read the full notice and apply through the Grants.gov application.")
    return Page(
        url=url,
        final_url=url,
        title=f"{title} | Grants.gov",
        text="\n".join(line for line in lines if line),
        content_type="application/json",
    )


class GrantsGovWeb:
    """`WebTools` plus Grants.gov: federal notices added to each search and read from the API."""

    def __init__(
        self,
        web: WebTools,
        settings: DiscoverySettings | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.web = web
        self.s = settings or get_discovery_settings()
        self._client = httpx.Client(base_url=API, timeout=TIMEOUT, transport=transport)
        self._added = 0

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(path, json=body)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("errorcode") != 0:
            raise ValueError("grants.gov error")
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def _federal(self, query: str) -> list[SearchResult]:
        room = min(self.s.grantsgov_per_query, self.s.grantsgov_max - self._added)
        words = keywords(query)
        if room <= 0 or not words:
            return []
        try:
            data = self._post(
                "/search2",
                {
                    "keyword": words,
                    "oppStatuses": "posted",
                    "eligibilities": NONPROFIT_ELIGIBILITY,
                    "fundingInstruments": INSTRUMENTS,
                    "rows": room,
                },
            )
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("grants.gov search failed (%s)", type(exc).__name__)
            return []
        hits = [
            SearchResult(url=DETAIL + str(h["id"]), title=str(h.get("title") or ""), snippet="")
            for h in data.get("oppHits") or []
            if isinstance(h, dict) and str(h.get("id", "")).isdigit()
        ][:room]
        self._added += len(hits)
        return hits

    def search(self, query: str, max_results: int = 8) -> list[SearchResult]:
        federal = self._federal(query)
        try:
            hits = self.web.search(query, max_results)
        except Exception:
            if not federal:
                raise
            hits = []
        return federal + hits  # first, so the candidate cap can't push them out

    def fetch(self, url: str) -> Page:
        opp = opportunity_id(url)
        if opp is None:
            return self.web.fetch(url)
        try:
            record = self._post("/fetchOpportunity", {"opportunityId": int(opp)})
        except httpx.HTTPError as exc:
            raise FetchError("network", type(exc).__name__) from exc
        except ValueError as exc:
            raise FetchError("http_404", url) from exc
        if not record.get("synopsis"):
            raise FetchError("unsupported_content_type", "grants.gov forecast")
        return render(record, url)
