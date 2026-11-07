// HTTP client for the pillar /v1 API (services/pillar/src/hope_pillar/api). Pillar response
// bodies are service-local models, so they are typed here and mapped onto the HopeApi views.
import type { AgencyProfile, Gate, GrantOpportunity, HitlRequest } from "@hope/schemas";
import { OPPORTUNITY_STATES, type OpportunityState } from "@/lib/lifecycle";
import { ApiError, PreconditionFailedError, StaleArtifactError } from "./errors";
import type {
  HopeApi,
  MatrixPage,
  MatrixQuery,
  MatrixRow,
  ProfilePatch,
  ProfilePatchResult,
  Recommendation,
  Session,
  SignalBody,
  SignalOptions,
  SignalReceipt,
  VersionedProfile,
  WorkflowEvent,
  WorkflowSummary,
  WorkflowView,
} from "./types";

export interface HttpApiConfig {
  baseUrl: string;
  tenantId: string;
  agencyId: string;
  /** Dev principal (X-Hope-User / X-Hope-Roles) until OIDC replaces it. */
  userId?: string;
  roles?: readonly string[];
  submissionChannel?: string;
  fetchImpl?: typeof fetch;
}

interface PillarMatrixItem {
  opportunity_id: string;
  title: string;
  state: string;
  composite_score: number | null;
  recommendation: string | null;
  internal_deadline: string | null;
  application_due: string | null;
  workflow_id: string | null;
}
interface PillarMatrixPage {
  items?: PillarMatrixItem[];
  rows?: MatrixRow[];
  next_cursor: string | null;
}
interface PillarOpportunity {
  title: string;
  normalized: GrantOpportunity;
}
interface PillarGate {
  request_id: string;
  gate: Gate;
  status: "open" | "decided" | "superseded";
  artifact_hash: string;
  approver_roles: string[];
  due_at: string | null;
  summary: string;
  decision: string | null;
  decided_by: string | null;
  requested_at: string;
  decided_at: string | null;
}
interface PillarWorkflow {
  workflow_id: string;
  opportunity_id: string | null;
  state: string | null;
  updated_at: string | null;
  gates: PillarGate[];
  timeline: { event_id: string; event_type: string; occurred_at: string }[];
}
interface PillarProfile {
  version: number;
  profile: AgencyProfile;
  valid_from: string;
}
interface PillarProposal {
  proposal_id: string;
  status: "pending_approval" | "accepted";
  protected_paths: string[];
}
interface PillarDecision {
  request_id: string;
  decision: SignalReceipt["decision"];
  tracking_id?: string;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  query?: Record<string, string | number | undefined>;
}

const RECOMMENDATIONS: readonly Recommendation[] = ["pursue", "consider", "watch", "skip"];
const MATRIX_PAGE_LIMIT = 200;

