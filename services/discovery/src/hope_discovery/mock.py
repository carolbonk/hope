"""Offline discovery: MockProvider responders, recorded web fixtures and an in-memory repo.

Used by the tests, by the demo seed and whenever no OpenAI key is configured.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from hope_core.model_gateway import Message, MockProvider
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.hackathon import DiscoveryProgress, GrantCandidate, JobStatus
from hope_core.web import Page, RecordedWebTools, SearchResult

from hope_discovery.models import FitAssessment, PageExtraction, QueryPlan
from hope_discovery.requirements import RequirementsExtraction
from hope_discovery.requirements import mock_responder as requirements_mock_responder

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "web"

DEMO_QUERIES = [
    "rural dental care grants Washington 2027",
    "mobile dental clinic funding nonprofit",
    "community health worker grants Washington",
    "youth mental health grants central Washington",
    "farmworker health grants Pacific Northwest",
    "community foundation health grants Chelan County",
]
# Recorded fit scores for the demo pages; any other grant gets a keyword-overlap score.
DEMO_FIT_SCORES = {
    "Rural Oral Health Access Grant 2027": 88,
    "Community Health Worker Training Grants": 71,
    "Mobile Health Equipment Fund": 54,
}

_PAGE = re.compile(r'<untrusted kind="web_page" n="(\d)">\n(.*?)\n</untrusted>', re.S)
_LINK = re.compile(r"^\[(\d+)\] (.*?) -> (\S+)$", re.M)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_DETAIL_LINK = re.compile(r"guideline|eligib|faq|how to apply", re.I)
_WORD = re.compile(r"[a-z]{5,}")


def _user(messages: list[Message]) -> str:
    return next((m.content for m in reversed(messages) if m.role == "user"), "")


def _line(text: str, label: str) -> str:
    m = re.search(rf"^{label}: (.*)$", text, re.M)
    return m.group(1).strip() if m else ""


def plan_responder(messages: list[Message], _schema: dict[str, Any]) -> dict[str, Any]:
    text = _user(messages)
    keywords = _line(text, "Focus keywords").lower()
    location = _line(text, "Location")
    if "dental" in keywords and "chelan" in location.lower():
        queries = DEMO_QUERIES
    else:
        areas = _line(text, r"\[P\d+\] mission\.focus_areas") or keywords
        year = _line(text, "Today")[:4]
        loc = "" if location == "(none)" else location
        queries = [
            " ".join(f"{a.strip()} grants {loc} {year}".split())
            for a in areas.split(",")
            if a.strip() and a.strip() != "(none)"
        ]
    return {
        "queries": [
            {"query": q, "rationale": "Matches the profile", "profile_refs": ["P1"]}
            for q in queries
        ]
    }


def _labelled(text: str, label: str) -> str | None:
    m = re.search(rf"\b{label}: ([^\n]*?)\.(?:\s|$)", text)
    return m.group(1).strip()[:300] if m else None


def extract_responder(messages: list[Message], _schema: dict[str, Any]) -> dict[str, Any]:
    """Keyword rules over the recorded pages' `Label: value.` lines."""
    text = _user(messages)
    pages = {int(n): body for n, body in _PAGE.findall(text)}
    title_line = _line(text, "Title").lower()
    url = _line(text, "URL").lower()
    first = pages.get(1, "")
    both = "\n".join(pages.values())
    low = both.lower()

    def quote(label: str) -> dict[str, Any] | None:
        for n in sorted(pages):
            if value := _labelled(pages[n], label):
                return {"text": value, "page": n}
        return None

    if "news" in title_line or "/news" in url:
        kind = "news_or_blog"
    elif "about" in title_line or "grants we have made" in low:
        kind = "funder_overview"
    elif "applications are closed" in low:
        kind = "closed_or_past"
    elif "grant" in low and ("apply" in low or "application" in low):
        kind = "open_opportunity"
    else:
        kind = "not_relevant"
    head = (_SENTENCE.split(first.strip(), maxsplit=1) or [""])[0].rstrip(".")[:300]
    deadline = quote("Deadline")
    needs_detail, index = False, None
    if kind == "open_opportunity" and deadline is None and len(pages) == 1:
        for n, label, _u in _LINK.findall(text):
            if _DETAIL_LINK.search(label):
                needs_detail, index = True, int(n)
                break
    eligibility = quote("Eligibility")
    return {
        "kind": kind,
        "is_grant_opportunity": kind in ("open_opportunity", "closed_or_past"),
        "confidence": 0.9,
        "title": {"text": head, "page": 1} if len(head) >= 3 else None,
        "funder": quote("Funder"),
        "summary": _labelled(both, "Summary"),
        "amount": quote("Awards"),
        "deadline": deadline,
        "rolling": bool(deadline and "rolling" in deadline["text"].lower()),
        "eligibility": [eligibility] if eligibility else [],
        "eligibility_summary": _labelled(both, "Eligibility"),
        "needs_more_detail": needs_detail,
        "detail_link_index": index,
    }


