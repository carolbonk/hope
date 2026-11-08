import { beforeEach, describe, expect, it } from "vitest";
import type { ProfileForm } from "@/api/profile/types";
import { DEMO_FORM } from "@/api/profile/fixture";
import { formFromProfile, profileFromOnboarding, seedHopeProfile } from "./fromOnboarding";
import { HOPE_KEY, emptyProfile } from "./store";
import type { OrgProfile } from "./types";

const form: ProfileForm = {
  basics: {
    legal_name: "Tidepath Youth Alliance",
    ein: "12-3456789",
    tax_status: "501c3_public_charity",
    hq_city: "Miami",
    hq_state: "FL",
    service_area: ["Miami-Dade", "Broward"],
    website: "https://tidepath.example.org",
  },
  mission: { mission_statement: "We mentor young people.", vision_statement: null, values: ["equity"] },
  ntee_codes: ["O50", "B90"],
  budget: { budget_band: "250k-1m", annual_operating_budget_usd: 480000, fiscal_year_end: "06-30" },
  programs: [{ program_id: null, name: "Mentors", description: "One-to-one mentoring", people_served: "Teens", annual_served: 120, age_range: null }],
};

describe("profileFromOnboarding", () => {
  it("maps onboarding answers onto the Hope profile", () => {
    const p = profileFromOnboarding(form, emptyProfile());
    expect(p.legalName).toBe("Tidepath Youth Alliance");
    expect(p.has501c3).toBe("yes");
    expect(p.country).toBe("US");
    expect(p.jurisdiction).toBe("FL");
    expect(p.serviceArea).toBe("Miami-Dade; Broward");
    expect(p.annualBudget).toBe(480000);
    expect(p.focusAreas).toEqual(expect.arrayContaining(["youth", "mentoring", "education"]));
    expect(p.programs).toEqual([{ id: "p-1", name: "Mentors", description: "One-to-one mentoring", outcomes: "", served: 120 }]);
    expect(p.completedSteps).toBe(3);
  });

  it("does not claim 501(c)(3) for other tax statuses", () => {
    const p = profileFromOnboarding({ ...form, basics: { ...form.basics, tax_status: "501c4" } }, emptyProfile());
    expect(p.has501c3).toBe("no");
  });
});

describe("seedHopeProfile", () => {
  beforeEach(() => window.localStorage.clear());

  it("keeps existing saved grants and applications", () => {
    window.localStorage.setItem(HOPE_KEY, JSON.stringify({ version: 1, decisions: { "opp-1": "saved" }, history: [], applications: {} }));
    seedHopeProfile(form);
    const state = JSON.parse(window.localStorage.getItem(HOPE_KEY)!);
    expect(state.decisions).toEqual({ "opp-1": "saved" });
    expect(state.profile.legalName).toBe("Tidepath Youth Alliance");
  });
});

const BROWSER_ONLY: (keyof OrgProfile)[] = [
  "publicName", "country", "contactName", "contactEmail", "responsibleName", "responsibleRole", "has501c3", "usTaxStatus",
  "targetPopulation", "servesMinors", "currency", "staffCount", "volunteerCount", "foundedYear", "experience", "fundingNeed",
  "intendedUse", "dossier", "reviews", "reviewRequest", "completedSteps",
];

const browser = (): OrgProfile => ({
  ...profileFromOnboarding(DEMO_FORM, emptyProfile()),
  publicName: "Riverbend Health",
  country: "US",
  contactName: "Dana Okafor",
  contactEmail: "dana@riverbendhealth.example.org",
  responsibleName: "Lee Park",
  responsibleRole: "ED",
  has501c3: "yes",
  usTaxStatus: "yes",
  targetPopulation: "Rural families",
  servesMinors: "yes",
  staffCount: 42,
  volunteerCount: 12,
  foundedYear: 2004,
  experience: "Twenty years of mobile care.",
  fundingNeed: "Dental unit",
  intendedUse: ["program"],
  dossier: { w9: { status: "declared", naReason: "", evidenceRef: "w9.pdf", period: "", expires: "", comments: [] } },
  reviews: { mission: { by: "Lee", at: "2026-11-01T00:00:00Z", note: "", value: "ok", simulated: true } },
  reviewRequest: { at: "2026-11-02T00:00:00Z", delivery: "local_only" },
  completedSteps: 5,
  focusAreas: ["rural_health"],
});

