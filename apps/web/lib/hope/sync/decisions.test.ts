import { readFileSync } from "node:fs";
import { join } from "node:path";

const API = "http://api.test";
const MOCKS = join(__dirname, "..", "..", "..", "..", "..", "contracts", "mocks", "w4");
const OUTBOX = "hope:sync:decisions:v1";
const G1 = "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10";
const G2 = "5d1c7a90-2b3e-4f61-9c8d-0e1f2a3b4c5d";
const G3 = "0b9f5c3e-1d2a-4c6b-9e8f-7a6b5c4d3e21";

/** A `contracts/mocks/w4/<name>.json` mock as a fetch `Response`. */
function w4(name: string): Response {
  const mock = JSON.parse(readFileSync(join(MOCKS, `${name}.json`), "utf8")) as { status: number; headers: Record<string, string>; body: unknown };
  return new Response(JSON.stringify(mock.body), { status: mock.status, headers: { "content-type": "application/json", ...mock.headers } });
}

function problem(status: number, code: string): Response {
  const body = { type: "about:blank", title: code, status, code };
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/problem+json" } });
}

const onlineListeners: EventListener[] = [];

/** Imports a fresh adapter (a page load) with sync on or off. */
async function load(on = true) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_HOPE_API_URL", on ? API : "");
  const add = vi.spyOn(window, "addEventListener");
  const mod = await import("./decisions");
  for (const [type, fn] of add.mock.calls) if (type === "online") onlineListeners.push(fn as EventListener);
  add.mockRestore();
  return mod;
}

function stubFetch(...responses: (Response | Error)[]) {
  const fetch = vi.fn(() => {
    const next = responses.shift() ?? w4("grants.save/ok");
    return next instanceof Error ? Promise.reject(next) : Promise.resolve(next);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

type FetchMock = { mock: { calls: unknown[][] } };
const calls = (fetch: FetchMock) =>
  fetch.mock.calls.map((args) => {
    const [url, init] = args as unknown as [string, RequestInit];
    return { url, method: init.method, body: init.body, credentials: init.credentials };
  });
const urls = (fetch: FetchMock) => calls(fetch).map((c) => c.url);
const outbox = () => JSON.parse(window.localStorage.getItem(OUTBOX) ?? "null");
const tick = () => new Promise((resolve) => setTimeout(resolve, 20));

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  for (const fn of onlineListeners.splice(0)) window.removeEventListener("online", fn);
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("maps status to endpoint", async () => {
  const fetch = stubFetch(w4("grants.save/ok"), w4("grants.pass/ok"), w4("grants.reset/ok"));
  const { mirrorDecision } = await load();
  mirrorDecision(G1, "saved");
  await tick();
  mirrorDecision(G2, "passed");
  await tick();
  mirrorDecision(G3, "new");
  await tick();
  expect(calls(fetch)).toEqual([
    { url: `${API}/v1/grants/${G1}/save`, method: "POST", body: undefined, credentials: "include" },
    { url: `${API}/v1/grants/${G2}/pass`, method: "POST", body: "{}", credentials: "include" },
    { url: `${API}/v1/grants/${G3}/reset`, method: "POST", body: undefined, credentials: "include" },
  ]);
  expect(outbox()).toEqual({ version: 1, pending: {} });
});

it("skips demo ids", async () => {
  const fetch = stubFetch();
  const { mirrorDecision } = await load();
  mirrorDecision("opp-tidal-sponsor", "saved");
  mirrorDecision("not-a-uuid", "passed");
  await tick();
  expect(fetch).not.toHaveBeenCalled();
  expect(outbox()).toBeNull();
});

it("coalesces per grant", async () => {
  const fetch = stubFetch(w4("grants.pass/ok"));
  const { mirrorDecision } = await load();
  mirrorDecision(G1, "saved");
  mirrorDecision(G1, "new");
  mirrorDecision(G1, "passed");
  expect(Object.keys(outbox().pending)).toEqual([G1]);
  expect(outbox().pending[G1]).toMatchObject({ status: "passed", attempts: 0 });
  await tick();
  expect(urls(fetch)).toEqual([`${API}/v1/grants/${G1}/pass`]);
  expect(outbox().pending).toEqual({});
});

it("a newer intent during a request is sent after it", async () => {
  let release: (r: Response) => void = () => {};
  const fetch = vi.fn(() => (fetch.mock.calls.length === 1 ? new Promise<Response>((r) => (release = r)) : Promise.resolve(w4("grants.reset/ok"))));
  vi.stubGlobal("fetch", fetch);
  const { mirrorDecision } = await load();
  mirrorDecision(G1, "saved");
  await tick();
  mirrorDecision(G1, "new");
  release(w4("grants.save/ok"));
  await tick();
  expect(urls(fetch as never)).toEqual([`${API}/v1/grants/${G1}/save`, `${API}/v1/grants/${G1}/reset`]);
  expect(outbox().pending).toEqual({});
});

it("retries with backoff", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  const offline = () => new TypeError("Failed to fetch");
  const fetch = stubFetch(offline(), problem(503, "unavailable"), offline(), offline(), offline(), w4("grants.save/ok"));
  const { mirrorDecision } = await load();
  mirrorDecision(G1, "saved");
  await vi.advanceTimersByTimeAsync(0);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(outbox().pending[G1].attempts).toBe(1);

  for (const [delay, attempts] of [
    [2_000, 2],
    [8_000, 3],
    [30_000, 4],
    [60_000, 5],
  ] as const) {
    await vi.advanceTimersByTimeAsync(delay - 1);
    expect(fetch).toHaveBeenCalledTimes(attempts - 1);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetch).toHaveBeenCalledTimes(attempts);
    expect(outbox().pending[G1].attempts).toBe(attempts);
  }

  await vi.advanceTimersByTimeAsync(60 * 60_000);
  expect(fetch).toHaveBeenCalledTimes(5);
  window.dispatchEvent(new Event("online"));
  await vi.advanceTimersByTimeAsync(0);
  expect(fetch).toHaveBeenCalledTimes(6);
  expect(outbox().pending).toEqual({});
});

it("new decisions wait for the backoff", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  const fetch = stubFetch(new TypeError("Failed to fetch"), w4("grants.save/ok"), w4("grants.pass/ok"), w4("grants.save/ok"));
  const { mirrorDecision } = await load();
  mirrorDecision(G1, "saved");
  await vi.advanceTimersByTimeAsync(500);
  mirrorDecision(G2, "passed");
  await vi.advanceTimersByTimeAsync(100);
  mirrorDecision(G3, "saved");
  await vi.advanceTimersByTimeAsync(100);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(outbox().pending[G1].attempts).toBe(1);
  await vi.advanceTimersByTimeAsync(1_300);
  expect(urls(fetch)).toEqual([`${API}/v1/grants/${G1}/save`, `${API}/v1/grants/${G1}/save`, `${API}/v1/grants/${G2}/pass`, `${API}/v1/grants/${G3}/save`]);
  expect(outbox().pending).toEqual({});
});