export class HttpApi implements HopeApi {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(private readonly config: HttpApiConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/, "");
    this.fetchImpl = config.fetchImpl ?? ((...args) => fetch(...args));
  }

  private async request(path: string, opts: RequestOptions = {}): Promise<Response> {
    const url = new URL(`${this.baseUrl}/v1${path}`);
    for (const [k, v] of Object.entries(opts.query ?? {})) if (v !== undefined) url.searchParams.set(k, String(v));
    const res = await this.fetchImpl(url.toString(), {
      method: opts.method ?? "GET",
      headers: {
        Accept: "application/json",
        "X-Hope-Tenant": this.config.tenantId,
        ...(this.config.userId ? { "X-Hope-User": this.config.userId } : {}),
        ...(this.config.roles?.length ? { "X-Hope-Roles": this.config.roles.join(",") } : {}),
        ...(opts.body === undefined ? {} : { "Content-Type": "application/json" }),
        ...opts.headers,
      },
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    });
    if (!res.ok) throw await toError(res);
    return res;
  }

  private async json<T>(path: string, opts?: RequestOptions): Promise<T> {
    return (await this.request(path, opts)).json() as Promise<T>;
  }

  private matrixItems(): Promise<PillarMatrixPage> {
    return this.json(`/agencies/${enc(this.config.agencyId)}/matrix`, { query: { limit: MATRIX_PAGE_LIMIT } });
  }

  async getSession(): Promise<Session> {
    const userId = this.config.userId ?? "anonymous";
    return {
      user_id: userId,
      display_name: userId,
      roles: [...(this.config.roles ?? [])],
      tenant_id: this.config.tenantId,
      agency_id: this.config.agencyId,
    };
  }

  async getMatrix(agencyId: string, query: MatrixQuery = {}): Promise<MatrixPage> {
    const page = await this.json<PillarMatrixPage>(`/agencies/${enc(agencyId)}/matrix`, {
      query: { cursor: query.cursor, limit: query.limit, state: query.state, min_score: query.min_score, due_before: query.due_before },
    });
    const base = { agency_id: agencyId, generated_at: new Date().toISOString(), model_version: "pillar", next_cursor: page.next_cursor };
    if (page.rows) return { ...base, rows: page.rows, detail: "full" };
    return { ...base, rows: (page.items ?? []).map(summaryRow), detail: "summary" };
  }

  async getOpportunity(opportunityId: string): Promise<GrantOpportunity> {
    const view = await this.json<PillarOpportunity>(`/opportunities/${enc(opportunityId)}`);
    return { ...view.normalized, title: view.normalized.title ?? view.title };
  }

  async listHitlRequests(roles: readonly string[]): Promise<HitlRequest[]> {
    const workflows = await this.listWorkflows();
    const views = await Promise.all(workflows.map((w) => this.json<PillarWorkflow>(`/workflows/${enc(w.workflow_id)}`)));
    const wanted = new Set(roles);
    return views
      .flatMap((v) => this.openGates(v))
      .filter((r) => r.approver_roles.length === 0 || r.approver_roles.some((role) => wanted.has(role)));
  }

  async submitSignal(workflowId: string, gate: Gate, body: SignalBody, opts: SignalOptions = {}): Promise<SignalReceipt> {
    const headers: Record<string, string> = opts.stepUpToken ? { "X-Hope-Mfa": "true" } : {};
    const authorize = gate === "HITL-5" && body.decision === "approve";
    if (authorize && !opts.requestId) throw new ApiError(400, "HITL-5 authorization needs the request id.");
    const receipt = authorize
      ? await this.json<PillarDecision>(`/packages/${enc(opts.requestId ?? "")}/authorize`, {
          method: "POST",
          headers,
          body: {
            manifest_hash: body.artifact_hash,
            channel: opts.channel ?? this.config.submissionChannel ?? "grants_gov",
            comment: body.comment ?? null,
          },
        })
      : await this.json<PillarDecision>(`/workflows/${enc(workflowId)}/signals/${enc(gate)}`, { method: "POST", headers, body });
    return {
      request_id: receipt.request_id,
      gate,
      decision: receipt.decision,
      accepted_at: new Date().toISOString(),
      ...(receipt.tracking_id ? { tracking_id: receipt.tracking_id } : {}),
    };
  }

  async listWorkflows(): Promise<WorkflowSummary[]> {
    const page = await this.matrixItems();
    return (page.items ?? []).flatMap((i) =>
      i.workflow_id
        ? [{ workflow_id: i.workflow_id, opportunity_id: i.opportunity_id, title: i.title, state: asState(i.state), internal_deadline: i.internal_deadline }]
        : [],
    );
  }

  async getWorkflow(workflowId: string): Promise<WorkflowView> {
    const view = await this.json<PillarWorkflow>(`/workflows/${enc(workflowId)}`);
    const title = view.opportunity_id
      ? await this.getOpportunity(view.opportunity_id).then((o) => o.title, () => workflowId)
      : workflowId;
    const state = asState(view.state);
    const at = view.updated_at ?? view.timeline.at(-1)?.occurred_at ?? new Date().toISOString();
    const events: WorkflowEvent[] = [
      ...view.timeline.map((t) => ({ at: t.occurred_at, label: humanizeEvent(t.event_type) })),
      ...view.gates.flatMap((g) =>
        g.decided_at && g.decision ? [{ at: g.decided_at, label: `${g.gate} ${g.decision}`, actor: g.decided_by }] : [],
      ),
    ].sort((a, b) => a.at.localeCompare(b.at));
    return {
      workflow_id: view.workflow_id,
      opportunity_id: view.opportunity_id ?? "",
      title,
      state,
      history: [{ from: null, to: state, at, actor: "pillar" }],
      open_gates: this.openGates(view),
      events,
    };
  }

  async getProfile(agencyId: string): Promise<VersionedProfile> {
    const res = await this.request(`/agencies/${enc(agencyId)}/profile`);
    const view = (await res.json()) as PillarProfile;
    return {
      profile: { ...view.profile, version: view.version, valid_from: view.profile.valid_from ?? view.valid_from },
      etag: res.headers.get("ETag") ?? `"${view.version}"`,
    };
  }

  async patchProfile(agencyId: string, patch: ProfilePatch, etag: string): Promise<ProfilePatchResult> {
    const changes = Object.fromEntries(Object.entries(patch).filter(([, v]) => v !== undefined));
    const res = await this.json<PillarProposal>(`/agencies/${enc(agencyId)}/profile`, {
      method: "PATCH",
      body: { changes },
      headers: { "If-Match": etag },
    });
    if (res.status === "pending_approval")
      return { status: "pending_approval", proposal_id: res.proposal_id, gate: "HITL-0", sections: topLevel(res.protected_paths) };
    return { status: "accepted", proposal_id: res.proposal_id };
  }

  private openGates(view: PillarWorkflow): HitlRequest[] {
    return view.gates
      .filter((g) => g.status === "open")
      .map((g) => ({
        request_id: g.request_id,
        tenant_id: this.config.tenantId,
        workflow_id: view.workflow_id,
        gate: g.gate,
        artifact_hash: g.artifact_hash,
        approver_roles: g.approver_roles,
        due_at: g.due_at,
        summary: g.summary,
      }));
  }
}