describe("formFromProfile", () => {
  it("formFromProfile mapping", () => {
    const p: OrgProfile = {
      ...browser(),
      legalName: "  Riverbend Health Alliance ",
      website: "",
      jurisdiction: "Oregon",
      serviceArea: "Hood River County, OR; ; Oregon ",
      legalStatus: "fiscal_sponsor",
      vision: "",
      annualBudget: 400_000.4,
      fiscalYear: "Fiscal year ends 12-31",
      programs: [
        { id: "prg-mobile-dental", name: "Mobile Dental", description: "Cleanings at schools and farmworker housing.", outcomes: "x", served: 10 },
        { id: "p-2", name: "Food pantry", description: "Weekly groceries for families in need.", outcomes: "", served: null },
      ],
    };
    const form = formFromProfile(p, DEMO_FORM);
    expect(form.basics).toEqual({
      ...DEMO_FORM.basics,
      legal_name: "Riverbend Health Alliance",
      website: null,
      hq_state: "OR",
      service_area: ["Hood River County, OR", "Oregon"],
      tax_status: "fiscally_sponsored",
    });
    expect(form.mission.vision_statement).toBeNull();
    expect(form.ntee_codes).toEqual(DEMO_FORM.ntee_codes);
    expect(form.budget).toEqual({ budget_band: "250k-1m", annual_operating_budget_usd: 400_000, fiscal_year_end: "12-31" });
    expect(form.programs).toEqual([
      { ...DEMO_FORM.programs[0], name: "Mobile Dental", description: "Cleanings at schools and farmworker housing.", annual_served: 10 },
      { program_id: null, name: "Food pantry", description: "Weekly groceries for families in need.", people_served: "Rural families", annual_served: null, age_range: null },
    ]);

    const odd = formFromProfile({ ...p, jurisdiction: "Narnia", serviceArea: " ; ", currency: "EUR", fiscalYear: "", legalStatus: "unknown" }, DEMO_FORM);
    expect(odd.basics.hq_state).toBe("WA");
    expect(odd.basics.service_area).toEqual(DEMO_FORM.basics.service_area);
    expect(odd.basics.tax_status).toBe("501c3_public_charity");
    expect(odd.budget).toEqual(DEMO_FORM.budget);
    expect(formFromProfile({ ...p, legalStatus: "501c3" }, { ...DEMO_FORM, basics: { ...DEMO_FORM.basics, tax_status: "501c4" } }).basics.tax_status).toBe("501c3_public_charity");
    expect(formFromProfile({ ...p, legalStatus: "other_nonprofit" }, DEMO_FORM).basics.tax_status).toBe("other");
  });

  it("round trip keeps browser-only fields", () => {
    const p = browser();
    const back = profileFromOnboarding(formFromProfile(p, DEMO_FORM), p);
    for (const key of BROWSER_ONLY) expect(back[key]).toEqual(p[key]);
    expect(back.focusAreas).toEqual(expect.arrayContaining(p.focusAreas));
    const eur = { ...p, currency: "EUR" as const, annualBudget: 900_000 };
    const kept = profileFromOnboarding(formFromProfile(eur, DEMO_FORM), eur);
    expect([kept.currency, kept.annualBudget]).toEqual(["EUR", 900_000]);
  });

  it("keeps program outcomes by id", () => {
    const p = browser();
    p.programs = [{ ...p.programs[0]!, outcomes: "1,200 children seen" }];
    const back = profileFromOnboarding(formFromProfile(p, DEMO_FORM), p);
    expect(back.programs[0]).toMatchObject({ id: "prg-mobile-dental", outcomes: "1,200 children seen" });
  });
});
