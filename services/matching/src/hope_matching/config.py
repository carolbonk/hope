"""Per-tenant matching configuration (blueprint 5.3: weights are tenant config)."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CompositeWeights(BaseModel):
    """Weights of S = G_elig * (0.35A + 0.15F + 0.15E + 0.15*100*P_win + 0.10D + 0.05R + 0.05B)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_alignment: float = Field(0.35, ge=0, le=1)
    funding_fit: float = Field(0.15, ge=0, le=1)
    effort_to_funding: float = Field(0.15, ge=0, le=1)
    win_probability: float = Field(0.15, ge=0, le=1)
    deadline_feasibility: float = Field(0.10, ge=0, le=1)
    funder_relationship: float = Field(0.05, ge=0, le=1)
    strategic_priority_boost: float = Field(0.05, ge=0, le=1)

    @model_validator(mode="after")
    def _sum_to_one(self) -> Self:
        total = sum(self.model_dump().values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weights must sum to 1, got {total}")
        return self


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pursue: float = Field(70, ge=0, le=100)
    consider: float = Field(55, ge=0, le=100)
    watch: float = Field(40, ge=0, le=100)

    @model_validator(mode="after")
    def _descending(self) -> Self:
        if not self.pursue >= self.consider >= self.watch:
            raise ValueError("thresholds must satisfy pursue >= consider >= watch")
        return self


class MatchingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    weights_profile: str = "heuristic-v1"
    weights: CompositeWeights = CompositeWeights()
    thresholds: Thresholds = Thresholds()
    efr_reference: float = Field(
        0.002, gt=0, description="hours per award dollar that maps to E = 50"
    )
    efr_cutoff: float | None = Field(0.01, gt=0, description="soft filter: demote above this EFR")
    internal_buffer_days: int = Field(5, ge=0)
    default_monthly_hours: int = Field(80, gt=0)
    horizon_days: int = Field(90, gt=0, description="planning horizon for rolling deadlines")
    tight_slack: float = Field(0.2, ge=0, le=1)
    strategic_funders: list[str] = []
    strategic_keywords: list[str] = []
    judge_samples: int = Field(3, ge=1)
    low_confidence_stdev: float = Field(15, ge=0)
    retrieval_top_k: int = Field(8, ge=1)
