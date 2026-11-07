import type { Gate, HitlRequest } from "@hope/schemas";
import { HAPPY_PATH, type OpportunityState } from "@/lib/lifecycle";
import { addDays, addHours } from "@/lib/time";
import type { Session, WorkflowTransition, WorkflowView } from "../types";
import { FIXTURE_AGENCY_ID, FIXTURE_TENANT_ID } from "./profile";

export const FIXTURE_SESSION: Session = {
  user_id: "u-dana",
  display_name: "Dana Okafor",
  roles: ["executive_director", "development_director", "finance_director", "compliance_officer", "aor"],
  tenant_id: FIXTURE_TENANT_ID,
  agency_id: FIXTURE_AGENCY_ID,
};

/** Deterministic sha256-shaped hex so fixture hashes look and compare like real ones. */
export function fakeHash(seed: string): string {
  let out = "";
  for (let round = 0; out.length < 64; round++) {
    let h = 0x811c9dc5 ^ round;
    for (const ch of seed) h = Math.imul(h ^ ch.charCodeAt(0), 0x01000193) >>> 0;
    out += h.toString(16).padStart(8, "0");
  }
  return `sha256:${out.slice(0, 64)}`;
}

interface WorkflowSpec {
  id: string;
  opportunityId: string;
  title: string;
  state: OpportunityState;
  dueInDays: number;
  detours?: OpportunityState[];
  gate?: { requestId: string; gate: Gate; roles: string[]; dueInHours: number; summary: string; staleHash?: boolean };
}

const ACTORS: Partial<Record<OpportunityState, string>> = {
  Normalized: "A2 RFP Parser",
  Screened: "A4 Eligibility",
  Recommended: "A6 Recommender",
  Planning: "Dana Okafor",
  Drafting: "Priya Raman",
  InReview: "A11 Grounding Critic",
  AwaitingCompliance: "A8 Compliance Monitor",
};

const SPECS: WorkflowSpec[] = [
  {
    id: "wf-hrsa-rhcso",
    opportunityId: "opp-hrsa-rhcso-2027",
    title: "Rural Health Care Services Outreach Program",
    state: "AwaitingGoNoGo",
    dueInDays: 34,
    gate: {
      requestId: "3d4a6a5e-2b9c-4c41-8f0e-9a7e1b2c3d01",
      gate: "HITL-1",
      roles: ["development_director", "program_lead"],
      dueInHours: 70,
      summary: "Go / No-Go: HRSA Rural Outreach, rank 1 (score 77.3), $300K ceiling, est. 120 writing hours.",
    },
  },
  {
    id: "wf-samhsa-aware",
    opportunityId: "opp-samhsa-aware-2027",
    title: "Project AWARE: Advancing Wellness and Resiliency in Education",
    state: "AwaitingBudgetSignoff",
    dueInDays: 21,
    gate: {
      requestId: "3d4a6a5e-2b9c-4c41-8f0e-9a7e1b2c3d02",
      gate: "HITL-2",
      roles: ["finance_director"],
      dueInHours: 20,
      summary: "Budget sign-off: $1.62M request over 5 periods; indirect at negotiated 18.2% MTDC; all cap checks pass.",
      staleHash: true,
    },
  },
  {
    id: "wf-state-oral",
    opportunityId: "opp-state-oral-health-2027",
    title: "Oral Health Access Expansion Grants",
    state: "AwaitingCompliance",
    dueInDays: 12,
    detours: ["NeedsEligibilityReview"],
    gate: {
      requestId: "3d4a6a5e-2b9c-4c41-8f0e-9a7e1b2c3d03",
      gate: "HITL-3",
      roles: ["compliance_officer"],
      dueInHours: 30,
      summary: "Compliance attestation: 14 of 14 checklist items have evidence; state charity registration current.",
    },
  },
  {
    id: "wf-cascade-crg",
    opportunityId: "opp-cascade-resilience-2027",
    title: "Community Resilience Grants",
    state: "AwaitingExecApproval",
    dueInDays: 48,
    gate: {
      requestId: "3d4a6a5e-2b9c-4c41-8f0e-9a7e1b2c3d04",
      gate: "HITL-4",
      roles: ["executive_director"],
      dueInHours: -3,
      summary: "Executive approval: final $150K package for Cascade Health Foundation; 2 red-line changes since last review.",
    },
  },
  {
    id: "wf-cdc-chw",
    opportunityId: "opp-cdc-chw-2027",
    title: "Community Health Workers for Public Health Response and Resilient Communities",
    state: "AwaitingSubmissionAuth",
    dueInDays: 9,
    gate: {
      requestId: "3d4a6a5e-2b9c-4c41-8f0e-9a7e1b2c3d05",
      gate: "HITL-5",
      roles: ["aor"],
      dueInHours: 6,
      summary: "Submission authorization: Grants.gov package (SF-424, SF-424A, narrative, 6 attachments) validated.",
    },
  },
  {
    id: "wf-northside-cb",
    opportunityId: "opp-northside-capacity-2027",
    title: "Nonprofit Capacity Building Fund",
    state: "AwaitingExecApproval",
    dueInDays: 63,
    gate: {
      requestId: "3d4a6a5e-2b9c-4c41-8f0e-9a7e1b2c3d06",
      gate: "HITL-4",
      roles: ["board_chair"],
      dueInHours: 90,
      summary: "Board approval: capacity-building request above the board threshold.",
    },
  },
  {
    id: "wf-usda-cf",
    opportunityId: "opp-usda-cf-2027",
    title: "Community Facilities Direct Loan and Grant Program",
    state: "Ineligible",
    dueInDays: 40,
  },
];

