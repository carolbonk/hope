"""Opportunity lifecycle state machine (blueprint 4.3). Workflow code and the web app both
read this table, so transitions are defined exactly once."""

from __future__ import annotations

from enum import StrEnum


class OpportunityState(StrEnum):
    INGESTED = "Ingested"
    NEEDS_PARSE_REVIEW = "NeedsParseReview"
    NORMALIZED = "Normalized"
    NEEDS_ELIGIBILITY_REVIEW = "NeedsEligibilityReview"
    SCREENED = "Screened"
    RECOMMENDED = "Recommended"
    AWAITING_GO_NO_GO = "AwaitingGoNoGo"
    PLANNING = "Planning"
    AWAITING_BUDGET_SIGNOFF = "AwaitingBudgetSignoff"
    DRAFTING = "Drafting"
    IN_REVIEW = "InReview"
    AWAITING_COMPLIANCE = "AwaitingCompliance"
    AWAITING_EXEC_APPROVAL = "AwaitingExecApproval"
    PACKAGING = "Packaging"
    AWAITING_SUBMISSION_AUTH = "AwaitingSubmissionAuth"
    SUBMITTED = "Submitted"
    SUBMISSION_ERROR = "SubmissionError"
    AWARDED = "Awarded"
    POST_AWARD = "PostAward"
    NOT_AWARDED = "NotAwarded"
    DECLINED = "Declined"
    EXPIRED = "Expired"
    INELIGIBLE = "Ineligible"
    ARCHIVED = "Archived"
    DISCARDED = "Discarded"


S = OpportunityState

TRANSITIONS: dict[OpportunityState, frozenset[OpportunityState]] = {
    S.INGESTED: frozenset({S.NORMALIZED, S.NEEDS_PARSE_REVIEW}),
    S.NEEDS_PARSE_REVIEW: frozenset({S.NORMALIZED, S.DISCARDED}),
    S.NORMALIZED: frozenset({S.INELIGIBLE, S.SCREENED, S.NEEDS_ELIGIBILITY_REVIEW}),
    S.NEEDS_ELIGIBILITY_REVIEW: frozenset({S.SCREENED, S.INELIGIBLE}),
    S.SCREENED: frozenset({S.RECOMMENDED, S.ARCHIVED}),
    S.RECOMMENDED: frozenset({S.AWAITING_GO_NO_GO}),
    S.AWAITING_GO_NO_GO: frozenset({S.DECLINED, S.PLANNING}),
    S.PLANNING: frozenset({S.AWAITING_BUDGET_SIGNOFF}),
    S.AWAITING_BUDGET_SIGNOFF: frozenset({S.PLANNING, S.DRAFTING}),
    S.DRAFTING: frozenset({S.IN_REVIEW}),
    S.IN_REVIEW: frozenset({S.DRAFTING, S.AWAITING_COMPLIANCE}),
    S.AWAITING_COMPLIANCE: frozenset({S.DRAFTING, S.AWAITING_EXEC_APPROVAL}),
    S.AWAITING_EXEC_APPROVAL: frozenset({S.DRAFTING, S.PACKAGING}),
    S.PACKAGING: frozenset({S.AWAITING_SUBMISSION_AUTH, S.DRAFTING}),
    S.AWAITING_SUBMISSION_AUTH: frozenset({S.SUBMITTED}),
    S.SUBMITTED: frozenset({S.SUBMISSION_ERROR, S.AWARDED, S.NOT_AWARDED}),
    S.SUBMISSION_ERROR: frozenset({S.PACKAGING}),
    S.AWARDED: frozenset({S.POST_AWARD}),
}

TERMINAL: frozenset[OpportunityState] = frozenset(
    {S.POST_AWARD, S.NOT_AWARDED, S.DECLINED, S.EXPIRED, S.INELIGIBLE, S.ARCHIVED, S.DISCARDED}
)

PRE_SUBMISSION_ACTIVE: frozenset[OpportunityState] = frozenset(
    s
    for s in OpportunityState
    if s not in TERMINAL and s not in {S.SUBMITTED, S.SUBMISSION_ERROR, S.AWARDED}
)
"""States that move to Expired when the internal deadline passes (global guard)."""


class InvalidTransitionError(ValueError):
    pass


def can_transition(current: OpportunityState, target: OpportunityState) -> bool:
    if target is S.EXPIRED:
        return current in PRE_SUBMISSION_ACTIVE
    return target in TRANSITIONS.get(current, frozenset())


def assert_transition(current: OpportunityState, target: OpportunityState) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(f"{current} -> {target} is not allowed")
