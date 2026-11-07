import type { Gate, HitlDecision } from "@hope/schemas";
import type { OpportunityState } from "./lifecycle";

export type Decision = HitlDecision["decision"];
export type DecisionTone = "primary" | "neutral" | "danger";

export interface DecisionOption {
  decision: Decision;
  label: string;
  tone: DecisionTone;
  /** Where the workflow goes after this decision (blueprint 4.3); undefined keeps the state. */
  next?: OpportunityState;
  requiresComment?: boolean;
}

interface GateInfo {
  title: string;
  options: DecisionOption[];
}

const standard = (approveLabel: string, onApprove: OpportunityState, onReturn: OpportunityState): DecisionOption[] => [
  { decision: "approve", label: approveLabel, tone: "primary", next: onApprove },
  { decision: "request_changes", label: "Request changes", tone: "neutral", next: onReturn, requiresComment: true },
  { decision: "reject", label: "Reject", tone: "danger", next: onReturn, requiresComment: true },
];

export const GATES: Record<Gate, GateInfo> = {
  "HITL-0": {
    title: "Profile commit",
    options: [
      { decision: "approve", label: "Approve change", tone: "primary" },
      { decision: "request_changes", label: "Request changes", tone: "neutral", requiresComment: true },
      { decision: "reject", label: "Reject", tone: "danger", requiresComment: true },
    ],
  },
  "HITL-1": {
    title: "Go / No-Go",
    options: [
      { decision: "go", label: "GO", tone: "primary", next: "Planning" },
      { decision: "defer", label: "Defer", tone: "neutral" },
      { decision: "no_go", label: "NO-GO", tone: "danger", next: "Declined", requiresComment: true },
    ],
  },
  "HITL-2": { title: "Budget sign-off", options: standard("Approve and lock", "Drafting", "Planning") },
  "HITL-3": { title: "Compliance attestation", options: standard("Attest", "AwaitingExecApproval", "Drafting") },
  "HITL-4": { title: "Executive approval", options: standard("Approve", "Packaging", "Drafting") },
  "HITL-5": {
    title: "Submission authorization",
    options: [
      { decision: "approve", label: "Authorize submission", tone: "primary", next: "Submitted" },
      { decision: "reject", label: "Hold", tone: "danger", requiresComment: true },
    ],
  },
  "REVIEW-ELIGIBILITY": { title: "Eligibility review", options: standard("Confirm eligible", "Screened", "Ineligible") },
  "REVIEW-PARSE": { title: "Parse review", options: standard("Confirm fields", "Normalized", "Discarded") },
};

export const optionFor = (gate: Gate, decision: Decision): DecisionOption | undefined =>
  GATES[gate].options.find((o) => o.decision === decision);
