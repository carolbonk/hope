from datetime import timedelta
from typing import Any

import pytest
from hope_core.money import Money
from hope_core.schemas.agency_profile import Capacity, GrantHistoryItem
from hope_core.schemas.opportunity_matrix import DimensionScores, OpportunityMatrix
from hope_matching.alignment import assess_alignment
from hope_matching.config import CompositeWeights, MatchingConfig, Thresholds
from hope_matching.eligibility import evaluate_eligibility
from hope_matching.recommender import (
    Assessed,
    Candidate,
    build_matrix,
    composite_score,
    funding_fit,
    select_portfolio,
    threshold_level,
    win_probability,
)
from hope_matching.testing import NOW, gateway, opportunity, profile

TODAY = NOW.date()


def scores(**changes: float) -> DimensionScores:
    base: dict[str, float] = {
        "mission_alignment": 80,
        "funding_fit": 100,
        "effort_to_funding": 60,
        "win_probability": 0.25,
        "deadline_feasibility": 100,
        "funder_relationship": 0,
        "strategic_priority_boost": 0,
    }
    return DimensionScores.model_validate(base | changes)


def test_composite_matches_blueprint_formula() -> None:
    # 0.35*80 + 0.15*100 + 0.15*60 + 0.15*25 + 0.10*100 = 65.75
    assert composite_score(scores(), "eligible", CompositeWeights()) == 65.75
    assert composite_score(scores(), "needs_review", CompositeWeights()) == 65.75
    assert composite_score(scores(), "ineligible", CompositeWeights()) == 0.0


def test_tenant_weights_are_validated_and_applied() -> None:
    with pytest.raises(ValueError):
        CompositeWeights(mission_alignment=0.9)
    only_alignment = CompositeWeights(
        mission_alignment=1,
        funding_fit=0,
        effort_to_funding=0,
        win_probability=0,
        deadline_feasibility=0,
        funder_relationship=0,
        strategic_priority_boost=0,
    )
    assert composite_score(scores(), "eligible", only_alignment) == 80.0
    with pytest.raises(ValueError):
        Thresholds(pursue=50, consider=60)


@pytest.mark.parametrize(
    ("score", "level"),
    [(70, "pursue"), (69.99, "consider"), (55, "consider"), (40, "watch"), (0, "skip")],
)
def test_thresholds(score: float, level: str) -> None:
    assert threshold_level(score, Thresholds()) == level


def test_funding_fit_bands() -> None:
    p = profile()  # 1.85M budget
    assert funding_fit(p, opportunity()) == 100.0  # 250k = 13.5%
    tiny = opportunity(
        funding=opportunity().funding.model_copy(
            update={"award_ceiling": Money.from_decimal("9250")}
        )
    )
    assert funding_fit(p, tiny) == pytest.approx(10.0)
    none = opportunity(funding=opportunity().funding.model_copy(update={"award_ceiling": None}))
    assert funding_fit(p, none) == 50.0


def test_prior_award_raises_relationship_and_win_probability() -> None:
    o = opportunity()
    history = [GrantHistoryItem(funder_id=o.funder.name, outcome="awarded")]
    assert win_probability(profile(grant_history=history), o, 50) > win_probability(
        profile(), o, 50
    )


def C(key: str, score: float, hours: float, days: int) -> Candidate:
    return Candidate(key, score, hours, days)


def test_knapsack_respects_deadlines_and_capacity() -> None:
    # 2 hours/day: by day 10 only 20 hours, by day 30 60 hours.
    fit = select_portfolio(
        [C("a", 80, 15, 10), C("b", 70, 15, 10), C("c", 60, 40, 30), C("d", 90, 100, 30)],
        hours_per_day=2.0,
    )
    assert fit == {"a": "fits", "b": "conflicts", "c": "tight", "d": "conflicts"}


def test_knapsack_max_concurrent() -> None:
    fit = select_portfolio([C("a", 80, 1, 30), C("b", 70, 1, 30)], 8.0, max_concurrent=1)
    assert fit == {"a": "fits", "b": "conflicts"}


def assessed(p: Any, o: Any) -> Assessed:
    e = evaluate_eligibility(p, o, TODAY)
    a = assess_alignment(gateway(), p, o) if e.status != "ineligible" else None
    return Assessed(o, e, a)


def test_matrix_rows_are_ranked_labelled_and_explained() -> None:
    p = profile(capacity=Capacity(monthly_hours_available=60))
    good = opportunity(1)
    ineligible = opportunity(
        2, eligibility=good.eligibility.model_copy(update={"applicant_types": ["tribal"]})
    )
    late = opportunity(3, days=7)
    matrix = build_matrix(
        p, [assessed(p, o) for o in (late, ineligible, good)], today=TODAY, generated_at=NOW
    )
    OpportunityMatrix.model_validate(matrix.model_dump(mode="json"))
    by_id = {r.opportunity_id: r for r in matrix.rows}
    assert [r.rank for r in matrix.rows] == [1, 2, 3]
    assert matrix.rows[0].opportunity_id == good.opportunity_id
    assert by_id[ineligible.opportunity_id].recommendation == "skip"
    assert by_id[ineligible.opportunity_id].composite_score == 0
    assert by_id[ineligible.opportunity_id].capacity_fit is None
    assert "failed eligibility rule: applicant_type" in by_id[ineligible.opportunity_id].risks
    assert by_id[late.opportunity_id].recommendation in ("watch", "skip")
    row = by_id[good.opportunity_id]
    assert row.estimates.expected_value is not None
    assert row.estimates.days_to_internal_deadline == 40
    assert row.explanation and f"composite {row.composite_score:g}" in row.explanation


def test_needs_review_is_never_pursue() -> None:
    p = profile()
    o = opportunity(
        eligibility=opportunity().eligibility.model_copy(update={"applicant_types": ["churches"]})
    )
    cfg = MatchingConfig(thresholds=Thresholds(pursue=0, consider=0, watch=0))
    row = build_matrix(p, [assessed(p, o)], cfg, today=TODAY, generated_at=NOW).rows[0]
    assert row.eligibility == "needs_review" and row.recommendation == "consider"


def test_efr_cutoff_demotes() -> None:
    p = profile()
    cfg = MatchingConfig(thresholds=Thresholds(pursue=0, consider=0, watch=0), efr_cutoff=1e-6)
    row = build_matrix(p, [assessed(p, opportunity())], cfg, today=TODAY, generated_at=NOW).rows[0]
    assert row.recommendation == "watch"
    assert any("effort-to-funding" in r for r in row.risks)


def test_strategic_keywords_boost() -> None:
    p = profile()
    cfg = MatchingConfig(strategic_keywords=["stem"])
    base = build_matrix(p, [assessed(p, opportunity())], today=TODAY, generated_at=NOW).rows[0]
    boosted = build_matrix(
        p, [assessed(p, opportunity())], cfg, today=TODAY, generated_at=NOW
    ).rows[0]
    assert boosted.scores.strategic_priority_boost == 100
    assert boosted.composite_score == pytest.approx(base.composite_score + 5)


def test_rolling_deadline_uses_horizon() -> None:
    o = opportunity()
    o = o.model_copy(
        update={
            "deadlines": o.deadlines.model_copy(update={"application_due": None, "rolling": True})
        }
    )
    p = profile()
    row = build_matrix(p, [assessed(p, o)], today=TODAY, generated_at=NOW + timedelta(0)).rows[0]
    assert row.scores.deadline_feasibility == 100
    assert row.estimates.days_to_internal_deadline is None
    assert row.capacity_fit == "fits"
