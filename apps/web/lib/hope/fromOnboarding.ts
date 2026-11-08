import type { ProfileForm, ProgramForm, TaxStatus } from "@/api/profile/types";
import { bandFor, US_STATES } from "@/features/onboarding/model";
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
  const keepBudget = base.currency !== "USD" && base.annualBudget !== null;
  for (const code of form.ntee_codes) for (const f of NTEE_FOCUS[code.charAt(0)] ?? []) focus.add(f);
  return {
    ...base,
    legalName: form.basics.legal_name,
    country: base.country || "US",
    jurisdiction: form.basics.hq_state,
    website: form.basics.website ?? "",
    legalStatus: is501c3 ? "501c3" : form.basics.tax_status === "fiscally_sponsored" ? "fiscal_sponsor" : "other_nonprofit",
    has501c3: base.has501c3 !== "unknown" ? base.has501c3 : is501c3 ? "yes" : "no",
    usTaxStatus: base.usTaxStatus !== "unknown" ? base.usTaxStatus : form.basics.ein ? "yes" : base.usTaxStatus,
    mission: form.mission.mission_statement,
    vision: form.mission.vision_statement ?? "",
    serviceArea: form.basics.service_area.join("; "),
    focusAreas: [...focus],
    programs: form.programs.map((p, i) => {
      const id = p.program_id ?? `p-${i + 1}`;
      return {
        id,
        name: p.name,
        description: p.description,
        outcomes: base.programs.find((b) => b.id === id)?.outcomes ?? "",
        served: p.annual_served ?? null,
      };
    }),
    annualBudget: keepBudget ? base.annualBudget : (form.budget.annual_operating_budget_usd ?? base.annualBudget),
    currency: keepBudget ? base.currency : "USD",
    fiscalYear: form.budget.fiscal_year_end ? `Fiscal year ends ${form.budget.fiscal_year_end}` : base.fiscalYear,
    completedSteps: Math.max(base.completedSteps, 3),
    updatedAt: new Date().toISOString(),
  };
}

function stateCode(jurisdiction: string): string | null {
  const v = jurisdiction.trim().toLowerCase();
  return US_STATES.find(([code, name]) => code.toLowerCase() === v || name.toLowerCase() === v)?.[0] ?? null;
}

function taxStatus(status: OrgProfile["legalStatus"], base: TaxStatus): TaxStatus {
  const base501c3 = base.startsWith("501c3");
  if (status === "501c3") return base501c3 ? base : "501c3_public_charity";
  if (status === "fiscal_sponsor") return "fiscally_sponsored";
  if (status === "other_nonprofit") return base501c3 ? "other" : base;
  return base;
}

/** Maps the browser profile back onto the server form. Only fields with a `/v1` home are written; the rest keep `base`. */
export function formFromProfile(profile: OrgProfile, base: ProfileForm): ProfileForm {
  const area = profile.serviceArea
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean);
  const usd = profile.currency === "USD" && profile.annualBudget !== null ? Math.round(profile.annualBudget) : null;
  const fiscal = /(\d{2}-\d{2})\s*$/.exec(profile.fiscalYear)?.[1];
  const population = profile.targetPopulation.trim() || base.programs.find((b) => b.people_served)?.people_served || "";
  const programs: ProgramForm[] = profile.programs.map((p) => {
    const old = base.programs.find((b) => b.program_id === p.id);
    return {
      program_id: old ? old.program_id : null,
      name: p.name,
      description: p.description,
      people_served: old ? old.people_served : population,
      annual_served: p.served,
      age_range: old ? old.age_range : null,
    };
  });
  return {
    basics: {
      ...base.basics,
      legal_name: profile.legalName.trim(),
      website: profile.website.trim() || null,
      hq_state: stateCode(profile.jurisdiction) ?? base.basics.hq_state,
      service_area: area.length ? area : base.basics.service_area,
      tax_status: taxStatus(profile.legalStatus, base.basics.tax_status),
    },
    mission: { ...base.mission, mission_statement: profile.mission, vision_statement: profile.vision || null },
    ntee_codes: base.ntee_codes,
    budget:
      usd === null
        ? { ...base.budget, fiscal_year_end: fiscal ?? base.budget.fiscal_year_end }
        : { ...base.budget, budget_band: bandFor(usd), annual_operating_budget_usd: usd, fiscal_year_end: fiscal ?? base.budget.fiscal_year_end },
    programs,
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
