"""Response models for the three discovery model calls. Local to this package (H2 section E).

None of them has a money, date, status or URL field that code trusts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PlannedQuery(BaseModel):
    query: str = Field(min_length=3, max_length=120)
    rationale: str = Field(max_length=140)
    profile_refs: list[str] = Field(default=[], max_length=4)  # "P1", "P3"


class QueryPlan(BaseModel):
    queries: list[PlannedQuery] = Field(min_length=1, max_length=10)  # code keeps 5-8


class Quote(BaseModel):
    text: str = Field(min_length=3, max_length=300)
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
    summary: str | None = Field(None, max_length=400)
    amount: Quote | None = None
    deadline: Quote | None = None
    rolling: bool = False
    eligibility: list[Quote] = Field(default=[], max_length=5)
    eligibility_summary: str | None = Field(None, max_length=300)
    needs_more_detail: bool = False
    detail_link_index: int | None = Field(None, ge=1, le=40)


class Point(BaseModel):
    text: str = Field(min_length=3, max_length=160)
    refs: list[str] = Field(default=[], max_length=4)  # "W2", "P1"


class FitAssessment(BaseModel):
    fit_score: int = Field(ge=0, le=100)
    reasons: list[Point] = Field(min_length=1, max_length=6)  # code keeps 4
    concerns: list[Point] = Field(default=[], max_length=5)  # code keeps 3
    eligibility_blocker: str | None = None  # a W# id
