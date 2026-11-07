"""Matching outputs that other services consume. Candidates for promotion to hope_core.schemas."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from hope_core.schemas.common import Contract, Evidence
from pydantic import Field

EligibilityStatus = Literal["eligible", "ineligible", "needs_review"]
RuleOutcomeKind = Literal["pass", "fail", "review"]
RubricDimension = Literal[
    "theory_of_change", "population", "geography", "outcomes", "capacity", "relationship"
]
RUBRIC: tuple[RubricDimension, ...] = (
    "theory_of_change",
    "population",
    "geography",
    "outcomes",
    "capacity",
    "relationship",
)


class RuleOutcome(Contract):
    rule_id: str
    outcome: RuleOutcomeKind
    detail: str
    evidence: list[Evidence] = []


class EffortEstimate(Contract):
    expected_hours: float = Field(ge=0)
    drivers: dict[str, float] = Field(default={}, description="hours contributed per feature")
    model: str = "heuristic-v1"


class EligibilityResult(Contract):
    opportunity_id: UUID
    agency_id: UUID
    status: EligibilityStatus
    failed_rules: list[str] = []
    review_rules: list[str] = []
    outcomes: list[RuleOutcome] = []
    evidence: list[Evidence] = []
    effort: EffortEstimate | None = None


class DimensionScore(Contract):
    dimension: RubricDimension
    score: float = Field(ge=0, le=100, description="median of accepted samples, 0 if none")
    samples: list[float] = Field(default=[], description="accepted sample scores")
    rejected_samples: int = Field(0, ge=0, description="samples without valid evidence ids")
    evidence_ids: list[str] = []
    rationale: str | None = None
    low_confidence: bool = False


class AlignmentAssessment(Contract):
    opportunity_id: UUID
    agency_id: UUID
    score: float = Field(ge=0, le=100)
    dimension_scores: list[DimensionScore]
    matched_programs: list[str] = []
    gaps: list[str] = []
    low_confidence: bool = False
    retrieved_evidence_ids: list[str] = []
    model_version: str
