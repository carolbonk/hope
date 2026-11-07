from typing import Any

import pytest
from hope_budget.framework import (
    FrameworkGenerator,
    FrameworkNeedsReviewError,
    FrameworkStructure,
    LineStructure,
    MissingCeilingError,
    drafted_envelope,
    framework_hash,
)
from hope_budget.resolver import InMemoryCostBasisResolver
from hope_budget.testing import SAMPLE_RECORDS, provenance
from hope_core.model_gateway import Message, MockProvider, ModelGateway
from hope_core.money import Money
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.grant_opportunity import GrantOpportunity, Requirements, RequirementSection
from hope_core.testing.factories import TENANT_A, agency_profile, grant_opportunity
from hope_core.topics import EventType
from pydantic import ValidationError

SCOPE: dict[str, Any] = {
    "project_title": "STEM Mentors",
    "program_ids": ["prog-stem"],
    "goals": [
        {
            "goal_id": "G1",
            "statement": "Grow STEM confidence",
            "objectives": [
                {
                    "objective_id": "O1",
                    "smart_statement": "Mentor youth weekly through the year",
                    "kpis": [{"metric": "youth mentored"}],
                    "activities": [{"activity_id": "A1", "description": "Weekly lab"}],
                }
            ],
        }
    ],
    "logic_model": {"inputs": ["mentors"], "outputs": ["sessions"]},
    "requirement_coverage": [
        {"section_id": "narrative", "covered_by": ["O1"], "status": "covered"},
        {"section_id": "invented", "status": "covered"},
    ],
}
LINES: list[dict[str, Any]] = [
    {
        "line_id": "pm",
        "category": "personnel",
        "cost_basis_ref": "hris:position:PM-02",
        "effort_pct_bps": 5000,
    },
    {
        "line_id": "coord",
        "category": "personnel",
        "cost_basis_ref": "hris:position:CO-01",
        "effort_pct_bps": 10000,
    },
    {
        "line_id": "travel",
        "category": "travel",
        "cost_basis_ref": "erp:travel:mileage-trip",
        "quantity": "3",
    },
    {"line_id": "robot", "category": "equipment", "cost_basis_ref": "erp:vendor-quote:Q-118"},
]


def structure(lines: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"scope": SCOPE, "line_items": lines or LINES}


def opportunity(**funding: Any) -> GrantOpportunity:
    base = grant_opportunity(
        requirements=Requirements(
            sections=[
                RequirementSection(section_id="narrative", title="Project Narrative"),
                RequirementSection(section_id="budget", title="Budget Justification"),
            ]
        )
    )
    return base.model_copy(update={"funding": base.funding.model_copy(update=funding)})


def profile() -> AgencyProfile:
    base = agency_profile()
    fin = base.financials.model_copy(update={"provenance": provenance("profile")})
    return base.model_copy(update={"financials": fin})


def generator(*responses: dict[str, Any]) -> tuple[FrameworkGenerator, list[list[Message]]]:
    seen: list[list[Message]] = []
    mock = MockProvider()

    def respond(messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
        seen.append(messages)
        return responses[min(len(seen), len(responses)) - 1]

    mock.register(FrameworkStructure, respond)
    resolver = InMemoryCostBasisResolver(SAMPLE_RECORDS)
    return FrameworkGenerator(ModelGateway([mock]), resolver), seen


def test_response_model_has_no_amount_fields() -> None:
    schema = str(FrameworkStructure.model_json_schema()).lower()
    for forbidden in ("amount", "_minor", "unit_rate", "total", "price", "cost'"):
        assert forbidden not in schema
    with pytest.raises(ValidationError):
        LineStructure.model_validate({**LINES[2], "amount_minor": 999})


def test_draft_framework() -> None:
    gen, seen = generator(structure())
    opp, prof = opportunity(), profile()
    draft = gen.draft(opp, prof)
    fw = draft.framework
    assert draft.attempts == 1 and not draft.needs_review
    assert fw.status == "draft" and fw.version == 1
    assert fw.opportunity_id == opp.opportunity_id and fw.agency_id == prof.agency_id
    assert fw.budget.computed_by == "budget-engine"
    assert (
        fw.budget.totals.request_minor == 128_336_82
    )  # 117,397.11 direct + 10% of 109,397.11 MTDC
    assert fw.content_hash == framework_hash(fw)
    assert [(c.section_id, c.status) for c in fw.scope.requirement_coverage] == [
        ("narrative", "covered"),
        ("budget", "missing"),
    ]
    user = seen[0][1].content
    assert "<untrusted" in user and "Youth STEM Mentoring" in user
    assert "72000" not in user and "7200000" not in user  # rates never reach the model


def test_draft_runs_solver_over_ceiling() -> None:
    gen, _ = generator(structure())
    draft = gen.draft(opportunity(award_ceiling=Money.from_decimal("100000")), profile())
    ledger = draft.framework.budget
    assert ledger.totals.request_minor <= 100_000_00
    assert any(c.rule == "award_ceiling" and c.status == "adjusted" for c in ledger.cap_checks)
    assert draft.framework.extra is not None
    assert draft.framework.extra["solver"]["adjustments"]


def test_repairs_invalid_structure() -> None:
    bad = [{**LINES[0], "cost_basis_ref": "hris:position:NOPE"}]
    gen, seen = generator(structure(bad), structure())
    draft = gen.draft(opportunity(), profile())
    assert draft.attempts == 2
    assert "does not resolve" in seen[1][-1].content


def test_gives_up_after_repairs() -> None:
    bad_scope = {
        **SCOPE,
        "goals": [
            {
                **SCOPE["goals"][0],
                "objectives": [
                    {
                        **SCOPE["goals"][0]["objectives"][0],
                        "kpis": [{"metric": "m", "baseline_ref": "x"}],
                    }
                ],
            }
        ],
    }
    gen, seen = generator({"scope": bad_scope, "line_items": LINES})
    with pytest.raises(FrameworkNeedsReviewError, match="unknown baseline_ref x"):
        gen.draft(opportunity(), profile())
    assert len(seen) == 3


def test_requires_ceiling() -> None:
    gen, seen = generator(structure())
    with pytest.raises(MissingCeilingError):
        gen.draft(opportunity(award_ceiling=None), profile())
    assert not seen


def test_drafted_envelope() -> None:
    gen, _ = generator(structure())
    fw = gen.draft(opportunity(), profile()).framework
    env = drafted_envelope(fw, TENANT_A)
    assert env.event_type == EventType.FRAMEWORK_DRAFTED
    assert env.producer.agent_id == "A7"
    assert env.payload is not None
    assert env.payload["budget"]["computed_by"] == "budget-engine"
