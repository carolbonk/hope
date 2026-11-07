from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from hope_core.money import Money
from hope_core.schemas.common import Evidence
from hope_core.schemas.grant_opportunity import Source
from hope_core.testing.factories import grant_opportunity
from hope_ingestion.connectors.base import SourceFacts
from hope_ingestion.parsing.extraction import Finding
from hope_ingestion.policy import (
    INTERNAL_DEADLINE_BUFFER,
    W_INDIRECT_ASSUMED,
    W_TIME_ASSUMED,
    apply_policy,
    field_diff,
    internal_deadline,
)

ET = ZoneInfo("America/New_York")
SOURCE = Source(system="upload", source_id="rfp-1")


def finding(field: str, quote: str, page: int = 1) -> Finding:
    return Finding(field, quote, 0.9, Evidence(artifact_id="art", page=page, quote=quote))


def run(*findings: Finding, facts: SourceFacts | None = None):  # type: ignore[no-untyped-def]
    return apply_policy(
        opportunity_id=uuid4(),
        source=SOURCE,
        findings=list(findings),
        facts=facts,
        facts_artifact_id="meta" if facts else None,
    )


def test_missing_deadline_blocks() -> None:
    result = run(finding("funding.award_ceiling", "Award ceiling: $100,000"))
    assert [(i.field, i.reason) for i in result.blocking] == [
        ("deadlines.application_due", "missing")
    ]
    assert result.opportunity.parse_quality.missing_critical_fields == ["deadlines.application_due"]


def test_date_only_deadline_becomes_2359_with_72h_buffer() -> None:
    result = run(finding("deadlines.application_due", "Applications are due May 1, 2027."))
    due = result.opportunity.deadlines.application_due
    assert due is not None
    assert due.value == datetime(2027, 5, 1, 23, 59, tzinfo=ET)
    assert due.timezone == "America/New_York"
    assert W_TIME_ASSUMED in result.opportunity.parse_quality.warnings
    assert any(
        w.startswith("deadline.timezone_assumed") for w in result.opportunity.parse_quality.warnings
    )
    assert result.internal_deadline == due.value - INTERNAL_DEADLINE_BUFFER
    assert internal_deadline(result.opportunity) == due.value - timedelta(hours=72)
    assert not result.blocking


def test_funder_timezone_from_source_facts() -> None:
    facts = SourceFacts(funder_timezone="America/Denver")
    result = run(
        finding("deadlines.application_due", "Applications are due May 1, 2027."), facts=facts
    )
    due = result.opportunity.deadlines.application_due
    assert due is not None and due.value == datetime(
        2027, 5, 1, 23, 59, tzinfo=ZoneInfo("America/Denver")
    )


def test_missing_indirect_policy_assumes_not_allowed() -> None:
    result = run(finding("deadlines.application_due", "Due May 1, 2027 5 PM ET"))
    policy = result.opportunity.funding.indirect_cost_policy
    assert policy is not None and policy.allowed is False
    assert W_INDIRECT_ASSUMED in result.opportunity.parse_quality.warnings
    assert any("indirect" in q for q in result.questions_to_funder)
    assert result.internal_deadline == datetime(2027, 5, 1, 17, 0, tzinfo=ET)


def test_missing_ceiling_is_flagged_but_not_blocking() -> None:
    result = run(finding("deadlines.application_due", "Due May 1, 2027 5 PM ET"))
    quality = result.opportunity.parse_quality
    assert quality.missing_critical_fields == ["funding.award_ceiling"]
    assert any(w.startswith("funding.award_ceiling_missing") for w in quality.warnings)
    assert not result.blocking


def test_conflicting_deadlines_block_with_both_candidates() -> None:
    result = run(
        finding("deadlines.application_due", "Applications are due May 1, 2027.", page=2),
        finding("deadlines.application_due", "Applications are due May 8, 2027.", page=9),
    )
    issue = result.blocking[0]
    assert (issue.field, issue.reason) == ("deadlines.application_due", "conflict")
    assert len(issue.candidates) == 2
    assert {c.evidence[0].page for c in issue.candidates} == {2, 9}
    assert result.opportunity.deadlines.application_due is None


def test_conflicting_amounts_block() -> None:
    result = run(
        finding("deadlines.application_due", "Due May 1, 2027 5 PM ET"),
        finding("funding.award_ceiling", "Awards of up to $100,000"),
        finding("funding.award_ceiling", "Maximum award $150,000"),
    )
    assert [(i.field, i.reason) for i in result.blocking] == [("funding.award_ceiling", "conflict")]


def test_date_only_fact_agrees_with_timed_document_value() -> None:
    facts = SourceFacts(
        funder_type="federal",
        funder_timezone="America/New_York",
        application_due=datetime(2027, 5, 1, tzinfo=ET),
        award_ceiling=Money.from_decimal("100000"),
        quotes={"awardCeiling": "awardCeiling: 100000"},
    )
    result = run(
        finding("deadlines.application_due", "Applications due May 1, 2027 at 11:59 PM ET"),
        finding("funding.award_ceiling", "Awards of up to $100,000"),
        facts=facts,
    )
    assert not result.blocking
    due = result.opportunity.deadlines.application_due
    assert due is not None and due.value == datetime(2027, 5, 1, 23, 59, tzinfo=ET)
    assert {e.artifact_id for e in due.evidence} == {"art", "meta"}
    assert W_TIME_ASSUMED not in result.opportunity.parse_quality.warnings
    assert result.opportunity.funding.award_ceiling == Money.from_decimal("100000")
    assert len(result.opportunity.funding.evidence) == 2


def test_field_diff_ignores_provenance() -> None:
    before = grant_opportunity()
    after = before.model_copy(
        update={
            "title": "Amended title",
            "funding": before.funding.model_copy(
                update={"award_ceiling": Money.from_decimal("300000")}
            ),
        }
    )
    changes = {
        c.path: c for c in field_diff(before.model_dump(mode="json"), after.model_dump(mode="json"))
    }
    assert set(changes) == {"title", "funding.award_ceiling.amount_minor"}
    assert changes["funding.award_ceiling.amount_minor"].before == 25_000_000
    assert changes["funding.award_ceiling.amount_minor"].after == 30_000_000
    assert field_diff(before.model_dump(mode="json"), before.model_dump(mode="json")) == []
