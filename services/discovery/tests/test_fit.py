from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hope_discovery.demo import demo_profile
from hope_discovery.digest import build_digest
from hope_discovery.fit import BLOCKER_CAP, WebSource, postprocess_fit
from hope_discovery.mock import ORAL, ScriptedWeb
from hope_discovery.models import FitAssessment, Point

NOW = datetime(2026, 11, 8, 14, 0, tzinfo=UTC)


def test_postprocess_citations_markers_blocker() -> None:
    digest = build_digest(demo_profile())
    web = [
        WebSource("W1", ORAL, "Rural Oral Health", "up to $75,000 per year"),
        WebSource("W2", ORAL, "Rural Oral Health", "Only open to public schools"),
    ]
    fit = FitAssessment.model_construct(
        fit_score=140,
        reasons=[
            Point(text="Funds rural dental care", refs=["W1", "P1"]),
            Point(text="Uncited reason here", refs=[]),
            Point(text="Bad refs only", refs=["W9", "X1"]),
            Point(text="Reason four", refs=["w1"]),
            Point(text="Reason five is dropped", refs=["P2"]),
        ],
        concerns=[Point(text=f"Concern {i}", refs=["W2"]) for i in range(5)],
        eligibility_blocker=None,
    )
    out = postprocess_fit(fit, web, digest, NOW)
    assert out.score == 100
    assert out.reasons[0] == "Funds rural dental care [c1][c2]"
    assert out.reasons[1] == "Uncited reason here"
    assert out.reasons[2] == "Bad refs only"
    assert out.reasons[3] == "Reason four [c1]"
    assert len(out.reasons) == 4 and len(out.concerns) == 3
    assert [c.citation_id for c in out.citations] == ["c1", "c2", "c3"]
    assert out.citations[0].kind == "web" and out.citations[0].url == ORAL
    assert out.citations[1].kind == "profile" and out.citations[1].profile_path

    blocked = postprocess_fit(
        fit.model_copy(update={"eligibility_blocker": "W2"}), web, digest, NOW
    )
    assert blocked.score == BLOCKER_CAP
    assert blocked.concerns[0].startswith("May not be eligible: Only open to public schools [c")
    unverified = postprocess_fit(
        fit.model_copy(update={"eligibility_blocker": "W7", "fit_score": -5}), web, digest, NOW
    )
    assert unverified.score == 0
    assert not unverified.concerns[0].startswith("May not be eligible")


def test_fit_retry_then_skip(run_agent: Any) -> None:
    calls: list[int] = []

    def broken(_messages: Any, _schema: Any) -> dict[str, Any]:
        calls.append(1)
        raise ValueError("bad json")

    repo, _ = run_agent(web=ScriptedWeb(hits=[ORAL]), overrides={FitAssessment: broken})
    assert len(calls) == 2 and repo.candidates == {}
    assert any(e["text"].startswith("Couldn't score") for e in repo.events)

    flaky: list[int] = []

    def once(messages: Any, schema: Any) -> dict[str, Any]:
        flaky.append(1)
        if len(flaky) == 1:
            raise ValueError("bad json")
        return {"fit_score": 77, "reasons": [{"text": "Good match", "refs": ["W1"]}]}

    repo, _ = run_agent(web=ScriptedWeb(hits=[ORAL]), overrides={FitAssessment: once})
    (candidate,) = repo.candidates.values()
    assert candidate.fit_score == 77 and candidate.fit_reasons == ["Good match [c1]"]