it("drops 404 and 422", async () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  const fetch = stubFetch(w4("grants.save/not_found"), w4("grants.pass/invalid_reason"), w4("grants.save/ok"));
  const { mirrorDecision } = await load();
  mirrorDecision(G1, "saved");
  mirrorDecision(G2, "passed");
  mirrorDecision(G3, "saved");
  await tick();
  expect(urls(fetch)).toEqual([`${API}/v1/grants/${G1}/save`, `${API}/v1/grants/${G2}/pass`, `${API}/v1/grants/${G3}/save`]);
  expect(outbox().pending).toEqual({});
  expect(warn).toHaveBeenCalledWith("decision sync dropped", { grantId: G1, code: "grant_not_found" });
  expect(warn).toHaveBeenCalledWith("decision sync dropped", { grantId: G2, code: "invalid_reason" });
});

it("keeps entries on 401", async () => {
  const fetch = stubFetch(problem(401, "not_signed_in"));
  const { mirrorDecision } = await load();
  mirrorDecision(G1, "saved");
  mirrorDecision(G2, "passed");
  await tick();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(outbox().pending).toEqual({
    [G1]: expect.objectContaining({ status: "saved", attempts: 0 }),
    [G2]: expect.objectContaining({ status: "passed", attempts: 0 }),
  });
});

it("no-op when sync is off", async () => {
  const fetch = stubFetch();
  const add = vi.spyOn(window, "addEventListener");
  const { mirrorDecision, flushDecisions } = await load(false);
  window.localStorage.setItem(OUTBOX, JSON.stringify({ version: 1, pending: { [G1]: { status: "saved", attempts: 0, at: "2026-11-07T12:00:00.000Z" } } }));
  const before = window.localStorage.getItem(OUTBOX);
  expect(mirrorDecision(G2, "saved")).toBeUndefined();
  await expect(flushDecisions()).resolves.toBeUndefined();
  await tick();
  expect(fetch).not.toHaveBeenCalled();
  expect(window.localStorage.getItem(OUTBOX)).toBe(before);
  expect(add.mock.calls.some(([type]) => type === "online")).toBe(false);
});

