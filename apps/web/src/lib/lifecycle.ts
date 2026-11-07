// Mirror of hope_core.schemas.lifecycle, hope_core.schemas.hitl.STEP_UP_MFA_GATES and
// hope_core.schemas.agency_profile.PROTECTED_PROFILE_PATHS, which are not yet exported to
// @hope/schemas. `lifecycle.test.ts` parses the Python sources and fails on any drift.
import type { AgencyProfile, Gate } from "@hope/schemas";

export const OPPORTUNITY_STATES = [
  "Ingested",
  "NeedsParseReview",
  "Normalized",
  "NeedsEligibilityReview",
  "Screened",
  "Recommended",
  "AwaitingGoNoGo",
  "Planning",
  "AwaitingBudgetSignoff",
  "Drafting",
  "InReview",
  "AwaitingCompliance",
  "AwaitingExecApproval",
  "Packaging",
  "AwaitingSubmissionAuth",
  "Submitted",
  "SubmissionError",
  "Awarded",
  "PostAward",
  "NotAwarded",
  "Declined",
  "Expired",
  "Ineligible",
  "Archived",
  "Discarded",
] as const;

export type OpportunityState = (typeof OPPORTUNITY_STATES)[number];

export const TRANSITIONS: Readonly<Partial<Record<OpportunityState, readonly OpportunityState[]>>> = {
  Ingested: ["Normalized", "NeedsParseReview"],
  NeedsParseReview: ["Normalized", "Discarded"],
  Normalized: ["Ineligible", "Screened", "NeedsEligibilityReview"],
  NeedsEligibilityReview: ["Screened", "Ineligible"],
  Screened: ["Recommended", "Archived"],
  Recommended: ["AwaitingGoNoGo"],
  AwaitingGoNoGo: ["Declined", "Planning"],
  Planning: ["AwaitingBudgetSignoff"],
  AwaitingBudgetSignoff: ["Planning", "Drafting"],
  Drafting: ["InReview"],
  InReview: ["Drafting", "AwaitingCompliance"],
  AwaitingCompliance: ["Drafting", "AwaitingExecApproval"],
  AwaitingExecApproval: ["Drafting", "Packaging"],
  Packaging: ["AwaitingSubmissionAuth", "Drafting"],
  AwaitingSubmissionAuth: ["Submitted"],
  Submitted: ["SubmissionError", "Awarded", "NotAwarded"],
  SubmissionError: ["Packaging"],
  Awarded: ["PostAward"],
};

export const TERMINAL_STATES: ReadonlySet<OpportunityState> = new Set([
  "PostAward",
  "NotAwarded",
  "Declined",
  "Expired",
  "Ineligible",
  "Archived",
  "Discarded",
]);

const EXPIRY_EXEMPT: ReadonlySet<OpportunityState> = new Set(["Submitted", "SubmissionError", "Awarded"]);

export function nextStates(current: OpportunityState): OpportunityState[] {
  const next = [...(TRANSITIONS[current] ?? [])];
  if (!TERMINAL_STATES.has(current) && !EXPIRY_EXEMPT.has(current)) next.push("Expired");
  return next;
}

/** The main path through the lifecycle, used to lay out the timeline. */
export const HAPPY_PATH: readonly OpportunityState[] = [
  "Ingested",
  "Normalized",
  "Screened",
  "Recommended",
  "AwaitingGoNoGo",
  "Planning",
  "AwaitingBudgetSignoff",
  "Drafting",
  "InReview",
  "AwaitingCompliance",
  "AwaitingExecApproval",
  "Packaging",
  "AwaitingSubmissionAuth",
  "Submitted",
  "Awarded",
  "PostAward",
];

/** Gate that holds a workflow in a given waiting state. */
export const GATE_FOR_STATE: Readonly<Partial<Record<OpportunityState, Gate>>> = {
  NeedsParseReview: "REVIEW-PARSE",
  NeedsEligibilityReview: "REVIEW-ELIGIBILITY",
  AwaitingGoNoGo: "HITL-1",
  AwaitingBudgetSignoff: "HITL-2",
  AwaitingCompliance: "HITL-3",
  AwaitingExecApproval: "HITL-4",
  AwaitingSubmissionAuth: "HITL-5",
};

export const STEP_UP_MFA_GATES: ReadonlySet<Gate> = new Set<Gate>(["HITL-2", "HITL-3", "HITL-5"]);

export type ProfileSection = keyof AgencyProfile;

export const PROTECTED_PROFILE_PATHS: readonly ProfileSection[] = ["legal", "financials", "approval_hierarchy"];

export const isProtectedSection = (section: ProfileSection): boolean =>
  PROTECTED_PROFILE_PATHS.includes(section);

export function humanizeState(state: OpportunityState): string {
  return state
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace("Go No Go", "Go / No-Go")
    .replace("Exec ", "Executive ")
    .replace("Auth", "Authorization");
}
