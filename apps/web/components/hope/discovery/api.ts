import { API_URL, ProblemError, UNAUTHORIZED_EVENT, apiFetch, type FieldError } from "@/lib/api/http";
import { discoveryJobView, discoveryRunList, type DiscoveryApi, type DiscoveryJobView, type DiscoveryRequest, type DiscoveryRunList } from "./types";

/** A `ProblemError` that keeps the problem body's extra members (`job_id`, `missing`, `limit`, `resets_at`). */
export class DiscoveryProblem extends ProblemError {
  constructor(
    status: number,
    code: string,
    message: string,
    errors: FieldError[],
    readonly extra: { job_id?: string; missing?: string[]; limit?: number; resets_at?: string },
  ) {
    super(status, code, message, errors);
    this.name = "DiscoveryProblem";
  }
}

type ProblemBody = { code?: string; title?: string; detail?: string; errors?: FieldError[]; job_id?: string; missing?: string[]; limit?: number; resets_at?: string };

/**
 * `POST /v1/discovery/jobs`. Same cookie, JSON and 401 handling as `apiFetch`, but its errors carry the
 * body's extra members, which the panel needs (`apiFetch` keeps only `code`, `detail` and `errors`).
 */
async function postStart(body: DiscoveryRequest): Promise<DiscoveryJobView> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/v1/discovery/jobs`, {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
      credentials: "include",
    });
  } catch (err) {
    throw new ProblemError(0, "network_error", err instanceof Error ? err.message : "Network error");
  }
  if (res.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  if (!res.ok) {
    const p = (await res.json().catch(() => ({}))) as ProblemBody;
    throw new DiscoveryProblem(res.status, p.code ?? `http_${res.status}`, p.detail ?? p.title ?? res.statusText, p.errors ?? [], {
      job_id: p.job_id,
      missing: p.missing,
      limit: p.limit,
      resets_at: p.resets_at,
    });
  }
  return discoveryJobView.parse(await res.json());
}

export const startJob = (body: DiscoveryRequest) => postStart(body);

export async function getJob(jobId: string, sinceSeq: number): Promise<DiscoveryJobView> {
  const view = await apiFetch<unknown>(`/v1/discovery/jobs/${encodeURIComponent(jobId)}?since_seq=${sinceSeq}`);
  return discoveryJobView.parse(view);
}

export async function listJobs(limit: number): Promise<DiscoveryRunList> {
  return discoveryRunList.parse(await apiFetch<unknown>(`/v1/discovery/jobs?limit=${limit}`));
}

export const httpDiscoveryApi: DiscoveryApi = { startJob, getJob, listJobs };