const enc = encodeURIComponent;

const asState = (state: string | null): OpportunityState =>
  (OPPORTUNITY_STATES as readonly string[]).includes(state ?? "") ? (state as OpportunityState) : "Ingested";

const asRecommendation = (value: string | null): Recommendation =>
  RECOMMENDATIONS.includes(value as Recommendation) ? (value as Recommendation) : "watch";

const humanizeEvent = (eventType: string): string => {
  const label = eventType.replace(/^hope\./, "").replace(/[._]/g, " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
};

const topLevel = (paths: readonly string[]): string[] => [...new Set(paths.map((p) => p.split(".")[0] ?? p))];

/** Pillar matrix items carry ranking only; dimension scores stay zero and eligibility needs review. */
function summaryRow(item: PillarMatrixItem, index: number): MatrixRow {
  return {
    opportunity_id: item.opportunity_id,
    rank: index + 1,
    composite_score: item.composite_score ?? 0,
    recommendation: asRecommendation(item.recommendation),
    eligibility: "needs_review",
    capacity_fit: null,
    scores: { mission_alignment: 0, funding_fit: 0, win_probability: 0, effort_to_funding: 0, deadline_feasibility: 0 },
  };
}

async function toError(res: Response): Promise<ApiError> {
  const body = (await res.json().catch(() => ({}))) as { detail?: unknown; current_hash?: string };
  const detail = typeof body.detail === "string" ? body.detail : undefined;
  if (res.status === 409 && (body.current_hash || /artifact_hash is stale/.test(detail ?? ""))) return new StaleArtifactError(body.current_hash);
  if (res.status === 412) return new PreconditionFailedError();
  return new ApiError(res.status, detail ?? `Request failed (${res.status})`);
}
