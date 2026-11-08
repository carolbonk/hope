import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { GrantCard } from "./opportunities";

const MOCKS = join(__dirname, "..", "..", "..", "..", "..", "contracts", "mocks", "w4", "grants.list");
const mockBody = (name: string) => JSON.parse(readFileSync(join(MOCKS, `${name}.json`), "utf8")).body as { items: GrantCard[] };
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

async function load(online: boolean) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_HOPE_API_URL", online ? "http://api.test" : "");
  return import("./opportunities");
}

const card = (over: Partial<GrantCard> = {}): GrantCard => ({ ...mockBody("new").items[0]!, ...over });

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("toOpportunity", () => {
  it("maps grant cards", async () => {
    const { toOpportunity } = await load(false);
    const opp = toOpportunity(card())!;
    expect(opp).toMatchObject({
      id: "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10",
      funder: "Cascade Health Foundation",
      name: "Rural Oral Health Access Grant 2027",
      amountMax: 75000,
      amountMin: 75000,
      currency: "USD",
      deadline: "2027-03-03",
      geography: [],
      fundingType: "grant",
      purpose: "program",
      federal: false,
      funderContext: null,
    });
    expect(opp.docs).toBeUndefined();
    const rich = toOpportunity(
      card({
        title: "Youth Mentoring and Family Safety Grant",
        summary: "General operating support for school-based behavioral health and mural arts with teens.",
        url: "https://grants.hrsa.gov/x",
        amount_min: { amount_minor: 1_000_000, currency: "USD" },
      }),
    )!;
    expect(rich.focusAreas).toEqual(["mentoring", "youth", "family", "mental_health", "safety", "school_based", "capacity", "arts"]);
    expect(rich.purpose).toBe("general_operating");
    expect(rich.amountMin).toBe(10000);
    expect(rich.federal).toBe(true);
    expect(rich.docs).toEqual(["uei", "sam"]);
    expect(toOpportunity(card({ title: "Capital campaign", summary: "Building fund" }))!.purpose).toBe("capital");
    expect(toOpportunity(card({ title: "Dental care", summary: "Rural clinics" }))!.focusAreas).toEqual([]);
  });

  it("needs check rules", async () => {
    const { needsCheck, toOpportunity } = await load(false);
    const usd = { amount_minor: 100, currency: "USD" };
    expect(needsCheck({ amount_max: null, deadline: "2027-01-01" })).toBe("no_amount");
    expect(needsCheck({ amount_max: usd, deadline: null })).toBe("no_deadline");
    expect(needsCheck({ amount_max: { amount_minor: 1, currency: "CAD" }, deadline: "2027-01-01" })).toBe("currency");
    expect(needsCheck({ amount_max: usd, deadline: "2027-01-01" })).toBeNull();
    expect(toOpportunity(card({ deadline: null }))).toBeNull();
    expect(toOpportunity(card({ amount_max: null }))).toBeNull();
    expect(toOpportunity(card({ amount_max: { amount_minor: 1, currency: "GBP" } }))).toBeNull();
  });

  it("requirements never meet by default", async () => {
    const { toOpportunity } = await load(false);
    expect(toOpportunity(card())!.requirements).toEqual([
      { id: "funder_eligibility", label: "Funder's eligibility rules (check the source page)" },
    ]);
    const c3 = "Nonprofits with 501(c)(3) status serving rural Washington counties.";
    expect(toOpportunity(card({ eligibility_summary: c3 }))!.requirements).toEqual([
      { id: "funder_eligibility", label: c3 },
      { id: "c3", label: "501(c)(3)", field: "has501c3", expect: "yes" },
    ]);
  });

  it("source verified", async () => {
    const { toOpportunity } = await load(false);
    expect(toOpportunity(card())!.source).toEqual({
      kind: "verified",
      url: "https://cascadehealth.example.org/grants/rural-oral-health",
      verifiedAt: "2026-11-07",
    });
  });
});

describe("fetchOpportunities", () => {
  it("sync off makes no request", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const { fetchOpportunities } = await load(false);
    await expect(fetchOpportunities()).resolves.toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("empty or error resolves null", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const { fetchOpportunities } = await load(true);
    vi.stubGlobal("fetch", vi.fn(async () => json(mockBody("empty"))));
    await expect(fetchOpportunities()).resolves.toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => json({ code: "not_signed_in" }, 401)));
    await expect(fetchOpportunities()).resolves.toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    await expect(fetchOpportunities()).resolves.toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("not json", { status: 200 })));
    await expect(fetchOpportunities()).resolves.toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => json({ items: [card({ deadline: null })] })));
    await expect(fetchOpportunities()).resolves.toBeNull();
  });

  it("reads new saved and passed", async () => {
    const { fetchOpportunities } = await load(true);
    const passed = card({ grant_id: "g-passed", title: "Passed grant" });
    const fetch = vi.fn(async (url: string, init?: RequestInit) => {
      void init;
      const status = new URL(url).searchParams.get("status");
      return json(status === "new" ? mockBody("new") : status === "saved" ? mockBody("saved") : { items: [passed] });
    });
    vi.stubGlobal("fetch", fetch);
    const opps = (await fetchOpportunities())!;
    expect(fetch.mock.calls.map(([url]) => url)).toEqual(
      ["new", "saved", "passed"].map((s) => `http://api.test/v1/grants?status=${s}&sort=fit&include_past=true&limit=100`),
    );
    expect(fetch.mock.calls[0]![1]).toMatchObject({ credentials: "include" });
    const ids = opps.map((o) => o.id);
    expect(ids).toContain("3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10");
    expect(ids).toContain("g-passed");
    expect(opps.every((o) => o.source.kind === "verified")).toBe(true);
    expect(opps.find((o) => o.name.includes("Youth Mental"))).toBeUndefined();
  });

  it("pages past 100 grants", async () => {
    const { fetchOpportunities } = await load(true);
    const many = Array.from({ length: 130 }, (_, i) => card({ grant_id: `g-${i}` }));
    const fetch = vi.fn(async (url: string) => {
      const q = new URL(url).searchParams;
      if (q.get("status") !== "new") return json({ items: [], total: 0 });
      const offset = Number(q.get("offset") ?? 0);
      return json({ items: many.slice(offset, offset + 100), total: many.length });
    });
    vi.stubGlobal("fetch", fetch);
    expect(await fetchOpportunities()).toHaveLength(130);
    expect(fetch.mock.calls.map(([url]) => url)).toContain(
      "http://api.test/v1/grants?status=new&sort=fit&include_past=true&limit=100&offset=100",
    );
  });
});
