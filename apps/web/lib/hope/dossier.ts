// The nonprofit's single dossier: profile facts + document requirements, shared by profile, discovery and applications.
// Completing it is not legal certification and does not guarantee eligibility for any opportunity.
import type { FactStatus, Opportunity, OrgProfile, ReqId, RequirementRecord } from "./types";

export const PROFILE_STEPS = 5;

export type GroupId = "identity_governance" | "registrations" | "finance" | "policies";
export const GROUPS: { id: GroupId; reqs: ReqId[] }[] = [
  { id: "identity_governance", reqs: ["incorporation", "irs_501c3", "ein_letter", "bylaws", "good_standing", "board_list"] },
  { id: "registrations", reqs: ["w9", "uei", "sam"] },
  { id: "finance", reqs: ["annual_report", "form_990", "financials", "annual_budget"] },
  { id: "policies", reqs: ["coi_policy", "child_protection"] },
];
export const ALL_REQS: ReqId[] = GROUPS.flatMap((g) => g.reqs);

/**
 * usual: commonly requested for this profile · when_asked: only if a call asks for it ·
 * auto_na: does not apply to this profile · needs_info: depends on a profile answer still missing.
 */
export type Level = "usual" | "when_asked" | "auto_na" | "needs_info";
export type Reason =
  | "general" | "us_only" | "us_501c3" | "not_501c3" | "need_501c3" | "need_country" | "if_jurisdiction"
  | "if_requested" | "need_us_tax" | "no_us_tax" | "need_tax_status" | "w9_fiscal_sponsor" | "federal_only" | "federal_call" | "requested_by_call" | "local_equivalent" | "serves_minors" | "no_minors" | "need_minors";
export type Applicability = { level: Level; reason: Reason; step: 0 | 1 };

export function applicability(id: ReqId, p: OrgProfile, opp?: Opportunity): Applicability {
  const us = p.country === "US";
  const noCountry = p.country === "";
  const usOnly = (yes: Applicability): Applicability => (noCountry ? { level: "needs_info", reason: "need_country", step: 0 } : us ? yes : { level: "auto_na", reason: "us_only", step: 0 });
  switch (id) {
    case "irs_501c3":
      if (!us) return usOnly({ level: "usual", reason: "us_501c3", step: 0 });
      if (p.has501c3 === "yes" || p.legalStatus === "501c3") return { level: "usual", reason: "us_501c3", step: 0 };
      if (p.has501c3 === "no") return { level: "auto_na", reason: "not_501c3", step: 0 };
      return { level: "needs_info", reason: "need_501c3", step: 0 };
    case "ein_letter":
      return usOnly({ level: "usual", reason: "general", step: 0 });
    case "good_standing":
      return noCountry ? { level: "needs_info", reason: "need_country", step: 0 } : us ? { level: "usual", reason: "general", step: 0 } : { level: "when_asked", reason: "if_jurisdiction", step: 0 };
    case "w9":
      return w9(p, !!opp?.docs?.includes("w9"));
    case "uei":
    case "sam":
      if (opp?.federal || opp?.docs?.includes(id)) return { level: "usual", reason: "federal_call", step: 0 };
      return { level: "when_asked", reason: "federal_only", step: 0 };
    case "form_990":
      return noCountry ? { level: "needs_info", reason: "need_country", step: 0 } : { level: "usual", reason: us ? "general" : "local_equivalent", step: 0 };
    case "child_protection":
      if (p.servesMinors === "yes") return { level: "usual", reason: "serves_minors", step: 1 };
      if (p.servesMinors === "no") return { level: "auto_na", reason: "no_minors", step: 1 };
      return { level: "needs_info", reason: "need_minors", step: 1 };
    default:
      return { level: "usual", reason: "general", step: 0 };
  }
}

/** W-9 is a US taxpayer form: decided by US tax status + whether the call asks; missing info → requires review. */
function w9(p: OrgProfile, requested: boolean): Applicability {
  const ask: Applicability = requested ? { level: "usual", reason: "requested_by_call", step: 0 } : { level: "when_asked", reason: "if_requested", step: 0 };
  if (p.country === "") return requested ? { level: "needs_info", reason: "need_country", step: 0 } : ask;
  if (p.country !== "US" && p.usTaxStatus === "no") return { level: "auto_na", reason: "no_us_tax", step: 0 };
  if (!requested) return ask;
  if (p.country !== "US") return p.usTaxStatus === "yes" ? ask : { level: "needs_info", reason: "need_us_tax", step: 0 };
  if (p.legalStatus === "unknown") return { level: "needs_info", reason: "need_tax_status", step: 0 };
  if (p.legalStatus === "fiscal_sponsor") return { level: "needs_info", reason: "w9_fiscal_sponsor", step: 0 };
  return ask;
}

export const emptyRecord = (): RequirementRecord => ({ status: "pending", naReason: "", evidenceRef: "", period: "", expires: "", comments: [] });
export const record = (p: OrgProfile, id: ReqId): RequirementRecord => ({ ...emptyRecord(), ...p.dossier[id] });

const today = () => new Date().toISOString().slice(0, 10);
export const isExpired = (r: RequirementRecord) => !!r.expires && r.expires < today();

