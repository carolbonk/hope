from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import pytest
from hope_core.model_gateway import RunBudget
from hope_discovery.agent import (
    PROGRAM_TOTAL_CONCERN,
    SEARCH_UNAVAILABLE,
    DiscoveryFailed,
    grant_id_for,
)
from hope_discovery.mock import (
    CLOSED,
    DEMO_QUERIES,
    EXPIRED,
    ORAL,
    UNQUOTED,
    ScriptedWeb,
    extract_responder,
)
from hope_discovery.models import FitAssessment, PageExtraction

DEMO_TITLES = {
    "Rural Oral Health Access Grant 2027",
    "Community Health Worker Training Grants",
    "Mobile Health Equipment Fund",
}


def test_query_failure_continues(run_agent: Any) -> None:
    web = ScriptedWeb(fail={DEMO_QUERIES[1]})
    repo, result = run_agent(web=web)
    assert web.searched == DEMO_QUERIES
    assert result["counts"]["queries_failed"] == 1
    warning = next(e for e in repo.events if e["kind"] == "warning")
    assert warning["text"] == f"Search failed: {DEMO_QUERIES[1]}"
    assert {c.title for c in repo.candidates.values()} >= {"Rural Oral Health Access Grant 2027"}


def test_all_queries_fail(run_agent: Any) -> None:
    repo, result = run_agent(web=ScriptedWeb(fail_all=True))
    assert isinstance(result, DiscoveryFailed) and str(result) == SEARCH_UNAVAILABLE
    assert repo.events[-1] == {**repo.events[-1], "kind": "error", "text": SEARCH_UNAVAILABLE}
    assert repo.candidates == {}


def test_only_open_opportunities_kept(run_agent: Any) -> None:
    repo, result = run_agent()
    assert {c.title for c in repo.candidates.values()} == DEMO_TITLES
    assert result["counts"]["skipped_not_grant"] == 2
    skips = [e["text"] for e in repo.events if e["kind"] == "skip"]
    assert any(t.endswith("news, not a grant") for t in skips)
    assert any(t.endswith("a funder overview, not an open call") for t in skips)

    def unsure(messages: Any, schema: Any) -> dict[str, Any]:
        return extract_responder(messages, schema) | {"confidence": 0.5}

    repo, result = run_agent(web=ScriptedWeb(hits=[ORAL]), overrides={PageExtraction: unsure})
    assert repo.candidates == {} and result["counts"]["skipped_not_grant"] == 1

    repo, result = run_agent(web=ScriptedWeb(hits=[CLOSED]))
    assert repo.candidates == {} and result["counts"]["skipped_expired"] == 1


def test_expired_dropped(run_agent: Any) -> None:
    repo, result = run_agent()
    assert EXPIRED not in repo.candidates
    assert result["counts"]["skipped_expired"] == 1
    assert {"kind": "skip", "url": EXPIRED} | {
        "text": "Skipping Rural Health Mini-Grants 2025: deadline has passed"
    } in [{k: e[k] for k in ("kind", "url", "text")} for e in repo.events if "url" in e]


def test_progress_after_every_step(run_agent: Any) -> None:
    repo, result = run_agent()
    steps = [p.current_step for p, _ in repo.progress_log]
    for event in repo.events:
        assert event["text"] in steps, event["text"]
    texts = [e["text"] for e in repo.events]
    assert texts[:2] == ["Reading your profile", "Planning searches"]
    assert texts[2:8] == [f"Searching: {q}" for q in DEMO_QUERIES]
    assert texts[8] == "Found 7 unique links from 6 searches"
    assert texts[-1] == "Done: 3 grants found, 3 new"
    assert "Saved: Rural Oral Health Access Grant 2027 (fit 88)" in texts
    assert "Checking details on chwcollaborative.example.org" in texts
    final, status = repo.progress_log[-1]
    assert status == "running"
    assert (final.queries_total, final.queries_done, final.pages_read, final.candidates_found) == (
        6,
        6,
        7,
        3,
    )
    assert result["counts"] | {} == repo.counts
    assert repo.counts["urls_found"] >= 7 and repo.counts["failed_pages"] == 1


def test_timeout_and_budget_stop_gracefully(run_agent: Any) -> None:
    ticks = iter(range(0, 10_000, 100))
    repo, result = run_agent(clock=lambda: float(next(ticks)), job_timeout_s=300)
    assert isinstance(result, dict)
    assert len(repo.candidates) < 3
    warning = next(e for e in repo.events if e["kind"] == "warning")
    assert warning["text"].startswith("Stopped early after ")
    assert repo.events[-1]["text"].startswith("Done: ")

    repo, result = run_agent(budget=RunBudget(max_calls=3))
    assert isinstance(result, dict)
    assert [c.title for c in repo.candidates.values()] == ["Rural Oral Health Access Grant 2027"]
    assert any(e["text"].startswith("Stopped early after ") for e in repo.events)


def test_logs_have_no_page_text(run_agent: Any, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    run_agent()
    assert caplog.records
    for phrase in UNQUOTED:
        assert phrase not in caplog.text


def test_poor_fit_and_ineligible_skipped(run_agent: Any) -> None:
    def weak(messages: Any, schema: Any) -> dict[str, Any]:
        return {"fit_score": 20, "reasons": [{"text": "Barely related", "refs": []}]}

    repo, result = run_agent(overrides={FitAssessment: weak})
    assert repo.candidates == {}
    assert result["counts"]["skipped_poor_fit"] == len(DEMO_TITLES)
    assert any(e["text"].endswith("weak fit (20)") for e in repo.events if e["kind"] == "skip")

    def blocked(messages: Any, schema: Any) -> dict[str, Any]:
        return {
            "fit_score": 90,
            "reasons": [{"text": "Strong match", "refs": ["W1"]}],
            "eligibility_blocker": "W1",
        }

    repo, result = run_agent(web=ScriptedWeb(hits=[ORAL]), overrides={FitAssessment: blocked})
    assert repo.candidates == {} and result["counts"]["skipped_poor_fit"] == 1
    assert any(e["text"].endswith("not eligible") for e in repo.events if e["kind"] == "skip")


def test_program_total_amount_dropped(run_agent: Any) -> None:
    repo, _ = run_agent(web=ScriptedWeb(hits=[ORAL]), max_award_budget_ratio=0)
    (grant,) = repo.candidates.values()
    assert grant.amount_max is None
    assert PROGRAM_TOTAL_CONCERN in grant.concerns


def test_grant_id_is_stable_per_tenant() -> None:
    url = "https://example.org/grants/oral-health"
    a, b = UUID(int=1), UUID(int=2)
    assert grant_id_for(url, a) == grant_id_for(url, a)
    assert grant_id_for(url, a) != grant_id_for(url, b)
