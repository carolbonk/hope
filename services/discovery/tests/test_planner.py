from __future__ import annotations

from datetime import date
from typing import Any

from hope_discovery.demo import demo_profile
from hope_discovery.digest import build_digest
from hope_discovery.models import PlannedQuery, QueryPlan
from hope_discovery.planner import fallback_queries, postprocess_plan
from hope_discovery.settings import DiscoverySettings

TODAY = date(2026, 11, 8)
S = DiscoverySettings()


def plan(*queries: str) -> QueryPlan:
    return QueryPlan(queries=[PlannedQuery(query=q, rationale="r") for q in queries])


def test_queries_deduped_and_bounded() -> None:
    digest = build_digest(demo_profile())
    many = [f"dental grants round {i}" for i in range(8)]
    out = postprocess_plan(
        plan("Dental  grants WA", "dental grants wa", *many), digest, [], None, TODAY, S
    )
    assert len(out) == S.max_queries
    assert out[0] == "Dental grants WA"
    assert len({q.lower() for q in out}) == len(out)


def test_fallback_queries() -> None:
    digest = build_digest(demo_profile(), "Chelan County, WA")
    fallbacks = fallback_queries(digest, ["dental"], "Chelan County, WA", TODAY)
    assert "foundation grants dental Chelan County, WA" in fallbacks
    assert "community foundation grants Chelan County, WA 2026" in fallbacks
    out = postprocess_plan(
        plan("rural dental grants"), digest, ["dental"], "Chelan County, WA", TODAY, S
    )
    assert len(out) == S.min_queries
    assert out[0] == "rural dental grants" and out[1:] == fallbacks[: S.min_queries - 1]


def test_plan_failure_uses_fallbacks(run_agent: Any) -> None:
    def broken(_messages: Any, _schema: Any) -> dict[str, Any]:
        raise ValueError("model down")

    repo, result = run_agent(overrides={QueryPlan: broken})
    assert isinstance(result, dict)
    assert len(repo.queries) == S.min_queries
    assert any(e["text"] == "Couldn't plan searches, using standard ones" for e in repo.events)
    digest = build_digest(demo_profile())
    assert (
        postprocess_plan(None, digest, [], None, TODAY, S)
        == fallback_queries(digest, [], None, TODAY)[: S.min_queries]
    )


def test_no_org_name_or_ein() -> None:
    profile = demo_profile()
    digest = build_digest(profile)
    rendered = digest.render()
    assert profile.legal.legal_name not in rendered and profile.legal.ein not in rendered
    out = postprocess_plan(
        plan(
            "Riverbend Community Health Alliance grants",
            "grants for EIN 91-1234567",
            "rural oral health grants",
        ),
        digest,
        [],
        None,
        TODAY,
        S,
    )
    assert "rural oral health grants" in out
    for q in out:
        assert "riverbend" not in q.lower() and "91-1234567" not in q
