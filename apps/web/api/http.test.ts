const API = "http://api.test";

async function load() {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_HOPE_API_URL", API);
  return import("./http");
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown, type = "application/json") =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": type } });

it("is offline without an API URL", async () => {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_HOPE_API_URL", "");
  const http = await import("./http");
  expect(http.online).toBe(false);
});

it("sends credentials and JSON, and parses JSON", async () => {
  const { apiFetch, online } = await load();
  const fetch = vi.fn().mockResolvedValue(json(200, { ok: true }));
  vi.stubGlobal("fetch", fetch);
  expect(online).toBe(true);
  await expect(apiFetch("/v1/x", { method: "POST", body: JSON.stringify({ a: 1 }) })).resolves.toEqual({ ok: true });
  const [url, init] = fetch.mock.calls[0]!;
  expect(url).toBe(`${API}/v1/x`);
  expect(init.credentials).toBe("include");
  expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
});

it("returns undefined for 204", async () => {
  const { apiFetch } = await load();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
  await expect(apiFetch("/v1/auth/logout", { method: "POST" })).resolves.toBeUndefined();
});

it("throws a ProblemError with code and errors", async () => {
  const { apiFetch, ProblemError } = await load();
  const errors = [{ field: "password", code: "weak_password", message: "Use at least 8 characters." }];
  const body = { type: "about:blank", title: "Password too short", status: 422, code: "weak_password", errors };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(422, body, "application/problem+json")));
  const err = await apiFetch("/v1/auth/signup").catch((e: unknown) => e);
  expect(err).toBeInstanceOf(ProblemError);
  expect(err).toMatchObject({ status: 422, code: "weak_password", message: "Password too short", errors });
});

it("falls back to http_<status> without a code", async () => {
  const { apiFetch } = await load();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("oops", { status: 502, statusText: "Bad Gateway" })));
  await expect(apiFetch("/v1/me")).rejects.toMatchObject({ status: 502, code: "http_502" });
});

it("normalises network failures", async () => {
  const { apiFetch } = await load();
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
  await expect(apiFetch("/v1/me")).rejects.toMatchObject({ status: 0, code: "network_error" });
});

it("dispatches hope:unauthorized on 401 before throwing", async () => {
  const { apiFetch } = await load();
  const heard = vi.fn();
  window.addEventListener("hope:unauthorized", heard);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(401, { code: "not_signed_in", title: "Sign in to continue" })));
  await expect(apiFetch("/v1/me")).rejects.toMatchObject({ status: 401, code: "not_signed_in" });
  expect(heard).toHaveBeenCalledTimes(1);
  window.removeEventListener("hope:unauthorized", heard);
});

it("profile types re-export the same ProblemError", async () => {
  vi.resetModules();
  const http = await import("./http");
  const profile = await import("./profile/types");
  expect(profile.ProblemError).toBe(http.ProblemError);
});
