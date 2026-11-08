"""Hackathon contracts (H0 section 4): discovery jobs, grant candidates, citations, sessions."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from hope_core.money import Money
from hope_core.schemas.common import Contract

CandidateStatus = Literal["new", "saved", "passed"]
JobStatus = Literal["queued", "running", "done", "failed"]


class Citation(Contract):
    citation_id: str = Field(description='"c1", "c2"... unique within its parent')
    kind: Literal["web", "profile"]
    url: str | None = None
    title: str | None = None
    quote: str = Field(max_length=500, description="exact supporting text")
    profile_path: str | None = Field(None, description='e.g. "mission.mission_statement"')
    retrieved_at: datetime | None = None


class DiscoveryProgress(Contract):
    queries_total: int = 0
    queries_done: int = 0
    pages_read: int = 0
    candidates_found: int = 0
    current_step: str = ""


class DiscoveryJob(Contract):
    job_id: UUID
    status: JobStatus
    queries: list[str] = []
    progress: DiscoveryProgress
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class GrantCandidate(Contract):
    grant_id: UUID
    title: str
    funder: str
    url: str = Field(description="canonical grant page")
    summary: str = Field(description="1-3 plain-English sentences; may contain [cN] markers")
    amount_text: str | None = Field(None, description='quoted, e.g. "up to $50,000"')
    amount_min: Money | None = Field(
        None, description="parsed by code; lower end of a range, else None"
    )
    amount_max: Money | None = Field(None, description="parsed by code, integer minor units")
    deadline_text: str | None = None
    deadline: date | None = Field(None, description="parsed by code; None for rolling or unknown")
    eligibility_summary: str | None = None
    fit_score: int = Field(ge=0, le=100)
    fit_reasons: list[str] = []
    concerns: list[str] = []
    citations: list[Citation] = []
    status: CandidateStatus = "new"
    found_by_job_id: UUID | None = None
    discovered_at: datetime


class UserView(Contract):
    user_id: UUID
    email: str
    display_name: str


class MeView(UserView):
    agency_id: UUID
    onboarding_complete: bool
