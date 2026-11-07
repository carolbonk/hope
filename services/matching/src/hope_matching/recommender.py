"""A6 Recommender: features, composite score (blueprint 5.3), portfolio selection, matrix."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.grant_opportunity import GrantOpportunity
from hope_core.schemas.opportunity_matrix import (
    DimensionScores,
    Estimates,
    MatrixRow,
    OpportunityMatrix,
)

from hope_matching.config import CompositeWeights, MatchingConfig, Thresholds
from hope_matching.contracts import AlignmentAssessment, EligibilityResult, EligibilityStatus
from hope_matching.eligibility import (
    effort_to_funding_ratio,
    efr_score,
    estimate_effort,
    expected_value,
)

MODEL_VERSION = "a6-heuristic-v1"
Recommendation = Literal["pursue", "consider", "watch", "skip"]
CapacityFit = Literal["fits", "tight", "conflicts"]
LEVELS: tuple[Recommendation, ...] = ("skip", "watch", "consider", "pursue")
BASE_WIN_RATE = {
    "federal": 0.15,
    "state": 0.25,
    "local": 0.30,
    "private_foundation": 0.20,
    "community_foundation": 0.30,
    "corporate": 0.25,
    "other": 0.20,
}
RELATIONSHIP_SCORE = {"awarded": 100.0, "pending": 60.0, "declined": 30.0, "withdrawn": 30.0}
FUNDING_SWEET_SPOT = (0.05, 0.30)
DEADLINE_COMFORT = 2.0
DAYS_PER_MONTH = 30.0


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _funder_history(profile: AgencyProfile, opportunity: GrantOpportunity) -> list[str]:
    keys = {k.lower() for k in (opportunity.funder.funder_id, opportunity.funder.name) if k}
    return [g.outcome for g in profile.grant_history if g.funder_id.lower() in keys]


def funder_relationship(profile: AgencyProfile, opportunity: GrantOpportunity) -> float:
    return max((RELATIONSHIP_SCORE[o] for o in _funder_history(profile, opportunity)), default=0.0)


def win_probability(
    profile: AgencyProfile, opportunity: GrantOpportunity, alignment: float
) -> float:
    """Cold-start prior until the isotonic-calibrated model exists."""
    base = BASE_WIN_RATE[opportunity.funder.type] * (0.5 + alignment / 100.0)
    if "awarded" in _funder_history(profile, opportunity):
        base *= 1.5
    return round(_clamp(base, 0.01, 0.9), 4)


def funding_fit(profile: AgencyProfile, opportunity: GrantOpportunity) -> float:
    ceiling = opportunity.funding.award_ceiling
    budget = profile.financials.annual_operating_budget.amount_minor
    if ceiling is None:
        return 50.0
    if budget <= 0 or ceiling.amount_minor <= 0:
        return 0.0
    ratio = ceiling.amount_minor / budget
    low, high = FUNDING_SWEET_SPOT
    if ratio < low:
        return _clamp(100.0 * ratio / low)
    return 100.0 if ratio <= high else _clamp(100.0 * high / ratio)


def strategic_boost(opportunity: GrantOpportunity, config: MatchingConfig) -> float:
    funders = {f.lower() for f in config.strategic_funders}
    if {(opportunity.funder.funder_id or "").lower(), opportunity.funder.name.lower()} & funders:
        return 100.0
    priorities = opportunity.funding_priorities.value if opportunity.funding_priorities else []
    text = " ".join([opportunity.title, opportunity.summary or "", *priorities]).lower()
    return 100.0 if any(k.lower() in text for k in config.strategic_keywords) else 0.0


def daily_hours(profile: AgencyProfile, config: MatchingConfig) -> float:
    monthly = (profile.capacity and profile.capacity.monthly_hours_available) or (
        config.default_monthly_hours
    )
    return monthly / DAYS_PER_MONTH


def days_to_internal_deadline(
    opportunity: GrantOpportunity, config: MatchingConfig, today: date
) -> int | None:
    due = opportunity.deadlines.application_due
    if due is None:
        return None
    return (due.value.date() - today).days - config.internal_buffer_days


@dataclass
class Features:
    opportunity_id: UUID
    eligibility: EligibilityStatus
    scores: DimensionScores
    expected_hours: float
    efr: float | None
    days_left: int | None
    deadline_ratio: float | None
    alignment_low_confidence: bool
    failed_rules: list[str] = field(default_factory=list)
    review_rules: list[str] = field(default_factory=list)
    matched_programs: list[str] = field(default_factory=list)
    missing_ceiling: bool = False


def compute_features(
    profile: AgencyProfile,
    opportunity: GrantOpportunity,
    eligibility: EligibilityResult,
    alignment: AlignmentAssessment | None,
    config: MatchingConfig,
    today: date,
) -> Features:
    a = alignment.score if alignment else 0.0
    p_win = win_probability(profile, opportunity, a)
    effort = eligibility.effort or estimate_effort(opportunity)
    hours = effort.expected_hours
    efr = effort_to_funding_ratio(hours, opportunity.funding.award_ceiling, p_win)
    days_left = days_to_internal_deadline(opportunity, config, today)
    ratio = None
    if days_left is not None:
        needed = hours / daily_hours(profile, config)
        ratio = max(days_left, 0) / needed if needed > 0 else float(DEADLINE_COMFORT)
    names = {p.program_id: p.name for p in profile.programs}
    scores = DimensionScores(
        mission_alignment=_clamp(a),
        funding_fit=round(funding_fit(profile, opportunity), 2),
        effort_to_funding=round(efr_score(efr, config.efr_reference), 2),
        win_probability=p_win,
        deadline_feasibility=(
            100.0 if ratio is None else round(_clamp(100.0 * ratio / DEADLINE_COMFORT), 2)
        ),
        funder_relationship=funder_relationship(profile, opportunity),
        strategic_priority_boost=strategic_boost(opportunity, config),
    )
    return Features(
        opportunity_id=opportunity.opportunity_id,
        eligibility=eligibility.status,
        scores=scores,
        expected_hours=hours,
        efr=efr,
        days_left=days_left,
        deadline_ratio=ratio,
        alignment_low_confidence=bool(alignment and alignment.low_confidence),
        failed_rules=eligibility.failed_rules,
        review_rules=eligibility.review_rules,
        matched_programs=[
            names.get(p, p) for p in (alignment.matched_programs if alignment else [])
        ],
        missing_ceiling=opportunity.funding.award_ceiling is None,
    )


def composite_score(
    scores: DimensionScores, eligibility: EligibilityStatus, weights: CompositeWeights
) -> float:
    """S = G_elig * weighted sum; needs_review passes the gate but is labelled."""
    gate = 0.0 if eligibility == "ineligible" else 1.0
    w = weights
    total = (
        w.mission_alignment * scores.mission_alignment
        + w.funding_fit * scores.funding_fit
        + w.effort_to_funding * scores.effort_to_funding
        + w.win_probability * 100.0 * scores.win_probability
        + w.deadline_feasibility * scores.deadline_feasibility
        + w.funder_relationship * scores.funder_relationship
        + w.strategic_priority_boost * scores.strategic_priority_boost
    )
    return round(_clamp(gate * total), 2)


def threshold_level(score: float, thresholds: Thresholds) -> Recommendation:
    if score >= thresholds.pursue:
        return "pursue"
    if score >= thresholds.consider:
        return "consider"
    return "watch" if score >= thresholds.watch else "skip"


def _cap(level: Recommendation, ceiling: Recommendation) -> Recommendation:
    return LEVELS[min(LEVELS.index(level), LEVELS.index(ceiling))]


def soft_filter_cap(f: Features, config: MatchingConfig) -> Recommendation:
    """Eligibility gate and soft filters (EFR cut-off, deadline feasibility) cap the label."""
    if f.eligibility == "ineligible":
        return "skip"
    cap: Recommendation = "consider" if f.eligibility == "needs_review" else "pursue"
    efr_too_high = config.efr_cutoff is not None and f.efr is not None and f.efr > config.efr_cutoff
    if efr_too_high or (f.deadline_ratio is not None and f.deadline_ratio < 1.0):
        cap = _cap(cap, "watch")
    return cap


@dataclass(frozen=True)
class Candidate:
    key: str
    score: float
    hours: float
    days_left: int


def select_portfolio(
    candidates: list[Candidate],
    hours_per_day: float,
    max_concurrent: int | None = None,
    tight_slack: float = 0.2,
) -> dict[str, CapacityFit]:
    """Greedy knapsack by score per staff-hour. A pick is kept only if every deadline is still
    schedulable earliest-deadline-first within the staff hours available before it."""

    def slacks(chosen: list[Candidate]) -> dict[str, float] | None:
        load, out = 0.0, {}
        for c in sorted(chosen, key=lambda c: (c.days_left, c.key)):
            load += c.hours
            available = hours_per_day * max(c.days_left, 0)
            if load > available + 1e-9:
                return None
            out[c.key] = (available - load) / available if available else 0.0
        return out

    chosen: list[Candidate] = []
    order = sorted(candidates, key=lambda c: (-c.score / max(c.hours, 1.0), c.key))
    for candidate in order:
        if max_concurrent is not None and len(chosen) >= max_concurrent:
            break
        if slacks([*chosen, candidate]) is not None:
            chosen.append(candidate)
    final = slacks(chosen) or {}
    fit: dict[str, CapacityFit] = {c.key: "conflicts" for c in candidates}
    fit.update({k: "tight" if s < tight_slack else "fits" for k, s in final.items()})
    return fit


def risks(f: Features, config: MatchingConfig, capacity: CapacityFit | None) -> list[str]:
    out = [f"failed eligibility rule: {r}" for r in f.failed_rules]
    out += [f"eligibility needs review: {r}" for r in f.review_rules]
    if f.missing_ceiling:
        out.append("award ceiling unknown")
    if config.efr_cutoff is not None and f.efr is not None and f.efr > config.efr_cutoff:
        out.append(f"effort-to-funding ratio {f.efr:.4f} above cut-off {config.efr_cutoff:g}")
    if f.deadline_ratio is not None and f.deadline_ratio < 1.0:
        out.append("internal deadline leaves less time than the estimated effort")
    if f.alignment_low_confidence:
        out.append("alignment score is low confidence")
    if capacity == "conflicts":
        out.append("does not fit current staff capacity")
    return out


def explain(f: Features, score: float, recommendation: Recommendation, capacity: str) -> str:
    """Built only from computed features, so the text can never claim more than the numbers."""
    s = f.scores
    parts = [
        f"{recommendation} (composite {score:g}, eligibility {f.eligibility}, capacity {capacity})",
        f"mission alignment {s.mission_alignment:g}",
        f"funding fit {s.funding_fit:g}",
        f"effort-to-funding {s.effort_to_funding:g}",
        f"win probability {s.win_probability:.0%}",
        f"deadline feasibility {s.deadline_feasibility:g}",
        f"relationship {s.funder_relationship:g}",
        f"strategic boost {s.strategic_priority_boost:g}",
        f"about {f.expected_hours:g} staff hours",
    ]
    if f.matched_programs:
        parts.append("matched programs: " + ", ".join(f.matched_programs))
    return "; ".join(parts) + "."


@dataclass(frozen=True)
class Assessed:
    opportunity: GrantOpportunity
    eligibility: EligibilityResult
    alignment: AlignmentAssessment | None


def build_matrix(
    profile: AgencyProfile,
    assessed: list[Assessed],
    config: MatchingConfig | None = None,
    today: date | None = None,
    generated_at: datetime | None = None,
) -> OpportunityMatrix:
    config = config or MatchingConfig()
    generated_at = generated_at or datetime.now(UTC)
    today = today or generated_at.date()
    rows = []
    for item in assessed:
        f = compute_features(
            profile, item.opportunity, item.eligibility, item.alignment, config, today
        )
        score = composite_score(f.scores, f.eligibility, config.weights)
        level = _cap(threshold_level(score, config.thresholds), soft_filter_cap(f, config))
        rows.append((item, f, score, level))

    horizon = config.horizon_days
    candidates = [
        Candidate(
            str(f.opportunity_id),
            score,
            f.expected_hours,
            horizon if f.days_left is None else f.days_left,
        )
        for _, f, score, level in rows
        if level != "skip"
    ]
    max_concurrent = profile.capacity.max_concurrent_applications if profile.capacity else None
    fits = select_portfolio(
        candidates, daily_hours(profile, config), max_concurrent, config.tight_slack
    )

    out = []
    ordered = sorted(rows, key=lambda r: (-r[2], str(r[1].opportunity_id)))
    for rank, (item, f, score, level) in enumerate(ordered, start=1):
        capacity = fits.get(str(f.opportunity_id))
        if capacity == "conflicts":
            level = _cap(level, "consider")
        ceiling = item.opportunity.funding.award_ceiling
        out.append(
            MatrixRow(
                opportunity_id=f.opportunity_id,
                rank=rank,
                composite_score=score,
                eligibility=f.eligibility,
                scores=f.scores,
                estimates=Estimates(
                    expected_hours=f.expected_hours,
                    expected_value=expected_value(ceiling, f.scores.win_probability),
                    days_to_internal_deadline=f.days_left,
                ),
                capacity_fit=capacity,
                recommendation=level,
                explanation=explain(f, score, level, capacity or "n/a"),
                top_matched_programs=f.matched_programs,
                risks=risks(f, config, capacity),
            )
        )
    return OpportunityMatrix(
        agency_id=profile.agency_id,
        generated_at=generated_at,
        model_version=MODEL_VERSION,
        weights_profile=config.weights_profile,
        rows=out,
    )
