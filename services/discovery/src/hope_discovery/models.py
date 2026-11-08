"""Response models for the three discovery model calls. Local to this package (H2 section E).

None of them has a money, date, status or URL field that code trusts.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field


def _clip_list(limit: int) -> BeforeValidator:
    """Models often return null or one item too many; keep the first `limit` instead of failing."""

    def clip(value: Any) -> Any:
        if value is None:
            return []
        return value[:limit] if isinstance(value, list) else value

    return BeforeValidator(clip)


def _clip_text(limit: int) -> BeforeValidator:
    def clip(value: Any) -> Any:
        return value[:limit] if isinstance(value, str) else value

    return BeforeValidator(clip)


class PlannedQuery(BaseModel):
    query: Annotated[str, _clip_text(120)] = Field(min_length=3, max_length=120)
    rationale: Annotated[str, _clip_text(140)] = Field(max_length=140)
    profile_refs: Annotated[list[str], _clip_list(4)] = Field(
        default=[], max_length=4
    )  # "P1", "P3"


class QueryPlan(BaseModel):
    queries: Annotated[list[PlannedQuery], _clip_list(10)] = Field(
        min_length=1, max_length=10
    )  # code keeps 5-8


class Quote(BaseModel):
    text: Annotated[str, _clip_text(300)] = Field(min_length=3, max_length=300)
    page: Literal[1, 2] = 1


PageKind = Literal[
    "open_opportunity",
    "closed_or_past",
    "funder_overview",
    "list_or_directory",
    "news_or_blog",
    "not_relevant",
]


class PageExtraction(BaseModel):
    kind: PageKind
    is_grant_opportunity: bool
    confidence: float = Field(ge=0, le=1)
    title: Quote | None = None
    funder: Quote | None = None
    summary: Annotated[str | None, _clip_text(400)] = Field(None, max_length=400)
    amount: Quote | None = None
    deadline: Quote | None = None
    rolling: bool = False
    eligibility: Annotated[list[Quote], _clip_list(5)] = Field(default=[], max_length=5)
    eligibility_summary: Annotated[str | None, _clip_text(300)] = Field(None, max_length=300)
    needs_more_detail: bool = False
    detail_link_index: int | None = Field(None, ge=1, le=40)


class Point(BaseModel):
    text: Annotated[str, _clip_text(160)] = Field(min_length=3, max_length=160)
    refs: Annotated[list[str], _clip_list(4)] = Field(default=[], max_length=4)  # "W2", "P1"


class FitAssessment(BaseModel):
    fit_score: int = Field(ge=0, le=100)
    reasons: Annotated[list[Point], _clip_list(6)] = Field(
        min_length=1, max_length=6
    )  # code keeps 4
    concerns: Annotated[list[Point], _clip_list(5)] = Field(
        default=[], max_length=5
    )  # code keeps 3
    eligibility_blocker: str | None = None  # a W# id
