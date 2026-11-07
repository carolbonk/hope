import type { Gate, GrantOpportunity, HitlRequest } from "@hope/schemas";
import { ApiError, PreconditionFailedError, StaleArtifactError } from "./errors";
import type {
  HopeApi,
  MatrixPage,
  MatrixQuery,
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

export interface HttpApiConfig {
  baseUrl: string;
  tenantId: string;
  fetchImpl?: typeof fetch;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  query?: Record<string, string | number | undefined>;
}

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

  getSession(): Promise<Session> {
    return this.json("/me");
  }

  getMatrix(agencyId: string, query: MatrixQuery = {}): Promise<MatrixPage> {
    return this.json(`/agencies/${enc(agencyId)}/matrix`, { query: { cursor: query.cursor, limit: query.limit } });
  }

  getOpportunity(opportunityId: string): Promise<GrantOpportunity> {
    return this.json(`/opportunities/${enc(opportunityId)}`);
  }

  listHitlRequests(roles: readonly string[]): Promise<HitlRequest[]> {
    return this.json("/hitl/requests", { query: { status: "pending", roles: roles.join(",") } });
  }

  submitSignal(workflowId: string, gate: Gate, body: SignalBody, opts: SignalOptions = {}): Promise<SignalReceipt> {
    return this.json(`/workflows/${enc(workflowId)}/signals/${enc(gate)}`, {
      method: "POST",
      body,
      headers: opts.stepUpToken ? { "X-Hope-Step-Up": opts.stepUpToken } : {},
    });
  }

  listWorkflows(): Promise<WorkflowSummary[]> {
    return this.json("/workflows");
  }

  getWorkflow(workflowId: string): Promise<WorkflowView> {
    return this.json(`/workflows/${enc(workflowId)}`);
  }

  async getProfile(agencyId: string): Promise<VersionedProfile> {
    const res = await this.request(`/agencies/${enc(agencyId)}/profile`);
    return { profile: await res.json(), etag: res.headers.get("ETag") ?? "" };
  }

  async patchProfile(agencyId: string, patch: ProfilePatch, etag: string): Promise<ProfilePatchResult> {
    const res = await this.request(`/agencies/${enc(agencyId)}/profile`, {
      method: "PATCH",
      body: patch,
      headers: { "If-Match": etag },
    });
    if (res.status === 202) return { status: "pending_approval", ...(await res.json()) };
    return { status: "applied", profile: await res.json(), etag: res.headers.get("ETag") ?? "" };
  }
}

const enc = encodeURIComponent;

async function toError(res: Response): Promise<ApiError> {
  const body = (await res.json().catch(() => ({}))) as { detail?: string; code?: string; current_hash?: string };
  if (res.status === 409) return new StaleArtifactError(body.current_hash);
  if (res.status === 412) return new PreconditionFailedError();
  return new ApiError(res.status, body.detail ?? `Request failed (${res.status})`, body.code);
}
