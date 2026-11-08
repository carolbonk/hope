"""Call 3: fit. The model scores; `postprocess_fit` clamps, caps and builds the citations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from hope_core.schemas.hackathon import Citation

from hope_discovery.digest import ProfileDigest
from hope_discovery.models import FitAssessment, Point

BLOCKER_CAP = 30
_REF = re.compile(r"^[PW]\d{1,3}$")


@dataclass(frozen=True)
class WebSource:
    ref: str  # "W1"
    url: str
    title: str
    quote: str


@dataclass
class FitResult:
    score: int
    reasons: list[str]
    concerns: list[str]
    citations: list[Citation] = field(default_factory=list)


def _trim(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def postprocess_fit(
    fit: FitAssessment,
    web: list[WebSource],
    digest: ProfileDigest,
    now: datetime,
    extra_concerns: list[str] | None = None,
    always_cite: list[str] | None = None,
) -> FitResult:
    web_by_ref = {w.ref: w for w in web}
    profile_by_ref = digest.by_ref()
    ids: dict[str, str] = {}
    citations: list[Citation] = []

    def cite(ref: str) -> str | None:
        if ref in ids:
            return ids[ref]
        if ref in web_by_ref:
            w = web_by_ref[ref]
            c = Citation(
                citation_id=f"c{len(citations) + 1}",
                kind="web",
                url=w.url,
                title=w.title[:300] or None,
                quote=w.quote[:500],
                retrieved_at=now,
            )
        elif ref in profile_by_ref:
            p = profile_by_ref[ref]
            c = Citation(
                citation_id=f"c{len(citations) + 1}",
                kind="profile",
                quote=p.text[:500],
                profile_path=p.path,
            )
        else:
            return None
        citations.append(c)
        cid: str = c.citation_id
        ids[ref] = cid
        return cid

    def render(point: Point) -> str:
        refs = [r.strip().upper() for r in point.refs if _REF.match(r.strip().upper())]
        markers = "".join(f"[{cid}]" for r in dict.fromkeys(refs) if (cid := cite(r)))
        text = _trim(point.text)
        return f"{text} {markers}" if markers else text

    score = max(0, min(100, fit.fit_score))
    reasons = [render(p) for p in fit.reasons[:4]]
    concerns = [render(p) for p in fit.concerns[:3]]
    blocker = (fit.eligibility_blocker or "").strip().upper()
    if blocker in web_by_ref:
        score = min(score, BLOCKER_CAP)
        cid = cite(blocker)
        concerns.insert(0, f"May not be eligible: {_trim(web_by_ref[blocker].quote, 100)} [{cid}]")
    concerns.extend(extra_concerns or [])
    for ref in always_cite or []:
        cite(ref)
    return FitResult(score=score, reasons=reasons, concerns=concerns, citations=citations)