/** Snapshot a (simulated) review is tied to; any later edit drops the review. */
export function reqValue(r: RequirementRecord): string {
  if (r.status === "pending") return "";
  return JSON.stringify([r.status, r.naReason, r.evidenceRef, r.period, r.expires]);
}

export function reqStatus(p: OrgProfile, id: ReqId): FactStatus {
  const v = reqValue(record(p, id));
  if (!v) return "pending";
  const rv = p.reviews[`req:${id}`];
  return rv && rv.value === v ? "reviewed" : "declared";
}

// ---- profile facts ----
export type FieldKey = keyof OrgProfile;
export const FIELDS: { key: FieldKey; step: 0 | 1 | 2; required: boolean; usOnly?: boolean }[] = [
  { key: "legalName", step: 0, required: true }, { key: "publicName", step: 0, required: false }, { key: "country", step: 0, required: true },
  { key: "jurisdiction", step: 0, required: true }, { key: "website", step: 0, required: false }, { key: "contactName", step: 0, required: true },
  { key: "contactEmail", step: 0, required: true }, { key: "responsibleName", step: 0, required: true }, { key: "responsibleRole", step: 0, required: false },
  { key: "legalStatus", step: 0, required: true }, { key: "has501c3", step: 0, required: true, usOnly: true },
  { key: "mission", step: 1, required: true }, { key: "vision", step: 1, required: false }, { key: "targetPopulation", step: 1, required: true },
  { key: "servesMinors", step: 1, required: true }, { key: "serviceArea", step: 1, required: true }, { key: "focusAreas", step: 1, required: true },
  { key: "programs", step: 1, required: true },
  { key: "annualBudget", step: 2, required: true }, { key: "fiscalYear", step: 2, required: true }, { key: "staffCount", step: 2, required: true },
  { key: "volunteerCount", step: 2, required: false }, { key: "foundedYear", step: 2, required: false }, { key: "experience", step: 2, required: true },
  { key: "fundingNeed", step: 2, required: true }, { key: "intendedUse", step: 2, required: true },
];
export const fieldsFor = (p: OrgProfile) => FIELDS.filter((f) => !f.usOnly || p.country === "US");

export function factValue(p: OrgProfile, key: FieldKey): string {
  const v = p[key] as unknown;
  if (v == null || v === "" || v === "unknown") return "";
  if (Array.isArray(v)) return v.length ? JSON.stringify(v) : "";
  if (key === "annualBudget") return `${v} ${p.currency}`;
  return String(v);
}

export function factStatus(p: OrgProfile, key: FieldKey): FactStatus {
  const v = factValue(p, key);
  if (!v) return "pending";
  const rv = p.reviews[String(key)];
  return rv && rv.value === v ? "reviewed" : "declared";
}

// ---- pending items & the three separate states ----
export type Pending =
  | { kind: "field"; key: FieldKey; step: 0 | 1 | 2 }
  | { kind: "req"; id: ReqId; problem: "missing" | "na_reason" | "expired" | "needs_info"; step: 3; infoStep?: 0 | 1 };

export function pendingItems(p: OrgProfile): Pending[] {
  const out: Pending[] = fieldsFor(p).filter((f) => f.required && !factValue(p, f.key)).map((f) => ({ kind: "field" as const, key: f.key, step: f.step }));
  for (const id of ALL_REQS) {
    const a = applicability(id, p);
    const r = record(p, id);
    if (r.status === "not_applicable" && !r.naReason.trim()) out.push({ kind: "req", id, problem: "na_reason", step: 3 });
    else if (r.status === "declared" && isExpired(r)) out.push({ kind: "req", id, problem: "expired", step: 3 });
    else if (r.status === "pending" && a.level === "needs_info") out.push({ kind: "req", id, problem: "needs_info", step: 3, infoStep: a.step });
    else if (r.status === "pending" && a.level === "usual") out.push({ kind: "req", id, problem: "missing", step: 3 });
  }
  return out;
}

export function summary(p: OrgProfile) {
  const req = fieldsFor(p).filter((f) => f.required);
  const filled = req.filter((f) => factValue(p, f.key)).length;
  const applicable = ALL_REQS.filter((id) => ["usual", "needs_info"].includes(applicability(id, p).level) || record(p, id).status !== "pending");
  const answered = applicable.filter((id) => {
    const r = record(p, id);
    return r.status === "declared" ? !isExpired(r) : r.status === "not_applicable" ? !!r.naReason.trim() : false;
  });
  const reviewed = answered.filter((id) => reqStatus(p, id) === "reviewed").length;
  return {
    profile: { filled, total: req.length, complete: filled === req.length },
    dossier: { answered: answered.length, total: applicable.length, complete: answered.length === applicable.length },
    review: { reviewed, total: answered.length, requested: p.reviewRequest },
  };
}

/** Dossier items a specific call lists, with their status in the shared dossier. */
export function oppDocs(opp: Opportunity, p: OrgProfile): { id: ReqId; status: FactStatus | "not_applicable"; expired: boolean; level: Level }[] {
  const ids = new Set<ReqId>(opp.docs ?? []);
  if (opp.federal) ["uei", "sam"].forEach((x) => ids.add(x as ReqId));
  return [...ids].map((id) => {
    const r = record(p, id);
    return { id, status: r.status === "not_applicable" ? "not_applicable" : reqStatus(p, id), expired: r.status === "declared" && isExpired(r), level: applicability(id, p, opp).level };
  });
}
