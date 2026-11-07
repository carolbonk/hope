import type { BudgetBand, FieldError, ProfileForm, ProgramForm, TaxStatus } from "@/api/profile";

export const STEPS = [
  { id: "basics", title: "Basics", rail: "Basics", why: "Funders check who you are and where you work. Hope searches by your service area." },
  { id: "mission", title: "Mission and values", rail: "Mission & values", why: "Hope matches grants to what you do and why. Use your own words." },
  { id: "cause", title: "Cause", rail: "Cause (NTEE)", why: "NTEE codes are how funders categorize nonprofits. Pick up to 3; the first is your primary." },
  { id: "budget", title: "Budget", rail: "Budget", why: "Many grants are limited to organizations of a certain size." },
  { id: "programs", title: "Programs", rail: "Programs", why: "Grants fund programs. Tell Hope what you run and who it serves." },
  { id: "review", title: "Review", rail: "Review", why: "Check everything once. You can change it later on your profile." },
] as const;

export type StepId = (typeof STEPS)[number]["id"];
export type Errors = Record<string, string>;

export const TAX_STATUSES: { value: TaxStatus; label: string }[] = [
  { value: "501c3_public_charity", label: "501(c)(3) public charity" },
  { value: "501c3_private_foundation", label: "501(c)(3) private foundation" },
  { value: "501c4", label: "501(c)(4) social welfare" },
  { value: "501c6", label: "501(c)(6) business league" },
  { value: "fiscally_sponsored", label: "Fiscally sponsored project" },
  { value: "government", label: "Government entity" },
  { value: "tribal", label: "Tribal organization" },
  { value: "other", label: "Other" },
];

export const BUDGET_BANDS: { value: BudgetBand; label: string; max: number }[] = [
  { value: "<250k", label: "Under $250K", max: 250_000 },
  { value: "250k-1m", label: "$250K–$1M", max: 1_000_000 },
  { value: "1m-5m", label: "$1M–$5M", max: 5_000_000 },
  { value: "5m-25m", label: "$5M–$25M", max: 25_000_000 },
  { value: ">25m", label: "Over $25M", max: Number.POSITIVE_INFINITY },
];

export const bandFor = (usd: number): BudgetBand => BUDGET_BANDS.find((b) => usd < b.max)!.value;
export const bandLabel = (band: BudgetBand | null) => BUDGET_BANDS.find((b) => b.value === band)?.label ?? "";

export const US_STATES: [string, string][] = [
  ["AL", "Alabama"], ["AK", "Alaska"], ["AZ", "Arizona"], ["AR", "Arkansas"], ["CA", "California"], ["CO", "Colorado"],
  ["CT", "Connecticut"], ["DE", "Delaware"], ["DC", "District of Columbia"], ["FL", "Florida"], ["GA", "Georgia"],
  ["HI", "Hawaii"], ["ID", "Idaho"], ["IL", "Illinois"], ["IN", "Indiana"], ["IA", "Iowa"], ["KS", "Kansas"],
  ["KY", "Kentucky"], ["LA", "Louisiana"], ["ME", "Maine"], ["MD", "Maryland"], ["MA", "Massachusetts"],
  ["MI", "Michigan"], ["MN", "Minnesota"], ["MS", "Mississippi"], ["MO", "Missouri"], ["MT", "Montana"],
  ["NE", "Nebraska"], ["NV", "Nevada"], ["NH", "New Hampshire"], ["NJ", "New Jersey"], ["NM", "New Mexico"],
  ["NY", "New York"], ["NC", "North Carolina"], ["ND", "North Dakota"], ["OH", "Ohio"], ["OK", "Oklahoma"],
  ["OR", "Oregon"], ["PA", "Pennsylvania"], ["PR", "Puerto Rico"], ["RI", "Rhode Island"], ["SC", "South Carolina"],
  ["SD", "South Dakota"], ["TN", "Tennessee"], ["TX", "Texas"], ["UT", "Utah"], ["VT", "Vermont"], ["VA", "Virginia"],
  ["WA", "Washington"], ["WV", "West Virginia"], ["WI", "Wisconsin"], ["WY", "Wyoming"],
];
export const stateName = (code: string) => US_STATES.find(([c]) => c === code)?.[1] ?? code;

