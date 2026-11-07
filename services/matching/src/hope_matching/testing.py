"""Deterministic fixtures for matching tests: fixed ids and clock, mock judge gateway."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from hope_core.model_gateway import Message, MockProvider, ModelGateway
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.grant_opportunity import Deadlines, ExtractedDeadline, GrantOpportunity
from hope_core.testing import factories

from hope_matching.alignment import JudgeSample
from hope_matching.contracts import RUBRIC

NOW = datetime(2027, 1, 4, 12, tzinfo=UTC)
AGENCY_ID = UUID("00000000-0000-4000-8000-0000000000a1")


def profile(**overrides: Any) -> AgencyProfile:
    return factories.agency_profile(**({"agency_id": AGENCY_ID} | overrides))


def due_in(days: int) -> Deadlines:
    return Deadlines(
        application_due=ExtractedDeadline(
            value=NOW + timedelta(days=days),
            timezone="America/New_York",
            confidence=0.97,
            evidence=[factories.evidence(3)],
        )
    )


def opportunity(n: int = 1, days: int = 45, **overrides: Any) -> GrantOpportunity:
    oid = UUID(f"00000000-0000-4000-8000-{n:012d}")
    return factories.grant_opportunity(opportunity_id=oid, deadlines=due_in(days), **overrides)


Judge = Callable[[int, list[str]], dict[str, Any]]


def scores_judge(scores: dict[str, list[float]] | float = 80.0) -> Judge:
    """Responder citing the first retrieved id; per-dimension scores per sample (1-based)."""

    def judge(sample: int, ids: list[str]) -> dict[str, Any]:
        def score(dim: str) -> float:
            return scores if isinstance(scores, float) else scores.get(dim, [60.0] * 3)[sample - 1]

        return {
            "dimensions": [
                {"dimension": d, "score": score(d), "evidence_ids": ids[:1], "rationale": f"{d} ok"}
                for d in RUBRIC
            ]
        }

    return judge


def gateway(judge: Judge | None = None) -> ModelGateway:
    provider = MockProvider()
    judge = judge or scores_judge()

    def respond(messages: list[Message], _schema: dict[str, Any]) -> dict[str, Any]:
        ids = re.findall(r"^\[([^\]]+)\]", messages[2].content, re.MULTILINE)
        found = re.search(r"sample (\d+)", messages[-1].content)
        sample = int(found.group(1)) if found else 1
        return judge(sample, ids)

    provider.register(JudgeSample, respond)
    return ModelGateway([provider])