it("never throws", async () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  const state = JSON.stringify({ version: 1, decisions: { [G1]: { decision: "saved", at: "x" } } });
  window.localStorage.setItem("hope:state:v1", state);
  vi.stubGlobal(
    "fetch",
    vi.fn(() => {
      throw new Error("boom");
    }),
  );
  const { mirrorDecision, flushDecisions } = await load();

  window.localStorage.setItem(OUTBOX, "{not json");
  expect(() => mirrorDecision(G1, "saved")).not.toThrow();
  await expect(flushDecisions()).resolves.toBeUndefined();

  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("quota");
  });
  expect(() => mirrorDecision(G2, "passed")).not.toThrow();
  await expect(flushDecisions()).resolves.toBeUndefined();
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("denied");
  });
  expect(() => mirrorDecision(G3, "new")).not.toThrow();
  await expect(flushDecisions()).resolves.toBeUndefined();
  await tick();
  vi.restoreAllMocks();
  expect(window.localStorage.getItem("hope:state:v1")).toBe(state);
});

it("replays the outbox after reload", async () => {
  window.localStorage.setItem(
    OUTBOX,
    JSON.stringify({
      version: 1,
      pending: {
        [G2]: { status: "passed", attempts: 5, at: "2026-11-07T12:00:02.000Z" },
        [G1]: { status: "saved", attempts: 2, at: "2026-11-07T12:00:01.000Z" },
      },
    }),
  );
  const fetch = stubFetch(w4("grants.save/ok"), w4("grants.pass/ok"));
  const { flushDecisions } = await load();
  await flushDecisions();
  expect(urls(fetch)).toEqual([`${API}/v1/grants/${G1}/save`, `${API}/v1/grants/${G2}/pass`]);
  expect(outbox().pending).toEqual({});
});

const page = (ids: string[], total = ids.length) =>
  new Response(JSON.stringify({ items: ids.map((grant_id) => ({ grant_id })), total }), { status: 200, headers: { "content-type": "application/json" } });

/** `GET /v1/grants?status=…` answered from `lists`; posts get `grants.save/ok`. */
function stubLists(lists: Record<string, string[]>, total?: Record<string, number>) {
  const fetch = vi.fn((url: string) => {
    const q = new URL(url).searchParams;
    const status = q.get("status");
    if (!status) return Promise.resolve(w4("grants.save/ok"));
    const offset = Number(q.get("offset"));
    const all = lists[status] ?? [];
    return Promise.resolve(page(all.slice(offset, offset + Number(q.get("limit"))), total?.[status] ?? all.length));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

it("loads saved and passed grants from the server", async () => {
  const many = Array.from({ length: 101 }, (_, i) => `00000000-0000-4000-8000-${String(i).padStart(12, "0")}`);
  const fetch = stubLists({ saved: [G1, ...many], passed: [G2] });
  const { loadRemoteDecisions } = await load();
  const remote = await loadRemoteDecisions();
  expect(remote?.decisions[G1]).toBe("saved");
  expect(remote?.decisions[many[100]!]).toBe("saved");
  expect(remote?.decisions[G2]).toBe("passed");
  expect(Object.keys(remote!.decisions)).toHaveLength(103);
  expect(urls(fetch)).toEqual([
    `${API}/v1/grants?status=saved&include_past=true&limit=100&offset=0`,
    `${API}/v1/grants?status=passed&include_past=true&limit=100&offset=0`,
    `${API}/v1/grants?status=saved&include_past=true&limit=100&offset=100`,
  ]);
  expect(calls(fetch).every((c) => c.credentials === "include")).toBe(true);
});

it("reports grants pending in the outbox or decided during the load as local", async () => {
  window.localStorage.setItem(OUTBOX, JSON.stringify({ version: 1, pending: { [G1]: { status: "passed", attempts: 5, at: "2026-11-07T12:00:00.000Z" } } }));
  stubLists({ saved: [G1, G2], passed: [] });
  const { loadRemoteDecisions, mirrorDecision } = await load();
  const loading = loadRemoteDecisions();
  mirrorDecision(G3, "passed");
  const remote = await loading;
  await tick();
  expect(outbox().pending[G3]).toBeUndefined();
  expect(remote?.localIds()).toEqual(new Set([G1, G3]));
});

it("loads nothing with sync off or on an error", async () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  const fetch = stubFetch(problem(401, "not_signed_in"), new Error("offline"));
  const off = await load(false);
  await expect(off.loadRemoteDecisions()).resolves.toBeNull();
  expect(fetch).not.toHaveBeenCalled();
  const { loadRemoteDecisions } = await load();
  await expect(loadRemoteDecisions()).resolves.toBeNull();
  await expect(loadRemoteDecisions()).resolves.toBeNull();
  expect(window.localStorage.getItem("hope:state:v1")).toBeNull();
});
