import type { AgencyProfile, Gate, GrantOpportunity, HitlRequest } from "@hope/schemas";
import { optionFor } from "@/lib/gates";
import { isProtectedSection, STEP_UP_MFA_GATES, type ProfileSection } from "@/lib/lifecycle";
import { addHours } from "@/lib/time";
import { ApiError, PreconditionFailedError, StaleArtifactError } from "./errors";
import { buildOpportunities } from "./fixtures/opportunities";
import { FIXTURE_PROFILE } from "./fixtures/profile";
import { buildWorkflows, fakeHash, FIXTURE_SESSION } from "./fixtures/workflows";
import type {
  HopeApi,
  MatrixPage,
  MatrixRow,
  ProfilePatch,
  ProfilePatchResult,
  Session,
  SignalBody,
  SignalOptions,
  SignalReceipt,
  VersionedProfile,
  WorkflowSummary,
  WorkflowView,
} from "./types";

const PROFILE_WORKFLOW_PREFIX = "wf-profile-";

/** In-memory implementation of the pillar API with realistic sample data. Mutations persist per instance. */
export class FixtureApi implements HopeApi {
  private readonly now: () => Date;
  private readonly opportunities: Map<string, GrantOpportunity>;
  private readonly rows: MatrixRow[];
  private readonly workflows: Map<string, WorkflowView>;
  private requests: HitlRequest[];
  private readonly currentHashes: Map<string, string>;
  private readonly proposals = new Map<string, ProfilePatch>();
  private profile: AgencyProfile = structuredClone(FIXTURE_PROFILE);
  private readonly generatedAt: string;

  constructor(opts: { now?: () => Date } = {}) {
    this.now = opts.now ?? (() => new Date());
    const now = this.now();
    const opp = buildOpportunities(now);
    const wf = buildWorkflows(now);
    this.opportunities = new Map(opp.opportunities.map((o) => [o.opportunity_id, o]));
    this.rows = opp.rows;
    this.workflows = wf.workflows;
    this.requests = wf.requests;
    this.currentHashes = wf.currentHashes;
    this.generatedAt = addHours(now, -2);
  }

  async getSession(): Promise<Session> {
    return { ...FIXTURE_SESSION };
  }

  async getMatrix(agencyId: string): Promise<MatrixPage> {
    return {
      agency_id: agencyId,
      generated_at: this.generatedAt,
      model_version: "matching-0.1.0",
      weights_profile: "heuristic-v1",
      rows: structuredClone(this.rows),
      next_cursor: null,
    };
  }

  async getOpportunity(opportunityId: string): Promise<GrantOpportunity> {
    const opp = this.opportunities.get(opportunityId);
    if (!opp) throw new ApiError(404, `Opportunity ${opportunityId} not found`);
    return structuredClone(opp);
  }

  async listHitlRequests(roles: readonly string[]): Promise<HitlRequest[]> {
    return structuredClone(this.requests.filter((r) => r.approver_roles.some((role) => roles.includes(role))));
  }

  async submitSignal(workflowId: string, gate: Gate, body: SignalBody, opts: SignalOptions = {}): Promise<SignalReceipt> {
    const request = this.requests.find((r) => r.workflow_id === workflowId && r.gate === gate);
    if (!request) throw new ApiError(404, "This approval request is no longer pending.");
    const option = optionFor(gate, body.decision);
    if (!option) throw new ApiError(422, `"${body.decision}" is not a valid decision for ${gate}.`);
    if (STEP_UP_MFA_GATES.has(gate) && !opts.stepUpToken) throw new ApiError(401, "Step-up verification is required.");
    const current = this.currentHashes.get(request.request_id) ?? request.artifact_hash;
    if (body.artifact_hash !== current) {
      request.artifact_hash = current;
      throw new StaleArtifactError(current);
    }
    this.requests = this.requests.filter((r) => r !== request);
    const at = this.now().toISOString();
    if (gate === "HITL-0") this.resolveProposal(workflowId, body.decision === "approve");
    const wf = this.workflows.get(workflowId);
    if (wf) {
      wf.open_gates = wf.open_gates.filter((g) => g.request_id !== request.request_id);
      if (option.next && option.next !== wf.state) {
        wf.history.push({ from: wf.state, to: option.next, at, actor: FIXTURE_SESSION.display_name, gate, note: body.comment ?? null });
        wf.state = option.next;
      }
    }
    return { request_id: request.request_id, gate, decision: body.decision, accepted_at: at };
  }

  async listWorkflows(): Promise<WorkflowSummary[]> {
    return [...this.workflows.values()].map(({ workflow_id, opportunity_id, title, state, internal_deadline }) => ({
      workflow_id,
      opportunity_id,
      title,
      state,
      internal_deadline,
    }));
  }

  async getWorkflow(workflowId: string): Promise<WorkflowView> {
    const wf = this.workflows.get(workflowId);
    if (!wf) throw new ApiError(404, `Workflow ${workflowId} not found`);
    return structuredClone(wf);
  }

  async getProfile(): Promise<VersionedProfile> {
    return { profile: structuredClone(this.profile), etag: etagOf(this.profile) };
  }

  async patchProfile(_agencyId: string, patch: ProfilePatch, etag: string): Promise<ProfilePatchResult> {
    if (etag !== etagOf(this.profile)) throw new PreconditionFailedError();
    const sections = Object.keys(patch) as ProfileSection[];
    const protectedSections = sections.filter(isProtectedSection);
    if (protectedSections.length === 0) {
      this.profile = { ...this.profile, ...structuredClone(patch), version: this.profile.version + 1 };
      return { status: "applied", ...(await this.getProfile()) };
    }
    const proposalId = `prop-${this.proposals.size + 1}-${this.profile.version}`;
    this.proposals.set(proposalId, structuredClone(patch));
    const rule = this.profile.approval_hierarchy.find((r) => r.gate === "HITL-0");
    const hash = fakeHash(JSON.stringify(patch));
    const request: HitlRequest = {
      request_id: crypto.randomUUID(),
      tenant_id: this.profile.tenant_id,
      workflow_id: `${PROFILE_WORKFLOW_PREFIX}${proposalId}`,
      gate: "HITL-0",
      artifact_hash: hash,
      approver_roles: rule?.approver_roles ?? ["org_admin"],
      due_at: addHours(this.now(), rule?.sla_hours ?? 72),
      summary: `Profile change proposed by ${FIXTURE_SESSION.display_name}: ${protectedSections.map(sectionLabel).join(", ")}.`,
      payload_ref: `proposal:${proposalId}`,
    };
    this.requests.push(request);
    this.currentHashes.set(request.request_id, hash);
    return { status: "pending_approval", proposal_id: proposalId, gate: "HITL-0", sections: protectedSections };
  }

  private resolveProposal(workflowId: string, approved: boolean): void {
    const proposalId = workflowId.slice(PROFILE_WORKFLOW_PREFIX.length);
    const patch = this.proposals.get(proposalId);
    this.proposals.delete(proposalId);
    if (approved && patch) this.profile = { ...this.profile, ...patch, version: this.profile.version + 1 };
  }
}

const etagOf = (profile: AgencyProfile): string => `W/"v${profile.version}"`;

export const sectionLabel = (section: string): string => section.replace(/_/g, " ");
