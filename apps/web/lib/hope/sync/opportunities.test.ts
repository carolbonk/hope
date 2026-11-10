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
    expect(rich.geography).toEqual(["United States"]);
    expect(rich.purpose).toBe("general_operating");
    expect(rich.amountMin).toBe(10000);
    expect(rich.federal).toBe(true);
    expect(rich.docs).toEqual(["uei", "sam"]);
    expect(toOpportunity(card({ title: "Capital campaign", summary: "Building fund" }))!.purpose).toBe("capital");
    expect(toOpportunity(card({ title: "Dental care", summary: "Rural clinics" }))!.focusAreas).toEqual(["health"]);
    expect(toOpportunity(card({ title: "Arts", summary: "Murals" }))!.focusAreas).toEqual(["arts"]);
    const local = toOpportunity(card({ eligibility_summary: "Nonprofits serving Chelan County, WA or Douglas County, WA" }))!;
    expect(local.geography).toEqual(["Chelan County, WA", "Douglas County, WA"]);
    expect(toOpportunity(card({ title: "Mental health access", summary: "Behavioral health counseling" }))!.focusAreas).toEqual(["mental_health"]);
    const county = toOpportunity(card({ url: "https://www.grants.gov/search-results-detail/1", eligibility_summary: "Applicants must serve Yakima County, WA" }))!;
    expect(county.geography).toEqual(["Yakima County, WA"]);
    const example = toOpportunity(card({ url: "https://www.grants.gov/search-results-detail/2", summary: "Past awards reached Yakima County, WA", eligibility_summary: "Nonprofits" }))!;
    expect(example.geography).toEqual(["United States"]);
  });

  it("needs check rules", async () => {
    const { needsCheck } = await load(false);
    const usd = { amount_minor: 100, currency: "USD" };
    expect(needsCheck({ amount_max: null, deadline: "2027-01-01" })).toBe("no_amount");
    expect(needsCheck({ amount_max: usd, deadline: null })).toBe("no_deadline");
    expect(needsCheck({ amount_max: { amount_minor: 1, currency: "CAD" }, deadline: "2027-01-01" })).toBe("currency");
    expect(needsCheck({ amount_max: usd, deadline: "2027-01-01" })).toBeNull();
  });

  it("requirements never meet by default", async () => {
    const { toOpportunity } = await load(false);
    expect(toOpportunity(card({ eligibility_summary: null }))!.requirements).toEqual([
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

describe("incomplete grants", () => {
  it("keep what is known and leave the rest null, never a guess", async () => {
    const { isCheck, isRolling, toOpportunity } = await load(false);
    expect(isCheck(toOpportunity(card()))).toBe(false);
    const noDate = toOpportunity(card({ deadline: null, deadline_text: "by 5 p.m. PDT on Sept. 18" }));
    expect(noDate).toMatchObject({
      id: "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10",
      name: "Rural Oral Health Access Grant 2027",
      amountMin: 75000,
      amountMax: 75000,
      amountText: "up to $75,000 per year",
      otherCurrency: null,
      deadline: null,
      deadlineText: "by 5 p.m. PDT on Sept. 18",
      source: { verifiedAt: "2026-11-07" },
    });
    expect(isCheck(noDate)).toBe(true);
    expect(isRolling(noDate)).toBe(false);
    expect(isRolling(toOpportunity(card({ deadline: null, deadline_text: "Rolling" })))).toBe(true);
    expect(isRolling(toOpportunity(card({ deadline: null, deadline_text: "Applications are accepted year-round" })))).toBe(true);
    expect(toOpportunity(card({ amount_max: null, amount_text: null }))).toMatchObject({ amountMin: null, amountMax: null, amountText: null, deadline: "2027-03-03" });
    expect(toOpportunity(card({ amount_max: { amount_minor: 5_000_000, currency: "CAD" } }))).toMatchObject({ amountMin: null, amountMax: null, otherCurrency: "CAD" });
  });

  it("join the catalog with the complete ones, saved and passed included", async () => {
    const { fetchOpportunities, isCheck } = await load(true);
    const fetch = vi.fn(async (url: string) => {
      const status = new URL(url).searchParams.get("status");
      if (status === "new") return json({ items: [card(), card({ grant_id: "g-check", amount_max: null })] });
      return json({ items: status === "saved" ? [card({ grant_id: "g-saved", deadline: null })] : [] });
    });
    vi.stubGlobal("fetch", fetch);
    const opps = (await fetchOpportunities())!;
    expect(opps.map((o) => [o.id, isCheck(o)])).toEqual([
      ["3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10", false],
      ["g-check", true],
      ["g-saved", true],
    ]);
    expect(fetch).toHaveBeenCalledTimes(3);
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
    // The mock's youth grant has no deadline: it stays in the catalog with the date unknown.
    expect(opps.find((o) => o.name.includes("Youth Mental"))).toMatchObject({ deadline: null });
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
