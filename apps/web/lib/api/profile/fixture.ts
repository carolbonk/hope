import { NTEE_CODES } from "@/lib/api/onboarding/ntee";
import { ProblemError, type ProfileApi, type ProfileForm, type ProfileSections, type ProfileView } from "./types";

export type ProfileFixtureMode = "empty" | "existing" | "invalid" | "conflict" | "network";

export const DEMO_FORM: ProfileForm = {
  basics: {
    legal_name: "Riverbend Community Health Alliance",
    ein: "84-3917265",
    tax_status: "501c3_public_charity",
    hq_city: "Wenatchee",
    hq_state: "WA",
    service_area: ["Chelan County, WA", "Douglas County, WA", "Washington"],
    website: "https://riverbendhealth.example.org/",
  },
  mission: {
    mission_statement:
      "Riverbend Community Health Alliance brings preventive care, dental services and mental health support to rural families in the Columbia River valley, regardless of ability to pay.",
    vision_statement: "Every rural family can reach the care they need within thirty minutes of home.",
    values: ["Care regardless of ability to pay", "Community-led", "Bilingual by default"],
  },
  ntee_codes: ["E32", "F30"],
  budget: { budget_band: "1m-5m", annual_operating_budget_usd: 3_120_000, fiscal_year_end: "06-30" },
  programs: [
    {
      program_id: "prg-mobile-dental",
      name: "Mobile Dental Clinic",
      description: "Two mobile units provide cleanings, sealants and restorative care at schools and farmworker housing.",
      people_served: "Children and adults on Medicaid",
      annual_served: 3200,
      age_range: null,
    },
  ],
};

const labels = (codes: string[]) => Object.fromEntries(codes.map((c) => [c, NTEE_CODES.find((n) => n.code === c)?.label ?? c]));

const view = (form: ProfileForm, version: number): ProfileView => ({
  version,
  updated_at: new Date().toISOString(),
  updated_by: "demo@hope.org",
  onboarding_complete: true,
  form,
  ntee_labels: labels(form.ntee_codes),
  etag: `"${version}"`,
});

/** Offline profile API: in-memory, with switches for the error cases in SC11 section 11. */
export class FixtureProfileApi implements ProfileApi {
  private current: ProfileView | null;
  constructor(
    private mode: ProfileFixtureMode = "empty",
    private readonly delayMs = 0,
  ) {
    this.current = mode === "existing" || mode === "conflict" ? view(DEMO_FORM, 3) : null;
  }

  private wait() {
    return new Promise((r) => setTimeout(r, this.delayMs));
  }

  async getProfile(): Promise<ProfileView | null> {
    await this.wait();
    return this.current ? structuredClone(this.current) : null;
  }

  async saveProfile(form: ProfileForm, etag?: string): Promise<ProfileView> {
    await this.wait();
    if (this.mode === "network") throw new TypeError("Failed to fetch");
    if (this.mode === "invalid")
      throw new ProblemError(422, "validation_error", "Validation failed", [
        { field: "basics.ein", code: "invalid_ein_prefix", message: "This EIN prefix isn't assigned by the IRS. Check the number." },
        { field: "programs.0.description", code: "too_short", message: "Write at least 20 characters." },
      ]);
    if (this.mode === "conflict") throw new ProblemError(409, "version_conflict", "Someone else saved the profile while you were editing.");
    if (this.current && !etag) throw new ProblemError(428, "if_match_required", "If-Match is required.");
    if (this.current && etag !== this.current.etag) throw new ProblemError(409, "version_conflict", "Someone else saved the profile while you were editing.");
    this.current = view(structuredClone(form), (this.current?.version ?? 0) + 1);
    return structuredClone(this.current);
  }

  async patchProfile(sections: ProfileSections, etag: string): Promise<ProfileView> {
    await this.wait();
    if (this.mode === "network") throw new TypeError("Failed to fetch");
    if (this.mode === "invalid")
      throw new ProblemError(422, "validation_error", "Validation failed", [
        { field: "programs.0.description", code: "too_short", message: "Write at least 20 characters." },
      ]);
    if (this.mode === "conflict") throw new ProblemError(409, "version_conflict", "Someone else saved the profile while you were editing.");
    if (!this.current) throw new ProblemError(404, "profile_not_found", "No profile yet.");
    if (etag !== this.current.etag) throw new ProblemError(409, "version_conflict", "Someone else saved the profile while you were editing.");
    this.current = view({ ...this.current.form, ...structuredClone(sections) }, this.current.version + 1);
    return structuredClone(this.current);
  }
}