function buildHistory(spec: WorkflowSpec, now: Date): WorkflowTransition[] {
  const path: OpportunityState[] =
    spec.state === "Ineligible" ? ["Ingested", "Normalized", "Ineligible"] : [...HAPPY_PATH.slice(0, HAPPY_PATH.indexOf(spec.state) + 1)];
  for (const detour of spec.detours ?? []) {
    const after = detour === "NeedsEligibilityReview" ? "Normalized" : "Ingested";
    path.splice(path.indexOf(after) + 1, 0, detour);
  }
  const start = new Date(now.getTime() - path.length * 26 * 3_600_000);
  return path.map((to, i) => ({
    from: i === 0 ? null : (path[i - 1] ?? null),
    to,
    at: addHours(start, i * 26),
    actor: ACTORS[to] ?? (i === 0 ? "A1 Discovery" : "A0 Workflow Supervisor"),
    note: to === "NeedsEligibilityReview" ? "Medicaid provider clause is ambiguous" : null,
  }));
}

export interface WorkflowFixtures {
  workflows: Map<string, WorkflowView>;
  requests: HitlRequest[];
  /** Hash of the artifact as it is now; differs from the request hash when it changed after the gate opened. */
  currentHashes: Map<string, string>;
}

export function buildWorkflows(now: Date): WorkflowFixtures {
  const workflows = new Map<string, WorkflowView>();
  const requests: HitlRequest[] = [];
  const currentHashes = new Map<string, string>();
  for (const spec of SPECS) {
    const open: HitlRequest[] = [];
    if (spec.gate) {
      const g = spec.gate;
      const hash = fakeHash(`${spec.id}:${g.gate}:v1`);
      const request: HitlRequest = {
        request_id: g.requestId,
        tenant_id: FIXTURE_TENANT_ID,
        workflow_id: spec.id,
        gate: g.gate,
        artifact_hash: hash,
        approver_roles: g.roles,
        due_at: addHours(now, g.dueInHours),
        summary: g.summary,
        payload_ref: `s3://hope-artifacts/${spec.id}/${g.gate}.json`,
      };
      open.push(request);
      requests.push(request);
      currentHashes.set(g.requestId, g.staleHash ? fakeHash(`${spec.id}:${g.gate}:v2`) : hash);
    }
    workflows.set(spec.id, {
      workflow_id: spec.id,
      opportunity_id: spec.opportunityId,
      title: spec.title,
      state: spec.state,
      internal_deadline: addDays(now, spec.dueInDays - 7),
      history: buildHistory(spec, now),
      open_gates: open,
    });
  }
  return { workflows, requests, currentHashes };
}
