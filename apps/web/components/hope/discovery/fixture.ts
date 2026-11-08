import { DiscoveryProblem } from "./api";
import type { DiscoveryApi, DiscoveryJobView, DiscoveryRequest, DiscoveryRunList } from "./types";
import done from "../../../../../contracts/mocks/w3/discovery.get/done.json";
import failed from "../../../../../contracts/mocks/w3/discovery.get/failed.json";
import notFound from "../../../../../contracts/mocks/w3/discovery.get/not_found.json";
import running from "../../../../../contracts/mocks/w3/discovery.get/running.json";
import listEmpty from "../../../../../contracts/mocks/w3/discovery.list/empty.json";
import listOk from "../../../../../contracts/mocks/w3/discovery.list/ok.json";
import dailyLimit from "../../../../../contracts/mocks/w3/discovery.start/daily_limit.json";
import jobRunning from "../../../../../contracts/mocks/w3/discovery.start/job_running.json";
import profileIncomplete from "../../../../../contracts/mocks/w3/discovery.start/profile_incomplete.json";
import queued from "../../../../../contracts/mocks/w3/discovery.start/queued.json";

type Mock = { status: number; body: Record<string, unknown> };
const copy = <T>(m: { body: unknown }): T => structuredClone(m.body) as T;

function problem(m: Mock): DiscoveryProblem {
  const b = m.body as { code: string; title: string; job_id?: string; missing?: string[]; limit?: number; resets_at?: string };
  return new DiscoveryProblem(m.status, b.code, b.title, [], { job_id: b.job_id, missing: b.missing, limit: b.limit, resets_at: b.resets_at });
}

/** The W3 mocks as named views, for tests and the fixture api. */
export const W3 = {
  queued: () => copy<DiscoveryJobView>(queued),
  running: () => copy<DiscoveryJobView>(running),
  done: () => copy<DiscoveryJobView>(done),
  failed: () => copy<DiscoveryJobView>(failed),
  listOk: () => copy<DiscoveryRunList>(listOk),
  listEmpty: () => copy<DiscoveryRunList>(listEmpty),
  mocks: { queued, running, done, failed, notFound, listOk, listEmpty, dailyLimit, jobRunning, profileIncomplete } as Record<string, Mock>,
};

function noneFound(): DiscoveryJobView {
  const v = W3.done();
  v.counts = { ...v.counts, candidates_new: 0, candidates_updated: 0, skipped_expired: 0 };
  v.job.progress.candidates_found = 0;
  v.candidates = [];
  v.steps = v.steps.filter((s) => s.kind !== "candidate");
  return v;
}

function stoppedEarly(): DiscoveryJobView {
  const v = W3.done();
  const at = v.steps.at(-1)!.at;
  v.steps.splice(-1, 0, { seq: 21, at, kind: "warning", text: "Stopped early after 5:00: showing what was found so far" });
  return v;
}

function needsCheck(): DiscoveryJobView {
  const v = W3.done();
  v.candidates.push({
    ...v.candidates[0]!,
    grant_id: "7a1d2e3f-0000-4000-8000-000000000003",
    title: "Mobile Health Equipment Fund",
    url: "https://ncwmedicalfund.example.org/mobile-equipment",
    deadline: null,
    deadline_text: "Rolling",
  });
  return v;
}

export type FixtureOptions = { profileIncomplete?: boolean; dailyLimit?: boolean; history?: "ok" | "empty"; runningJob?: boolean };

/**
 * A scripted run (SC24 section 11). `startJob` → queued, then each `getJob` advances one frame:
 * running → done. `focus_keywords` switches: `fail`, `none`, `stop`, `check`.
 */
export class FixtureDiscoveryApi implements DiscoveryApi {
  readonly calls: { start: DiscoveryRequest[]; get: [string, number][]; list: number[] } = { start: [], get: [], list: [] };
  private frames: DiscoveryJobView[] = [];
  private active = false;

  constructor(private readonly options: FixtureOptions = {}) {
    if (options.runningJob) {
      this.active = true;
      this.frames = [W3.running(), W3.done()];
    }
  }

  async startJob(body: DiscoveryRequest): Promise<DiscoveryJobView> {
    this.calls.start.push(body);
    if (this.options.profileIncomplete) throw problem(profileIncomplete);
    if (this.options.dailyLimit) throw problem(dailyLimit);
    if (this.active) throw problem(jobRunning);
    const key = body.focus_keywords[0];
    const last =
      key === "fail" ? W3.failed() : key === "none" ? noneFound() : key === "stop" ? stoppedEarly() : key === "check" ? needsCheck() : W3.done();
    this.frames = key === "fail" ? [last] : [W3.running(), last];
    this.active = true;
    return { ...W3.queued(), request: body };
  }

  async getJob(jobId: string, sinceSeq: number): Promise<DiscoveryJobView> {
    this.calls.get.push([jobId, sinceSeq]);
    if (jobId === "missing" || !this.frames.length) throw problem(notFound);
    const frame = this.frames.length > 1 ? this.frames.shift()! : this.frames[0]!;
    if (frame.job.status === "done" || frame.job.status === "failed") this.active = false;
    return { ...frame, steps: frame.steps.filter((s) => s.seq > sinceSeq) };
  }

  async listJobs(limit: number): Promise<DiscoveryRunList> {
    this.calls.list.push(limit);
    const list = this.options.history === "empty" ? W3.listEmpty() : W3.listOk();
    if (this.active) list.running_job_id = W3.running().job.job_id;
    return list;
  }
}
