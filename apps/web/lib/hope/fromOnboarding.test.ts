import { beforeEach, describe, expect, it } from "vitest";
import type { ProfileForm } from "@/api/profile/types";
import { profileFromOnboarding, seedHopeProfile } from "./fromOnboarding";
import { HOPE_KEY, emptyProfile } from "./store";

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
