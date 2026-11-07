"""Eligibility, mission alignment and recommendation agents (A4, A5, A6)."""

from hope_matching.agents import MatchingAgent
from hope_matching.alignment import assess_alignment
from hope_matching.config import CompositeWeights, MatchingConfig, Thresholds
from hope_matching.contracts import AlignmentAssessment, EffortEstimate, EligibilityResult
from hope_matching.eligibility import draft_clause_rule, evaluate_eligibility
from hope_matching.recommender import Assessed, build_matrix, composite_score

__all__ = [
    "AlignmentAssessment",
    "Assessed",
    "CompositeWeights",
    "EffortEstimate",
    "EligibilityResult",
    "MatchingAgent",
    "MatchingConfig",
    "Thresholds",
    "assess_alignment",
    "build_matrix",
    "composite_score",
    "draft_clause_rule",
    "evaluate_eligibility",
]
