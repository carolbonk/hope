"""Call 2: classify a page and extract quotes; `verify_extraction` keeps only what is on it."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from hope_core.web import Link

from hope_discovery.models import PageExtraction, Quote
from hope_discovery.parse import has_money_or_date
from hope_discovery.settings import DiscoverySettings, get_discovery_settings
from hope_discovery.urls import canonicalize, registrable_domain, same_site

FUNDER_NOT_CONFIRMED = "Funder name not confirmed on the page"
_INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def clean_text(text: str) -> str:
    return " ".join(_INVISIBLE.sub("", text).split())


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


@dataclass
class VerifiedQuote:
    text: str
    page: int  # 1 or 2


@dataclass
class VerifiedExtraction:
    kind: str
    keep: bool
    title: str
    funder: str
    summary: str
    amount: VerifiedQuote | None = None
    deadline: VerifiedQuote | None = None
    rolling: bool = False
    eligibility: list[VerifiedQuote] = field(default_factory=list)
    eligibility_summary: str | None = None
    concerns: list[str] = field(default_factory=list)
    detail_url: str | None = None


def scrub_summary(summary: str | None) -> str:
    if not summary:
        return ""
    sentences = _SENTENCE.split(" ".join(summary.split()))
    return " ".join(s for s in sentences if s and not has_money_or_date(s)).strip()


def verify_extraction(
    ext: PageExtraction,
    pages: list[str],
    page_url: str,
    page_title: str,
    links: list[Link],
    settings: DiscoverySettings | None = None,
) -> VerifiedExtraction:
    s = settings or get_discovery_settings()
    normed = [_norm(p) for p in pages]

    def check(q: Quote | None) -> VerifiedQuote | None:
        if q is None or q.page > len(normed):
            return None
        return (
            VerifiedQuote(q.text.strip(), q.page) if _norm(q.text) in normed[q.page - 1] else None
        )

    concerns: list[str] = []
    title_q, funder_q = check(ext.title), check(ext.funder)
    title = title_q.text if title_q else (page_title.strip() or registrable_domain(page_url))
    if funder_q:
        funder = funder_q.text
    else:
        funder = registrable_domain(page_url)
        concerns.append(FUNDER_NOT_CONFIRMED)
    keep = (
        ext.is_grant_opportunity
        and ext.kind == "open_opportunity"
        and ext.confidence >= s.min_classify_confidence
    )
    detail_url = None
    index = ext.detail_link_index
    if ext.needs_more_detail and index is not None and 1 <= index <= min(len(links), 40):
        candidate = canonicalize(links[index - 1].url)
        if candidate and candidate != canonicalize(page_url) and same_site(candidate, page_url):
            detail_url = candidate
    return VerifiedExtraction(
        kind=ext.kind,
        keep=keep,
        title=title[:200],
        funder=funder[:200],
        summary=scrub_summary(ext.summary),
        amount=check(ext.amount),
        deadline=check(ext.deadline),
        rolling=ext.rolling,
        eligibility=[v for q in ext.eligibility if (v := check(q))],
        eligibility_summary=scrub_summary(ext.eligibility_summary) or None,
        concerns=concerns,
        detail_url=detail_url,
    )
