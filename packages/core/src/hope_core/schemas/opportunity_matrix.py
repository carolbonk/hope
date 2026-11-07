from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from hope_core.money import Money
from hope_core.schemas.common import Contract

Score = float  # 0..100 unless noted


class DimensionScores(Contract):
    mission_alignment: Score = Field(ge=0, le=100)
    funding_fit: Score = Field(ge=0, le=100)
    effort_to_funding: Score = Field(ge=0, le=100, description="normalized inverse of EFR")
    win_probability: float = Field(ge=0, le=1)
    deadline_feasibility: Score = Field(ge=0, le=100)
    funder_relationship: Score = Field(0, ge=0, le=100)
    strategic_priority_boost: Score = Field(0, ge=0, le=100)


class Estimates(Contract):
    expected_hours: float | None = None
    expected_value: Money | None = None
    days_to_internal_deadline: int | None = None


class MatrixRow(Contract):
    opportunity_id: UUID
    rank: int = Field(ge=1)
    composite_score: Score = Field(ge=0, le=100)
    eligibility: Literal["eligible", "needs_review", "ineligible"]
    scores: DimensionScores
    estimates: Estimates = Estimates()
    capacity_fit: Literal["fits", "tight", "conflicts"] | None = None
    recommendation: Literal["pursue", "consider", "watch", "skip"]
    explanation: str | None = Field(None, description="generated only from the values above")
    top_matched_programs: list[str] = []
    risks: list[str] = []


class OpportunityMatrix(Contract):
    agency_id: UUID
    generated_at: datetime
    model_version: str
    weights_profile: str | None = None
    rows: list[MatrixRow]
