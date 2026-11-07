// Client-side view of the pillar /v1 API (blueprint 7.4). Contract payloads come from
// @hope/schemas; the envelopes below are endpoint shapes not yet in hope_core.schemas
// (listed under "Requests for orchestrator" in the PR).
import type { AgencyProfile, Gate, GrantOpportunity, HitlDecision, HitlRequest, OpportunityMatrix } from "@hope/schemas";
import type { OpportunityState } from "@/lib/lifecycle";

export type Recommendation = OpportunityMatrix["rows"][number]["recommendation"];
export type EligibilityStatus = OpportunityMatrix["rows"][number]["eligibility"];
export type CapacityFit = NonNullable<OpportunityMatrix["rows"][number]["capacity_fit"]>;
export type MatrixRow = OpportunityMatrix["rows"][number];

export interface MatrixQuery {
  cursor?: string;
  limit?: number;
}

export interface MatrixPage extends OpportunityMatrix {
  next_cursor?: string | null;
}

export interface Session {
  user_id: string;
  display_name: string;
  roles: string[];
  tenant_id: string;
  agency_id: string;
}

export type SignalBody = Pick<HitlDecision, "decision" | "artifact_hash" | "comment">;

export interface SignalOptions {
  /** Step-up MFA assertion for HITL-2/3/5 (placeholder until the IdP flow exists). */
  stepUpToken?: string;
}

export interface SignalReceipt {
  request_id: string;
  gate: Gate;
  decision: HitlDecision["decision"];
  accepted_at: string;
}

export interface WorkflowTransition {
  from: OpportunityState | null;
  to: OpportunityState;
  at: string;
  actor: string;
  gate?: Gate | null;
  note?: string | null;
}

export interface WorkflowSummary {
  workflow_id: string;
  opportunity_id: string;
  title: string;
  state: OpportunityState;
  internal_deadline?: string | null;
}

export interface WorkflowView extends WorkflowSummary {
  history: WorkflowTransition[];
  open_gates: HitlRequest[];
}

export interface VersionedProfile {
  profile: AgencyProfile;
  etag: string;
}

export type ProfilePatch = Partial<Omit<AgencyProfile, "agency_id" | "tenant_id" | "version">>;

export type ProfilePatchResult =
  | ({ status: "applied" } & VersionedProfile)
  | { status: "pending_approval"; proposal_id: string; gate: "HITL-0"; sections: string[] };

export interface HopeApi {
  getSession(): Promise<Session>;
  getMatrix(agencyId: string, query?: MatrixQuery): Promise<MatrixPage>;
  getOpportunity(opportunityId: string): Promise<GrantOpportunity>;
  listHitlRequests(roles: readonly string[]): Promise<HitlRequest[]>;
  submitSignal(workflowId: string, gate: Gate, body: SignalBody, opts?: SignalOptions): Promise<SignalReceipt>;
  listWorkflows(): Promise<WorkflowSummary[]>;
  getWorkflow(workflowId: string): Promise<WorkflowView>;
  getProfile(agencyId: string): Promise<VersionedProfile>;
  patchProfile(agencyId: string, patch: ProfilePatch, etag: string): Promise<ProfilePatchResult>;
}
