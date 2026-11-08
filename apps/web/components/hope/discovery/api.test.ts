import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { DiscoveryProblem, getJob, listJobs, startJob } from "./api";
import { discoveryJobView, discoveryRunList } from "./types";

const W3 = join(__dirname, "..", "..", "..", "..", "..", "contracts", "mocks", "w3");
const read = (p: string) => JSON.parse(readFileSync(join(W3, p), "utf8")) as { status: number; headers: Record<string, string>; body: Record<string, unknown> };
const respond = (p: string) => {
  const m = read(p);
  return new Response(JSON.stringify(m.body), { status: m.status, headers: { "content-type": "application/json", ...m.headers } });
};

afterEach(() => vi.unstubAllGlobals());

it("parses every w3 mock", async () => {
  for (const dir of readdirSync(W3)) {
    for (const file of readdirSync(join(W3, dir))) {
      const m = read(join(dir, file));
      if (file === "request.json") continue;
      if (m.status >= 400) expect(typeof m.body.code).toBe("string");
      else if (dir === "discovery.list") expect(() => discoveryRunList.parse(m.body)).not.toThrow();
      else expect(() => discoveryJobView.parse(m.body)).not.toThrow();
    }
  }
  vi.stubGlobal("fetch", vi.fn(async () => respond("discovery.start/queued.json")));
  await expect(startJob({ focus_keywords: ["dental"], location: null })).resolves.toMatchObject({ job: { status: "queued" } });
  vi.stubGlobal("fetch", vi.fn(async () => respond("discovery.get/done.json")));
  await expect(getJob("j1", 3)).resolves.toMatchObject({ last_seq: 22 });
  vi.stubGlobal("fetch", vi.fn(async () => respond("discovery.list/ok.json")));
  await expect(listJobs(1)).resolves.toMatchObject({ running_job_id: null });
  for (const [name, extra] of [
    ["job_running", { job_id: "0b9f5c3e-1d2a-4c6b-9e8f-7a6b5c4d3e21" }],
    ["daily_limit", { limit: 20, resets_at: "2026-11-09T05:00:00Z" }],
    ["profile_incomplete", { missing: ["mission.mission_statement", "programs"] }],
  ] as const) {
    vi.stubGlobal("fetch", vi.fn(async () => respond(`discovery.start/${name}.json`)));
    const err = await startJob({ focus_keywords: [], location: null }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(DiscoveryProblem);
    expect((err as DiscoveryProblem).code).toBe(name);
    expect((err as DiscoveryProblem).extra).toMatchObject(extra);
  }
  for (const f of ["api.ts", "types.ts", "DiscoveryPanel.tsx"]) {
    const src = readFileSync(join(__dirname, f), "utf8");
    expect(src).not.toMatch(/OPENAI|api[_-]?key|server-only/i);
  }
});
