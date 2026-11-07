// Every request HttpApi makes must match a route in the pillar OpenAPI snapshot.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { HttpApi } from "./http";

const spec = JSON.parse(
  readFileSync(resolve(__dirname, "../../../../services/pillar/tests/snapshots/openapi.json"), "utf8"),
) as { paths: Record<string, Record<string, unknown>> };

const routes = Object.entries(spec.paths).flatMap(([path, ops]) =>
  Object.keys(ops).map((method) => ({ method: method.toUpperCase(), re: new RegExp(`^${path.replace(/\{[^}]+\}/g, "[^/]+")}$`) })),
);

const workflow = { workflow_id: "wf-1", opportunity_id: "o-1", state: "Planning", updated_at: null, gates: [], timeline: [] };
const bodies: Record<string, unknown> = {
  matrix: { items: [{ opportunity_id: "o-1", title: "T", state: "Planning", composite_score: 1, recommendation: null, internal_deadline: null, application_due: null, workflow_id: "wf-1" }], next_cursor: null },
  workflows: workflow,
  opportunities: { title: "T", normalized: { title: "T" } },
  profile: { version: 1, profile: {}, valid_from: "x" },
  signals: { request_id: "r", decision: "approve" },
  authorize: { request_id: "r", decision: "approve", tracking_id: "t" },
};

it("only calls routes that exist in services/pillar/tests/snapshots/openapi.json", async () => {
  const calls: { method: string; path: string }[] = [];
  const fetchImpl = vi.fn<typeof fetch>(async (input, init) => {
    const url = new URL(String(input));
    calls.push({ method: init?.method ?? "GET", path: url.pathname });
    const key = Object.keys(bodies).find((k) => url.pathname.includes(k === "profile" && init?.method === "PATCH" ? "profile" : k));
    const body = init?.method === "PATCH" ? { proposal_id: "p", status: "accepted", protected_paths: [] } : bodies[key ?? ""] ?? {};
    return new Response(JSON.stringify(body), { status: 200 });
  });
  const api = new HttpApi({ baseUrl: "http://x", tenantId: "t", agencyId: "a-1", fetchImpl });
  await api.getMatrix("a-1");
  await api.getOpportunity("o-1");
  await api.listWorkflows();
  await api.listHitlRequests(["aor"]);
  await api.getWorkflow("wf-1");
  await api.submitSignal("wf-1", "HITL-1", { decision: "approve", artifact_hash: "h", comment: null });
  await api.submitSignal("wf-1", "HITL-5", { decision: "approve", artifact_hash: "h", comment: null }, { requestId: "r-5" });
  await api.getProfile("a-1");
  await api.patchProfile("a-1", { capacity: {} as never }, '"1"');

  expect(calls.length).toBeGreaterThan(8);
  const unknown = calls.filter((c) => !routes.some((r) => r.method === c.method && r.re.test(c.path)));
  expect(unknown).toEqual([]);
});
