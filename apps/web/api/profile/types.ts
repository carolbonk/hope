export { ProblemError, type FieldError } from "@/api/http";

// Client view of H1's hackathon profile endpoints (docs/specs/features/H1-sign-in-and-profile.md).
export type TaxStatus =
  | "501c3_public_charity"
  | "501c3_private_foundation"
  | "501c4"
  | "501c6"
  | "fiscally_sponsored"
  | "government"
  | "tribal"
  | "other";

export type BudgetBand = "<250k" | "250k-1m" | "1m-5m" | "5m-25m" | ">25m";

export interface BasicsForm {
  legal_name: string;
  ein: string;
  tax_status: TaxStatus;
  hq_city: string;
  hq_state: string;
  service_area: string[];
  website: string | null;
}

export interface MissionForm {
  mission_statement: string;
  vision_statement: string | null;
  values: string[];
}

export interface BudgetForm {
  budget_band: BudgetBand | null;
  annual_operating_budget_usd: number | null;
  fiscal_year_end: string;
}

export interface ProgramForm {
  program_id: string | null;
  name: string;
  description: string;
  people_served: string;
  annual_served: number | null;
  age_range: string | null;
}

export interface ProfileForm {
  basics: BasicsForm;
  mission: MissionForm;
  ntee_codes: string[];
  budget: BudgetForm;
  programs: ProgramForm[];
}

export interface ProfileView {
  version: number;
  updated_at: string;
  updated_by: string;
  onboarding_complete: boolean;
  form: ProfileForm;
  ntee_labels: Record<string, string>;
  etag: string;
}

/** RFC 7807 problem from the API, keeping `code` and field `errors[]`. */
export interface ProfileApi {
  /** Resolves `null` when no profile exists yet (404 `profile_not_found`). */
  getProfile(): Promise<ProfileView | null>;
  saveProfile(form: ProfileForm, etag?: string): Promise<ProfileView>;
  /** `PATCH /v1/profile`: replaces the given top-level sections. Used only by `lib/hope/sync/profile.ts`. */
  patchProfile(sections: ProfileSections, etag: string): Promise<ProfileView>;
}

export type ProfileSections = Partial<ProfileForm>;
