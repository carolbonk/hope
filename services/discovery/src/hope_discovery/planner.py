"""Call 1: plan the searches. The model suggests; `postprocess_plan` decides."""

from __future__ import annotations

from datetime import date

from hope_discovery.digest import ProfileDigest
from hope_discovery.models import QueryPlan
from hope_discovery.settings import DiscoverySettings, get_discovery_settings


def _clean(text: str) -> str:
    return " ".join(text.split())


def fallback_queries(
    digest: ProfileDigest, focus_keywords: list[str], location: str | None, today: date
) -> list[str]:
    """Deterministic queries, in the spec's order; `{focus_area}`/`{program}` rotate per round."""
    year = str(today.year)
    loc = location or (digest.service_area[0] if digest.service_area else "")
    keyword = focus_keywords[0] if focus_keywords else ""
    rounds = max(len(digest.focus_areas), len(digest.programs), 1)
    out: list[str] = []
    for i in range(rounds):
        area = digest.focus_areas[i] if i < len(digest.focus_areas) else ""
        program = digest.programs[i] if i < len(digest.programs) else ""
        if area:
            out.append(f"{area} grants for nonprofits {loc}")
        if program:
            out.append(f"{program} grant {loc} {year}")
        if i == 0:
            out.append(f"foundation grants {keyword} {loc}")
            out.append(f"community foundation grants {loc} {year}")
        if area:
            out.append(f"{area} funding opportunity 501(c)(3) {year}")
    return [_clean(q) for q in out]


def postprocess_plan(
    plan: QueryPlan | None,
    digest: ProfileDigest,
    focus_keywords: list[str],
    location: str | None,
    today: date,
    settings: DiscoverySettings | None = None,
) -> list[str]:
    s = settings or get_discovery_settings()
    forbidden = [f.lower() for f in digest.forbidden if f.strip()]
    kept: list[str] = []
    seen: set[str] = set()

    def offer(query: str) -> None:
        q = _clean(query)
        low = q.lower()
        if len(q) < 3 or len(q) > 120 or low in seen or any(f in low for f in forbidden):
            return
        seen.add(low)
        kept.append(q)

    for planned in plan.queries if plan else []:
        offer(planned.query)
    if len(kept) < s.min_queries:
        for q in fallback_queries(digest, focus_keywords, location, today):
            if len(kept) >= s.min_queries:
                break
            offer(q)
    return kept[: s.max_queries]
