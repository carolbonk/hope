import { z } from "zod";

// Mirrors `contracts/mocks/w3` (H2's `/v1/discovery/jobs*`). Money stays in minor units here.
const money = z.object({ amount_minor: z.number().int(), currency: z.string().optional() });

export const discoveryRequest = z.object({ focus_keywords: z.array(z.string()), location: z.string().nullable() });

export const discoveryStep = z.object({
  seq: z.number().int(),
  at: z.string(),
  kind: z.enum(["info", "query", "page", "skip", "candidate", "warning", "error"]),
  text: z.string(),
  query: z.string().optional(),
  url: z.string().optional(),
  grant_id: z.string().optional(),
  is_new: z.boolean().optional(),
  result_count: z.number().int().optional(),
});

export const jobCandidate = z.object({
  grant_id: z.string(),
  title: z.string(),
  funder: z.string(),
  url: z.string(),
  fit_score: z.number().int(),
  amount_text: z.string().nullable(),
  amount_max: money.nullable(),
  deadline_text: z.string().nullable(),
  deadline: z.string().nullable(),
  summary: z.string().nullable(),
  is_new: z.boolean(),
  status: z.enum(["new", "saved", "passed"]),
});

export const discoveryJobView = z.object({
  job: z.object({
    job_id: z.string(),
    status: z.enum(["queued", "running", "done", "failed"]),
    queries: z.array(z.string()),
    progress: z.object({
      queries_total: z.number().int(),
      queries_done: z.number().int(),
      pages_read: z.number().int(),
      candidates_found: z.number().int(),
      current_step: z.string(),
    }),
    error: z.string().nullable(),
    started_at: z.string(),
    finished_at: z.string().nullable(),
  }),
  request: discoveryRequest,
  counts: z.object({
    urls_found: z.number().int(),
    pages_read: z.number().int(),
    candidates_new: z.number().int(),
    candidates_updated: z.number().int(),
    skipped_expired: z.number().int(),
    skipped_not_grant: z.number().int(),
    skipped_known: z.number().int(),
    failed_pages: z.number().int(),
    queries_failed: z.number().int(),
  }),
  steps: z.array(discoveryStep),
  last_seq: z.number().int(),
  candidates: z.array(jobCandidate),
  elapsed_s: z.number().int(),
  limits: z.object({ max_queries: z.number().int(), max_pages: z.number().int(), timeout_s: z.number().int() }),
});

export const discoveryRunSummary = z.object({
  job_id: z.string(),
  status: z.enum(["queued", "running", "done", "failed"]),
  started_at: z.string(),
  finished_at: z.string().nullable(),
  request: discoveryRequest,
  queries_total: z.number().int(),
  pages_read: z.number().int(),
  candidates_found: z.number().int(),
  candidates_new: z.number().int(),
  error: z.string().nullable(),
});

export const discoveryRunList = z.object({ items: z.array(discoveryRunSummary), running_job_id: z.string().nullable() });

export type DiscoveryRequest = z.infer<typeof discoveryRequest>;
export type DiscoveryStep = z.infer<typeof discoveryStep>;
export type JobCandidate = z.infer<typeof jobCandidate>;
export type DiscoveryJobView = z.infer<typeof discoveryJobView>;
export type DiscoveryRunSummary = z.infer<typeof discoveryRunSummary>;
export type DiscoveryRunList = z.infer<typeof discoveryRunList>;
export type JobStatus = DiscoveryJobView["job"]["status"];

/** The three calls the run panel makes; `api.ts` is the HTTP one, `fixture.ts` a scripted one. */
export interface DiscoveryApi {
  startJob(body: DiscoveryRequest): Promise<DiscoveryJobView>;
  getJob(jobId: string, sinceSeq: number): Promise<DiscoveryJobView>;
  listJobs(limit: number): Promise<DiscoveryRunList>;
}
