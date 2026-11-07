import { ApiError, PreconditionFailedError, StaleArtifactError } from "./errors";
import { HttpApi, type HttpApiConfig } from "./http";

type Reply = { status: number; body: unknown; headers?: Record<string, string> };

function mockFetch(...replies: Reply[]) {
  let i = 0;
  return vi.fn<typeof fetch>(async () => {
    const r = replies[Math.min(i++, replies.length - 1)] ?? { status: 200, body: {} };
    return new Response(JSON.stringify(r.body), { status: r.status, headers: r.headers });
  });
}

const call = (f: ReturnType<typeof mockFetch>, n = 0) => {
  const [url, init] = f.mock.calls[n] ?? [];
  return { url: String(url), init: init as RequestInit, headers: (init?.headers ?? {}) as Record<string, string> };
};

const api = (f: typeof fetch, extra: Partial<HttpApiConfig> = {}) =>
  new HttpApi({ baseUrl: "http://x/", tenantId: "t-1", agencyId: "a-1", userId: "dana", roles: ["aor", "cfo"], fetchImpl: f, ...extra });

const gate = (over: Record<string, unknown> = {}) => ({
  request_id: "r-1",
  gate: "HITL-1",
  status: "open",
  artifact_hash: "sha256:a",
  approver_roles: ["cfo"],
  due_at: null,
  summary: "Go/no-go",
  decision: null,
  decided_by: null,
  requested_at: "2026-11-01T00:00:00Z",
  decided_at: null,
  ...over,
});

