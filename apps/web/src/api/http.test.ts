import { StaleArtifactError } from "./errors";
import { HttpApi } from "./http";

function mockFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  return vi.fn<typeof fetch>(async () => new Response(JSON.stringify(body), { status, headers }));
}

const call = (f: ReturnType<typeof mockFetch>) => {
  const [url, init] = f.mock.calls[0] ?? [];
  return { url: String(url), init: init as RequestInit, headers: (init?.headers ?? {}) as Record<string, string> };
};

describe("HttpApi", () => {
  it("prefixes /v1 and sends the tenant header", async () => {
    const f = mockFetch(200, { rows: [] });
    await new HttpApi({ baseUrl: "https://api.example.org/", tenantId: "t-1", fetchImpl: f }).getMatrix("a-1", { limit: 50 });
    const { url, headers } = call(f);
    expect(url).toBe("https://api.example.org/v1/agencies/a-1/matrix?limit=50");
    expect(headers["X-Hope-Tenant"]).toBe("t-1");
  });

  it("posts HITL signals with the artifact hash and maps 409 to StaleArtifactError", async () => {
    const f = mockFetch(409, { detail: "stale", current_hash: "sha256:new" });
    const api = new HttpApi({ baseUrl: "http://x", tenantId: "t", fetchImpl: f });
    const err = await api
      .submitSignal("wf-1", "HITL-2", { decision: "approve", artifact_hash: "sha256:old", comment: null }, { stepUpToken: "tok" })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(StaleArtifactError);
    expect((err as StaleArtifactError).currentHash).toBe("sha256:new");
    const { url, init, headers } = call(f);
    expect(url).toBe("http://x/v1/workflows/wf-1/signals/HITL-2");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ decision: "approve", artifact_hash: "sha256:old", comment: null });
    expect(headers["X-Hope-Step-Up"]).toBe("tok");
  });

  it("sends If-Match and returns pending_approval on 202", async () => {
    const f = mockFetch(202, { proposal_id: "p-1", gate: "HITL-0", sections: ["legal"] });
    const res = await new HttpApi({ baseUrl: "http://x", tenantId: "t", fetchImpl: f }).patchProfile("a", { legal: undefined }, 'W/"v3"');
    expect(res).toEqual({ status: "pending_approval", proposal_id: "p-1", gate: "HITL-0", sections: ["legal"] });
    expect(call(f).headers["If-Match"]).toBe('W/"v3"');
  });
});
