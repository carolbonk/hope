from hope_core.schemas.opportunity_matrix import DimensionScores
from hope_matching.config import CompositeWeights, MatchingConfig, Thresholds
from hope_matching.recommender import (
    LEVELS,
    Candidate,
    Features,
    _cap,
    composite_score,
    select_portfolio,
    soft_filter_cap,
    threshold_level,
)
from hypothesis import given
from hypothesis import strategies as st

score = st.floats(0, 100, allow_nan=False)
dimension_scores = st.builds(
    DimensionScores,
    mission_alignment=score,
    funding_fit=score,
    effort_to_funding=score,
    win_probability=st.floats(0, 1, allow_nan=False),
    deadline_feasibility=score,
    funder_relationship=score,
    strategic_priority_boost=score,
)


@st.composite
def weights(draw: st.DrawFn) -> CompositeWeights:
    raw = [draw(st.floats(0.01, 1)) for _ in range(7)]
    total = sum(raw)
    w = [r / total for r in raw]
    w[-1] = 1 - sum(w[:-1])
    names = list(CompositeWeights.model_fields)
    return CompositeWeights(**dict(zip(names, w, strict=True)))


status = st.sampled_from(["eligible", "needs_review", "ineligible"])


@given(dimension_scores, status, weights())
def test_composite_is_bounded_and_gated(s: DimensionScores, st_: str, w: CompositeWeights) -> None:
    value = composite_score(s, st_, w)  # type: ignore[arg-type]
    assert 0 <= value <= 100
    if st_ == "ineligible":
        assert value == 0
    else:
        assert value == composite_score(s, "eligible", w)


@given(dimension_scores, score)
def test_composite_is_monotonic_in_alignment(s: DimensionScores, bump: float) -> None:
    higher = s.model_copy(update={"mission_alignment": max(s.mission_alignment, bump)})
    assert composite_score(higher, "eligible", CompositeWeights()) >= composite_score(
        s, "eligible", CompositeWeights()
    )


@given(dimension_scores, status, st.floats(0, 1, allow_nan=False) | st.none())
def test_gate_caps_recommendation(s: DimensionScores, st_: str, ratio: float | None) -> None:
    f = Features(
        opportunity_id=__import__("uuid").uuid4(),
        eligibility=st_,  # type: ignore[arg-type]
        scores=s,
        expected_hours=10,
        efr=None,
        days_left=None,
        deadline_ratio=ratio,
        alignment_low_confidence=False,
    )
    cfg = MatchingConfig()
    score = composite_score(s, st_, cfg.weights)  # type: ignore[arg-type]
    level = _cap(threshold_level(score, Thresholds()), soft_filter_cap(f, cfg))
    assert level in LEVELS
    if st_ == "ineligible":
        assert level == "skip"
    if st_ == "needs_review":
        assert level != "pursue"
    if ratio is not None and ratio < 1:
        assert level in ("watch", "skip")


candidates = st.lists(
    st.builds(
        Candidate,
        key=st.uuids().map(str),
        score=score,
        hours=st.floats(0, 200, allow_nan=False),
        days_left=st.integers(-5, 120),
    ),
    max_size=12,
    unique_by=lambda c: c.key,
)


@given(candidates, st.floats(0.1, 16, allow_nan=False))
def test_portfolio_never_overbooks(cands: list[Candidate], per_day: float) -> None:
    fit = select_portfolio(cands, per_day)
    assert set(fit) == {c.key for c in cands}
    chosen = sorted(
        (c for c in cands if fit[c.key] != "conflicts"), key=lambda c: (c.days_left, c.key)
    )
    load = 0.0
    for c in chosen:
        load += c.hours
        assert load <= per_day * max(c.days_left, 0) + 1e-6
