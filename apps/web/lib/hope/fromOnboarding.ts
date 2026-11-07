import type { ProfileForm } from "@/api/profile/types";
import { writeStoredJson } from "./storage";
import { HOPE_KEY, normalizeProfile } from "./store";
import type { HopeState, OrgProfile } from "./types";

const NTEE_FOCUS: Record<string, string[]> = {
  B: ["education"], E: ["health"], F: ["mental_health"], I: ["safety"], O: ["youth", "mentoring"], P: ["family"], A: ["arts"],
};

/** Maps the onboarding wizard's answers onto the Hope profile the discover and workspace screens read. */
export function profileFromOnboarding(form: ProfileForm, base: OrgProfile): OrgProfile {
  const is501c3 = form.basics.tax_status.startsWith("501c3");
  const focus = new Set(base.focusAreas);
  for (const code of form.ntee_codes) for (const f of NTEE_FOCUS[code.charAt(0)] ?? []) focus.add(f);
  return {
    ...base,
    legalName: form.basics.legal_name,
    country: "US",
    jurisdiction: form.basics.hq_state,
    website: form.basics.website ?? "",
    legalStatus: is501c3 ? "501c3" : form.basics.tax_status === "fiscally_sponsored" ? "fiscal_sponsor" : "other_nonprofit",
    has501c3: is501c3 ? "yes" : "no",
    usTaxStatus: form.basics.ein ? "yes" : base.usTaxStatus,
    mission: form.mission.mission_statement,
    vision: form.mission.vision_statement ?? "",
    serviceArea: form.basics.service_area.join("; "),
    focusAreas: [...focus],
    programs: form.programs.map((p, i) => ({
      id: p.program_id ?? `p-${i + 1}`,
      name: p.name,
      description: p.description,
      outcomes: "",
      served: p.annual_served ?? null,
    })),
    annualBudget: form.budget.annual_operating_budget_usd ?? base.annualBudget,
    currency: "USD",
    fiscalYear: form.budget.fiscal_year_end ? `Fiscal year ends ${form.budget.fiscal_year_end}` : base.fiscalYear,
    completedSteps: Math.max(base.completedSteps, 3),
    updatedAt: new Date().toISOString(),
  };
}

export function seedHopeProfile(form: ProfileForm) {
  let state: Partial<HopeState> = {};
  try {
    state = JSON.parse(window.localStorage.getItem(HOPE_KEY) ?? "{}") as Partial<HopeState>;
  } catch {
    state = {};
  }
  const profile = profileFromOnboarding(form, normalizeProfile(state.profile));
  writeStoredJson(HOPE_KEY, { version: 1, decisions: {}, history: [], applications: {}, ...state, profile });
}
