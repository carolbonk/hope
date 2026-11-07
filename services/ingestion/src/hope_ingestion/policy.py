"""Missing-field policy for malformed RFPs (blueprint 8.5), as code.

Inputs are grounded findings from A2 plus structured facts from the source API. Code
resolves them into a GrantOpportunity and a list of blocking issues; any blocking issue
routes the opportunity to NeedsParseReview via `opportunity.parse_incomplete`."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from hope_core.money import Money
from hope_core.schemas.common import Evidence
from hope_core.schemas.grant_opportunity import (
    CRITICAL_FIELDS,
    CostShare,
    Deadlines,
    Eligibility,
    EligibilityClause,
    ExtractedDeadline,
    ExtractedStrings,
    Funder,
    Funding,
    GrantOpportunity,
    IndirectCostPolicy,
    ParseQuality,
    PipelinePath,
    Requirements,
    RequirementSection,
    Source,
)

from hope_ingestion.connectors.base import SourceFacts
from hope_ingestion.contracts import BlockingIssue, Candidate, FieldChange
from hope_ingestion.parsing.extraction import EXTRACTOR_ID, Finding
from hope_ingestion.parsing.validators import (
    DEFAULT_TZ,
    ParsedDeadline,
    find_forms,
    parse_cost_share,
    parse_deadline,
    parse_indirect,
    parse_int,
    parse_money,
    parse_page_limit,
)

INTERNAL_DEADLINE_BUFFER = timedelta(hours=72)
FACT_CONFIDENCE = 0.99
REVIEW_CONFIDENCE = 0.7
SOURCE_EXTRACTOR = "source-api"

W_TIME_ASSUMED = "deadline.time_assumed"
W_TZ_ASSUMED = "deadline.timezone_assumed"
W_INDIRECT_ASSUMED = "funding.indirect_cost_policy_assumed"
W_CEILING_MISSING = "funding.award_ceiling_missing:blocks_budgeting"
INDIRECT_QUESTION = "What indirect cost rate and base are allowed under this opportunity?"
CEILING_QUESTION = "What is the maximum award amount (award ceiling)?"


@dataclass
class Cand[T]:
    value: T
    confidence: float
    evidence: list[Evidence]
    display: str


@dataclass
class PolicyResult:
    opportunity: GrantOpportunity
    blocking: list[BlockingIssue] = field(default_factory=list)
    questions_to_funder: list[str] = field(default_factory=list)
    internal_deadline: datetime | None = None


def internal_deadline(opportunity: GrantOpportunity) -> datetime | None:
    """Working deadline: 72h before an assumed (date-only) due time, else the due time."""
    due = opportunity.deadlines.application_due
    if due is None:
        return None
    assumed = W_TIME_ASSUMED in opportunity.parse_quality.warnings
    return due.value - INTERNAL_DEADLINE_BUFFER if assumed else due.value


def _issue(name: str, groups: list[list[Cand[Any]]]) -> BlockingIssue:
    return BlockingIssue(
        field=name,
        reason="conflict",
        candidates=[
            Candidate(value=g[0].display, evidence=[e for c in g for e in c.evidence])
            for g in groups
        ],
    )


def _merge[T](group: list[Cand[T]]) -> Cand[T]:
    best = max(group, key=lambda c: c.confidence)
    evidence = [e for c in group for e in c.evidence]
    return Cand(best.value, max(c.confidence for c in group), evidence, best.display)


def resolve[T](
    name: str, cands: list[Cand[T]], key: Callable[[T], Hashable]
) -> tuple[Cand[T] | None, BlockingIssue | None]:
    """Agreeing candidates merge their evidence; disagreeing ones block (blueprint 8.5)."""
    groups: dict[Hashable, list[Cand[T]]] = {}
    for cand in cands:
        groups.setdefault(key(cand.value), []).append(cand)
    if len(groups) > 1:
        return None, _issue(name, list(groups.values()))
    return (_merge(next(iter(groups.values()))) if groups else None), None


def resolve_deadline(
    name: str, cands: list[Cand[ParsedDeadline]]
) -> tuple[Cand[ParsedDeadline] | None, BlockingIssue | None]:
    """A date-only value agrees with a timed value on the same local date; the timed one wins."""
    by_date, issue = resolve(name, cands, key=lambda d: d.local_date)
    if issue or by_date is None:
        return by_date, issue
    timed = [c for c in cands if c.value.has_time]
    if not timed:
        return by_date, None
    exact, issue = resolve(name, timed, key=lambda d: d.value)
    if exact is None:
        return None, issue
    return Cand(exact.value, exact.confidence, by_date.evidence, exact.display), None


@dataclass
class _Facts:
    facts: SourceFacts | None
    artifact_id: str | None

    def cand[T](self, key: str, value: T | None) -> list[Cand[T]]:
        if value is None or self.facts is None or self.artifact_id is None:
            return []
        quote = self.facts.quotes.get(key, f"{key}: {value}")[:500]
        evidence = Evidence(artifact_id=self.artifact_id, page=1, quote=quote)
        return [Cand(value, FACT_CONFIDENCE, [evidence], quote)]


def _parsed[T](
    findings: list[Finding], name: str, parse: Callable[[str], T | None]
) -> list[Cand[T]]:
    out: list[Cand[T]] = []
    for f in findings:
        if f.field == name and (value := parse(f.quote)) is not None:
            out.append(Cand(value, f.confidence, [f.evidence], f.quote))
    return out


def _first_text(findings: list[Finding], name: str) -> Finding | None:
    return max((f for f in findings if f.field == name), key=lambda f: f.confidence, default=None)


def _strip_label(text: str) -> str:
    head, sep, tail = text.partition(":")
    return tail.strip() if sep and len(head) <= 30 and tail.strip() else text.strip()


def _extracted_deadline(cand: Cand[ParsedDeadline]) -> ExtractedDeadline:
    extractor = SOURCE_EXTRACTOR if cand.confidence == FACT_CONFIDENCE else EXTRACTOR_ID
    return ExtractedDeadline(
        value=cand.value.value,
        timezone=cand.value.timezone,
        confidence=cand.confidence,
        evidence=cand.evidence,
        extractor=extractor,
    )


def apply_policy(
    *,
    opportunity_id: UUID,
    source: Source,
    findings: list[Finding],
    facts: SourceFacts | None = None,
    facts_artifact_id: str | None = None,
    full_text: str = "",
    pipeline_path: list[PipelinePath] | None = None,
    injection: list[str] | None = None,
    warnings: list[str] | None = None,
    blocking: list[BlockingIssue] | None = None,
) -> PolicyResult:
    src = _Facts(facts, facts_artifact_id)
    tz = (facts.funder_timezone if facts else None) or DEFAULT_TZ
    warn: list[str] = list(warnings or [])
    block: list[BlockingIssue] = list(blocking or [])
    questions: list[str] = []

    def deadline(kind: str) -> ExtractedDeadline | None:
        name = f"deadlines.{kind}"
        cands = _parsed(findings, name, lambda q: parse_deadline(q, tz))
        if kind == "application_due" and facts and facts.application_due:
            fact = ParsedDeadline(facts.application_due, tz, facts.application_due_has_time, False)
            if not fact.has_time:
                fact = parse_deadline(fact.value.date().isoformat(), tz) or fact
            cands += src.cand("responseDate", fact)
        chosen, issue = resolve_deadline(name, cands)
        if issue:
            block.append(issue)
        if chosen is None:
            return None
        if not chosen.value.has_time:
            warn.append(f"{W_TIME_ASSUMED}:{name}")
        if chosen.value.timezone_assumed:
            warn.append(f"{W_TZ_ASSUMED}:{name}")
        return _extracted_deadline(chosen)

    application_due = deadline("application_due")
    if application_due is None and not any(i.field == "deadlines.application_due" for i in block):
        block.append(BlockingIssue(field="deadlines.application_due", reason="missing"))
    if application_due and any(w == f"{W_TIME_ASSUMED}:deadlines.application_due" for w in warn):
        warn.append(W_TIME_ASSUMED)
    deadlines = Deadlines(
        application_due=application_due,
        loi_due=deadline("loi_due"),
        questions_due=deadline("questions_due"),
    )

    funding_evidence: list[Evidence] = []

    def money(name: str, fact_key: str, fact: Money | None) -> Money | None:
        cands = _parsed(findings, f"funding.{name}", parse_money) + src.cand(fact_key, fact)
        chosen, issue = resolve(
            f"funding.{name}", cands, key=lambda m: (m.amount_minor, m.currency)
        )
        if issue:
            block.append(issue)
        if chosen is None:
            return None
        funding_evidence.extend(chosen.evidence)
        return chosen.value

    ceiling = money("award_ceiling", "awardCeiling", facts.award_ceiling if facts else None)
    floor = money("award_floor", "awardFloor", facts.award_floor if facts else None)
    total = money(
        "total_program_funding",
        "estimatedFunding",
        facts.total_program_funding if facts else None,
    )
    if ceiling is None:
        warn.append(W_CEILING_MISSING)
        questions.append(CEILING_QUESTION)

    indirect_cands = _parsed(findings, "funding.indirect_cost_policy", parse_indirect)
    indirect, issue = resolve(
        "funding.indirect_cost_policy", indirect_cands, key=lambda p: (p.allowed, p.cap_bps)
    )
    if issue:
        block.append(issue)
    if indirect is None:
        indirect_policy = IndirectCostPolicy(allowed=False, base="unspecified")
        if not issue:
            warn.append(W_INDIRECT_ASSUMED)
            questions.append(INDIRECT_QUESTION)
    else:
        indirect_policy = indirect.value
        funding_evidence.extend(indirect.evidence)

    share_cands = _parsed(findings, "funding.cost_share", parse_cost_share)
    if facts and facts.cost_share_required is not None:
        share_cands += src.cand("costSharing", CostShare(required=facts.cost_share_required))
    share, issue = resolve("funding.cost_share", share_cands, key=lambda s: s.required)
    if issue:
        block.append(issue)
    if share is not None:
        funding_evidence.extend(share.evidence)
        detailed = [c.value for c in share_cands if c.value.ratio_bps or c.value.in_kind_allowed]
        cost_share: CostShare | None = detailed[0] if detailed else share.value
    else:
        cost_share = None

    awards = _first_text(findings, "funding.expected_awards")
    expected_awards = (facts.expected_awards if facts else None) or (
        parse_int(awards.quote) if awards else None
    )

    title_f = _first_text(findings, "title")
    title = (facts.title if facts else None) or (_strip_label(title_f.quote) if title_f else None)
    if not title:
        title = f"Untitled opportunity {source.source_id}"
        warn.append("title_missing")
    funder_f = _first_text(findings, "funder_name")
    funder_name = (facts.funder_name if facts else None) or (
        _strip_label(funder_f.quote) if funder_f else None
    )
    if not funder_name:
        funder_name = "Unknown funder"
        warn.append("funder_missing")
    summary_f = _first_text(findings, "summary")

    clauses = [
        EligibilityClause(
            text=f.quote,
            evidence=[f.evidence],
            rule_status="draft" if f.confidence >= REVIEW_CONFIDENCE else "needs_review",
        )
        for f in findings
        if f.field == "eligibility.clauses"
    ]
    priorities = [f for f in findings if f.field == "funding_priorities"]
    lowered = full_text.lower()
    registrations: list[Any] = [
        reg
        for reg, needle in (("sam", "sam.gov"), ("uei", "uei"), ("grants_gov", "grants.gov"))
        if needle in lowered
    ]
    sections = [
        RequirementSection(
            section_id=f"req-{i}",
            title=f.label or f.quote[:80],
            instructions=f.quote,
            page_limit=parse_page_limit(f.quote),
        )
        for i, f in enumerate((f for f in findings if f.field == "requirements.sections"), 1)
    ]

    missing = [
        name
        for name, value in (
            ("deadlines.application_due", application_due),
            ("funding.award_ceiling", ceiling),
        )
        if name in CRITICAL_FIELDS and value is None
    ]
    confidences = [c for c in (application_due.confidence if application_due else None,) if c]
    overall = min(confidences) if confidences else 0.3
    if ceiling is None:
        overall = min(overall, 0.8)
    if injection:
        overall = min(overall, 0.5)
        warn.extend(f"injection_suspected:{s}" for s in injection)
    if block:
        overall = min(overall, 0.5)

    opportunity = GrantOpportunity(
        opportunity_id=opportunity_id,
        source=source,
        title=title,
        funder=Funder(
            name=funder_name,
            type=facts.funder_type if facts else "other",
            aln=facts.aln if facts else [],
            contact_email=facts.contact_email if facts else None,
        ),
        summary=(facts.summary if facts else None)
        or (_strip_label(summary_f.quote) if summary_f else None),
        funding_priorities=ExtractedStrings(
            value=[p.quote for p in priorities],
            confidence=min(p.confidence for p in priorities),
            evidence=[p.evidence for p in priorities],
            extractor=EXTRACTOR_ID,
        )
        if priorities
        else None,
        deadlines=deadlines,
        funding=Funding(
            award_ceiling=ceiling,
            award_floor=floor,
            total_program_funding=total,
            expected_awards=expected_awards,
            cost_share=cost_share,
            indirect_cost_policy=indirect_policy,
            evidence=funding_evidence,
        ),
        eligibility=Eligibility(
            applicant_types=facts.applicant_types if facts else [],
            required_registrations=registrations,
            clauses=clauses,
        ),
        requirements=Requirements(
            sections=sections,
            forms=find_forms(full_text),
            submission_channel="grants_gov" if source.system == "grants_gov" else None,
        ),
        parse_quality=ParseQuality(
            overall_confidence=overall,
            missing_critical_fields=missing,
            warnings=list(dict.fromkeys(warn)),
            injection_suspected=bool(injection),
            pipeline_path=list(dict.fromkeys(pipeline_path or ["native_text"])),
        ),
    )
    result = PolicyResult(opportunity, block, questions)
    result.internal_deadline = internal_deadline(opportunity)
    return result


VOLATILE_KEYS = frozenset(
    {"evidence", "confidence", "extractor", "artifact_ids", "opportunity_id", "parse_quality"}
)


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in VOLATILE_KEYS or (prefix == "source." and key == "amendment_seq"):
                continue
            out |= _flatten(item, f"{prefix}{key}.")
        return out
    if isinstance(value, list):
        return {prefix.rstrip("."): [_flatten(v) if isinstance(v, dict) else v for v in value]}
    return {prefix.rstrip("."): value}


def field_diff(before: dict[str, Any], after: dict[str, Any]) -> list[FieldChange]:
    """Red-line between two normalized versions, ignoring provenance-only changes."""
    old, new = _flatten(before), _flatten(after)
    return [
        FieldChange(path=path, before=old.get(path), after=new.get(path))
        for path in sorted(old.keys() | new.keys())
        if old.get(path) != new.get(path)
    ]