def fit_responder(messages: list[Message], _schema: dict[str, Any]) -> dict[str, Any]:
    text = _user(messages)
    title = _line(text, "Grant")
    quotes = re.findall(r'^\[(W\d+)\] "(.*)" \(\S+\)$', text, re.M)
    profile = re.findall(r"^\[(P\d+)\] (\S+): (.*)$", text, re.M)
    profile_words = {w for _r, _p, t in profile for w in _WORD.findall(t.lower())}
    quote_words = {w for _r, q in quotes for w in _WORD.findall(q.lower())}
    overlap = len(profile_words & quote_words)
    score = DEMO_FIT_SCORES.get(title, min(95, 40 + 8 * overlap))
    mission = next((r for r, p, _t in profile if p == "mission.mission_statement"), "P1")
    program = next((r for r, p, _t in profile if p.endswith(".description")), mission)
    w_refs = [r for r, _q in quotes]
    reasons = [
        {"text": "Funds the kind of work your programs do", "refs": [*w_refs[-1:], program]},
        {"text": "Fits your mission and the people you serve", "refs": [mission]},
    ]
    concerns = [
        {"text": "Requires an audited financial statement", "refs": [r]}
        for r, q in quotes
        if "audit" in q.lower()
    ]
    blocker = next(
        (
            r
            for r, q in quotes
            if re.search(r"only open to (?:public )?(?:schools|tribal)", q, re.I)
        ),
        None,
    )
    return {
        "fit_score": score,
        "reasons": reasons,
        "concerns": concerns[:3],
        "eligibility_blocker": blocker,
    }


def register(provider: MockProvider) -> MockProvider:
    provider.register(QueryPlan, plan_responder)
    provider.register(PageExtraction, extract_responder)
    provider.register(FitAssessment, fit_responder)
    provider.register(RequirementsExtraction, requirements_mock_responder)
    return provider


def recorded_web(fixture_dir: Path | str = FIXTURES) -> RecordedWebTools:
    return RecordedWebTools(fixture_dir)


# Fixture URLs (tests/fixtures/web).
ORAL = "https://cascadehealth.example.org/grants/rural-oral-health"
INJECT = "https://cascadehealth.example.org/grants/rural-oral-health-print"
CHW = "https://chwcollaborative.example.org/training-grants"
CHW_GUIDELINES = "https://chwcollaborative.example.org/training-grants/guidelines"
MOBILE = "https://ncwmedicalfund.example.org/mobile-equipment"
EXPIRED = "https://wahealth.example.org/mini-grants-2025"
CLOSED = "https://pnwsmiles.example.org/grants/smile-grants"
SCHOOLS = "https://wakids.example.org/grants/school-health"
# Fixture page text that is never quoted, so is never stored or logged.
UNQUOTED = [
    "complete the online application and attach your program budget",
    "Since 1986 we have connected donors",
    "Twelve clinics received grants",
    "the grant committee meets monthly",
]


class ScriptedWeb:
    """The recorded fixtures, with optional failing queries or a fixed first-query hit list."""

    def __init__(
        self, fail: set[str] | None = None, hits: list[str] | None = None, fail_all: bool = False
    ) -> None:
        self.recorded = recorded_web()
        self.fail = fail or set()
        self.hits = hits
        self.fail_all = fail_all
        self.searched: list[str] = []
        self.fetched: list[str] = []

    def search(self, query: str, max_results: int = 8) -> list[SearchResult]:
        self.searched.append(query)
        if self.fail_all or query in self.fail:
            raise RuntimeError("search down")
        if self.hits is not None:
            first = len(self.searched) == 1
            return [SearchResult(url=u, title="", snippet="") for u in self.hits] if first else []
        return self.recorded.search(query, max_results)

    def fetch(self, url: str) -> Page:
        self.fetched.append(url)
        return self.recorded.fetch(url)


class MemoryRepo:
    """`DiscoveryRepo` in memory, for unit tests."""

    def __init__(
        self,
        profile: AgencyProfile | None,
        focus_keywords: list[str] | None = None,
        location: str | None = None,
    ) -> None:
        self.profile = profile
        self.request = (focus_keywords or [], location)
        self.progress_log: list[tuple[DiscoveryProgress, JobStatus]] = []
        self.events: list[dict[str, Any]] = []
        self.queries: list[str] = []
        self.counts: dict[str, int] = {}
        self.candidates: dict[str, GrantCandidate] = {}
        self.known: set[str] = set()

    def load_profile(self) -> AgencyProfile | None:
        return self.profile

    def load_request(self, job_id: UUID) -> tuple[list[str], str | None]:
        return self.request

    def progress(self, job_id: UUID, progress: DiscoveryProgress, status: JobStatus) -> None:
        self.progress_log.append((progress.model_copy(), status))

    def event(self, job_id: UUID, kind: str, text: str, **fields: Any) -> int:
        self.events.append(
            {"seq": len(self.events) + 1, "kind": kind, "text": text[:300], **fields}
        )
        return len(self.events)

    def set_queries(self, job_id: UUID, queries: list[str]) -> None:
        self.queries = list(queries)

    def set_counts(self, job_id: UUID, counts: dict[str, int]) -> None:
        self.counts = dict(counts)

    def known_urls(self, urls: list[str], since: datetime) -> set[str]:
        return self.known & set(urls)

    def url_exists(self, url: str) -> bool:
        return url in self.candidates

    def upsert(self, candidate: GrantCandidate) -> GrantCandidate:
        old = self.candidates.get(candidate.url)
        if old is not None:
            candidate = candidate.model_copy(
                update={"grant_id": old.grant_id, "status": old.status}
            )
        self.candidates[candidate.url] = candidate
        return candidate