export const emptyProgram = (): ProgramForm => ({
  program_id: null,
  name: "",
  description: "",
  people_served: "",
  annual_served: null,
  age_range: null,
});

export const emptyForm = (): ProfileForm => ({
  basics: { legal_name: "", ein: "", tax_status: "501c3_public_charity", hq_city: "", hq_state: "", service_area: [], website: null },
  mission: { mission_statement: "", vision_statement: null, values: [] },
  ntee_codes: [],
  budget: { budget_band: null, annual_operating_budget_usd: null, fiscal_year_end: "12-31" },
  programs: [emptyProgram()],
});

/** Digits only, dash after the 2nd digit: "843917265" -> "84-3917265". */
export function formatEin(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 9);
  return d.length > 2 ? `${d.slice(0, 2)}-${d.slice(2)}` : d;
}

const required = (label: string) => `${label} is required.`;
const tooShort = (n: number) => `Write at least ${n} characters.`;

function text(errors: Errors, path: string, value: string | null | undefined, label: string, min: number, max: number, optional = false) {
  const v = (value ?? "").trim();
  if (!v) {
    if (!optional) errors[path] = required(label);
  } else if (v.length < min) errors[path] = tooShort(min);
  else if (v.length > max) errors[path] = `Keep it under ${max} characters.`;
}

export function validateStep(step: StepId, form: ProfileForm): Errors {
  const e: Errors = {};
  if (step === "basics") {
    const b = form.basics;
    text(e, "basics.legal_name", b.legal_name, "Legal name", 2, 200);
    if (!b.ein) e["basics.ein"] = required("EIN");
    else if (!/^\d{2}-\d{7}$/.test(b.ein)) e["basics.ein"] = "Enter your EIN as 12-3456789.";
    text(e, "basics.hq_city", b.hq_city, "City", 2, 80);
    if (!b.hq_state) e["basics.hq_state"] = required("State");
    if (b.service_area.length === 0) e["basics.service_area"] = required("Service area");
  } else if (step === "mission") {
    text(e, "mission.mission_statement", form.mission.mission_statement, "Mission statement", 20, 2000);
    text(e, "mission.vision_statement", form.mission.vision_statement, "Vision", 0, 2000, true);
  } else if (step === "cause") {
    if (form.ntee_codes.length === 0) e.ntee_codes = "Pick at least one NTEE code.";
  } else if (step === "budget") {
    if (!form.budget.budget_band) e["budget.budget_band"] = required("Budget");
  } else if (step === "programs") {
    form.programs.forEach((p, i) => {
      text(e, `programs.${i}.name`, p.name, "Program name", 2, 120);
      text(e, `programs.${i}.description`, p.description, "Description", 20, 1000);
      text(e, `programs.${i}.people_served`, p.people_served, "People served", 2, 200);
    });
  }
  return e;
}

export const stepOfField = (field: string): StepId => {
  const head = field.split(".")[0];
  if (head === "basics" || head === "mission" || head === "budget" || head === "programs") return head;
  return head === "ntee_codes" ? "cause" : "review";
};

export const fieldErrorsToMap = (errors: FieldError[]): Errors => Object.fromEntries(errors.map((x) => [x.field, x.message]));

/** First step (in order) that still has errors; "review" when all are valid. */
export function firstIncomplete(form: ProfileForm): StepId {
  return STEPS.find((s) => s.id !== "review" && Object.keys(validateStep(s.id, form)).length > 0)?.id ?? "review";
}

export const stepIndex = (id: StepId) => STEPS.findIndex((s) => s.id === id);
export const isStepId = (v: string | null): v is StepId => STEPS.some((s) => s.id === v);