describe("HttpApi (pillar /v1)", () => {
  it("prefixes /v1 and sends the dev principal headers", async () => {
    const f = mockFetch({ status: 200, body: { items: [], next_cursor: null } });
    await api(f).getMatrix("a-1", { limit: 50, min_score: 60 });
    const { url, headers } = call(f);
    expect(url).toBe("http://x/v1/agencies/a-1/matrix?limit=50&min_score=60");
    expect(headers).toMatchObject({ "X-Hope-Tenant": "t-1", "X-Hope-User": "dana", "X-Hope-Roles": "aor,cfo" });
  });

  it("maps summary matrix items to ranked rows flagged as summary", async () => {
    const item = { opportunity_id: "o-1", title: "T", state: "Screened", composite_score: 71.5, recommendation: "pursue", internal_deadline: null, application_due: null, workflow_id: "wf-1" };
    const page = await api(mockFetch({ status: 200, body: { items: [item], next_cursor: "c" } })).getMatrix("a-1");
    expect(page.detail).toBe("summary");
    expect(page.next_cursor).toBe("c");
    expect(page.rows[0]).toMatchObject({ opportunity_id: "o-1", rank: 1, composite_score: 71.5, recommendation: "pursue", eligibility: "needs_review" });
  });

  it("unwraps the normalized opportunity", async () => {
    const f = mockFetch({ status: 200, body: { opportunity_id: "o-1", title: "T", normalized: { opportunity_id: "o-1", title: "Norm" }, provenance: {} } });
    expect((await api(f).getOpportunity("o-1")).title).toBe("Norm");
  });

  it("posts signals with artifact_hash, X-Hope-Mfa on step-up, and maps the stale 409", async () => {
    const f = mockFetch({ status: 409, body: { detail: "artifact_hash is stale; review the current artifact" } });
    const err = await api(f)
      .submitSignal("wf-1", "HITL-2", { decision: "approve", artifact_hash: "sha256:old", comment: null }, { stepUpToken: "tok" })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(StaleArtifactError);
    const { url, init, headers } = call(f);
    expect(url).toBe("http://x/v1/workflows/wf-1/signals/HITL-2");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ decision: "approve", artifact_hash: "sha256:old", comment: null });
    expect(headers["X-Hope-Mfa"]).toBe("true");
  });

  it("keeps other 409s (already decided) as plain API errors", async () => {
    const f = mockFetch({ status: 409, body: { detail: "gate request is decided" } });
    const err = await api(f).submitSignal("wf-1", "HITL-1", { decision: "approve", artifact_hash: "h", comment: null }).catch((e: unknown) => e);
    expect(err).not.toBeInstanceOf(StaleArtifactError);
    expect((err as ApiError).message).toBe("gate request is decided");
  });

  it("authorizes HITL-5 approvals through /packages/{request_id}/authorize", async () => {
    const f = mockFetch({ status: 202, body: { request_id: "r-5", event_id: "e", decision: "approve", tracking_id: "trk-1" } });
    const receipt = await api(f).submitSignal("wf-1", "HITL-5", { decision: "approve", artifact_hash: "sha256:m", comment: "ok" }, { stepUpToken: "tok", requestId: "r-5" });
    const { url, init } = call(f);
    expect(url).toBe("http://x/v1/packages/r-5/authorize");
    expect(JSON.parse(String(init.body))).toEqual({ manifest_hash: "sha256:m", channel: "grants_gov", comment: "ok" });
    expect(receipt).toMatchObject({ request_id: "r-5", gate: "HITL-5", tracking_id: "trk-1" });
  });

  it("builds the inbox from matrix workflows, keeping open gates for the user's roles", async () => {
    const item = { opportunity_id: "o-1", title: "T", state: "AwaitingGoNoGo", composite_score: 1, recommendation: null, internal_deadline: null, application_due: null, workflow_id: "wf-1" };
    const wf = { workflow_id: "wf-1", opportunity_id: "o-1", agency_id: "a-1", state: "AwaitingGoNoGo", updated_at: null, timeline: [], gates: [gate(), gate({ request_id: "r-2", approver_roles: ["board"] }), gate({ request_id: "r-3", status: "decided" })] };
    const f = mockFetch({ status: 200, body: { items: [item], next_cursor: null } }, { status: 200, body: wf });
    const requests = await api(f).listHitlRequests(["cfo"]);
    expect(requests.map((r) => r.request_id)).toEqual(["r-1"]);
    expect(requests[0]).toMatchObject({ workflow_id: "wf-1", tenant_id: "t-1", artifact_hash: "sha256:a" });
    expect(call(f, 1).url).toBe("http://x/v1/workflows/wf-1");
  });

  it("maps the workflow view with the opportunity title and event log", async () => {
    const wf = {
      workflow_id: "wf-1",
      opportunity_id: "o-1",
      agency_id: "a-1",
      state: "Planning",
      updated_at: "2026-11-02T00:00:00Z",
      timeline: [{ event_id: "e1", event_type: "opportunity.recommended", occurred_at: "2026-11-01T00:00:00Z" }],
      gates: [gate({ status: "decided", decision: "go", decided_by: "dana", decided_at: "2026-11-01T12:00:00Z" })],
    };
    const f = mockFetch({ status: 200, body: wf }, { status: 200, body: { title: "T", normalized: { title: "Rural Health" } } });
    const view = await api(f).getWorkflow("wf-1");
    expect(view).toMatchObject({ title: "Rural Health", state: "Planning", open_gates: [] });
    expect(view.events?.map((e) => e.label)).toEqual(["Opportunity recommended", "HITL-1 go"]);
  });

  it("reads the profile version as the ETag and patches dotted changes with If-Match", async () => {
    const get = mockFetch({ status: 200, body: { agency_id: "a-1", version: 3, profile: { version: 1 }, valid_from: "2026-01-01T00:00:00Z", recorded_at: "x" }, headers: { ETag: '"3"' } });
    const profile = await api(get).getProfile("a-1");
    expect(profile.etag).toBe('"3"');
    expect(profile.profile.version).toBe(3);

    const patch = mockFetch({ status: 202, body: { proposal_id: "p-1", status: "pending_approval", protected_paths: ["legal", "legal.ein"] } });
    const res = await api(patch).patchProfile("a-1", { legal: undefined, mission: { statement: "m" } as never }, '"3"');
    expect(res).toEqual({ status: "pending_approval", proposal_id: "p-1", gate: "HITL-0", sections: ["legal"] });
    const { init, headers } = call(patch);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ changes: { mission: { statement: "m" } } });
    expect(headers["If-Match"]).toBe('"3"');
  });

  it("reports unprotected proposals as accepted and maps 412", async () => {
    const ok = mockFetch({ status: 202, body: { proposal_id: "p-2", status: "accepted", protected_paths: [] } });
    expect(await api(ok).patchProfile("a-1", { capacity: {} as never }, '"3"')).toEqual({ status: "accepted", proposal_id: "p-2" });
    const stale = mockFetch({ status: 412, body: { detail: "profile is at version 4" } });
    await expect(api(stale).patchProfile("a-1", { capacity: {} as never }, '"3"')).rejects.toBeInstanceOf(PreconditionFailedError);
  });
});
