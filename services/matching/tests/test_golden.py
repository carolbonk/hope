"""Golden matrix: fixed inputs must keep producing the same scores. Regenerate deliberately
with `HOPE_UPDATE_GOLDEN=1 uv run pytest services/matching/tests/test_golden.py`."""

import json
import os
from pathlib import Path

from hope_core.money import Money
from hope_core.schemas.agency_profile import Capacity, GrantHistoryItem
from hope_core.schemas.grant_opportunity import CostShare, Requirements, RequirementSection
from hope_matching.alignment import assess_alignment
from hope_matching.config import MatchingConfig
from hope_matching.contracts import RUBRIC
from hope_matching.eligibility import evaluate_eligibility
from hope_matching.recommender import Assessed, build_matrix
from hope_matching.testing import NOW, gateway, opportunity, profile, scores_judge

GOLDEN = Path(__file__).parent / "golden" / "matrix.json"


def golden_matrix() -> dict[str, object]:
    p = profile(
        capacity=Capacity(
            monthly_hours_available=90,
            max_concurrent_applications=3,
            cost_share_capacity=Money.from_decimal("20000"),
        ),
        grant_history=[
            GrantHistoryItem(
                funder_id="Administration for Children and Families", outcome="awarded"
            )
        ],
    )
    base = opportunity()
    reqs = Requirements(
        sections=[RequirementSection(section_id="n", title="Narrative", page_limit=15)],
        forms=["SF-424", "SF-424A"],
    )
    opps = [
        opportunity(1, requirements=reqs),
        opportunity(2, days=20),
        opportunity(
            3,
            funding=base.funding.model_copy(
                update={"cost_share": CostShare(required=True, ratio_bps=2500)}
            ),
        ),
        opportunity(4, eligibility=base.eligibility.model_copy(update={"applicant_types": ["x"]})),
    ]
    gw = gateway(scores_judge({d: [60.0 + i, 70.0 + i, 65.0 + i] for i, d in enumerate(RUBRIC)}))
    config = MatchingConfig(strategic_keywords=["mentoring"])
    assessed = []
    for o in opps:
        e = evaluate_eligibility(p, o, NOW.date())
        a = assess_alignment(gw, p, o, config) if e.status != "ineligible" else None
        assessed.append(Assessed(o, e, a))
    return build_matrix(p, assessed, config, generated_at=NOW).model_dump(mode="json")


def test_golden_matrix() -> None:
    actual = golden_matrix()
    if os.environ.get("HOPE_UPDATE_GOLDEN"):
        GOLDEN.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
    assert actual == json.loads(GOLDEN.read_text())
