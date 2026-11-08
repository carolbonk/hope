"use client";

import { useCallback, useMemo } from "react";
import { useStoredJson } from "./storage";
import { PROFILE_STEPS, record } from "./dossier";
import { isGrantId, mirrorDecision, type RemoteDecisions } from "./sync/decisions";
import { saveRemoteProfile } from "./sync/profile";
import type { Application, Eligibility, HopeState, Opportunity, OrgProfile, ReqId, RequirementRecord, SectionId, Stage, TriState } from "./types";

export { PROFILE_STEPS };

export const HOPE_KEY = "hope:state:v1";
export const ORG_ID = "org-local-1";
export const SECTION_IDS: SectionId[] = ["program", "alignment", "logicModel", "objectives", "budget", "budgetNarrative"];
export const STAGES: Stage[] = ["saved", "eligibility", "approval", "drafting", "ready"];

export const emptyProfile = (): OrgProfile => ({
  id: ORG_ID, legalName: "", publicName: "", country: "", jurisdiction: "", website: "", contactName: "", contactEmail: "",
  responsibleName: "", responsibleRole: "", legalStatus: "unknown", has501c3: "unknown", usTaxStatus: "unknown",
  mission: "", vision: "", targetPopulation: "", servesMinors: "unknown", serviceArea: "", focusAreas: [], programs: [],
  annualBudget: null, currency: "USD", fiscalYear: "", staffCount: null, volunteerCount: null, foundedYear: null, experience: "",
  fundingNeed: "", intendedUse: [], dossier: {}, reviews: {}, reviewRequest: null, completedSteps: 0, updatedAt: "",
});

const rec = (r: Partial<RequirementRecord>): RequirementRecord => ({ status: "declared", naReason: "", evidenceRef: "", period: "", expires: "", comments: [], ...r });

export const DEMO_PROFILE: OrgProfile = {
  ...emptyProfile(),
  legalName: "Tidepath Family Alliance, Inc. (demo)",
  publicName: "Tidepath (demo)",
  country: "US",
  jurisdiction: "Florida",
  website: "https://example.org/tidepath-demo",
  contactName: "Marisol Vega (demo)",
  contactEmail: "marisol@example.org",
  responsibleName: "Marisol Vega (demo)",
  responsibleRole: "Executive Director",
  legalStatus: "501c3",
  has501c3: "yes",
  mission: "Tidepath Family Alliance (demo) helps Miami-Dade children and families thrive through mentoring, family counseling, and school safety and mental-health workshops.",
  vision: "Every child in Miami-Dade has a trusted adult and a family that feels supported.",
  targetPopulation: "Children 8–17 and their families",
  servesMinors: "yes",
  serviceArea: "Miami-Dade",
  focusAreas: ["mentoring", "youth", "family", "mental_health", "safety", "school_based"],
  programs: [
    { id: "p-mentoring", name: "Youth mentoring", description: "Weekly 1:1 mentoring for children 8–17.", outcomes: "80% of mentees attend 10+ sessions per semester", served: 22 },
    { id: "p-counseling", name: "Family counseling", description: "Bilingual counseling sessions for families.", outcomes: "70% of families report reduced stress after 8 sessions", served: 19 },
    { id: "p-workshops", name: "School safety & mental-health workshops", description: "Workshops in Miami-Dade public schools.", outcomes: "300 students reached per school year", served: 297 },
  ],
  annualBudget: 420000, currency: "USD", fiscalYear: "FY2026 (Jul 2025 – Jun 2026)",
  staffCount: 6, volunteerCount: 35, foundedYear: 2012,
  experience: "13 years running school-based mentoring in Miami-Dade; managed 4 foundation grants (demo).",
  fundingNeed: "Expand mentoring to 40 more children and add a bilingual family counselor.",
  intendedUse: ["program", "capacity"],
  dossier: {
    incorporation: rec({ evidenceRef: "example-articles-of-incorporation.pdf", period: "2012" }),
    irs_501c3: rec({ evidenceRef: "example-irs-determination-letter.pdf" }),
    ein_letter: rec({ evidenceRef: "example-ein-cp575.pdf" }),
    bylaws: rec({ evidenceRef: "example-bylaws-2023.pdf", period: "Amended 2023" }),
    board_list: rec({ evidenceRef: "example-board-list.xlsx", period: "FY2026" }),
    annual_budget: rec({ evidenceRef: "example-budget-fy2026.xlsx", period: "FY2026" }),
    financials: rec({ evidenceRef: "example-financials-fy2025.pdf", period: "FY2025" }),
    coi_policy: rec({ evidenceRef: "example-coi-policy.pdf", expires: "2027-06-30" }),
  },
  completedSteps: PROFILE_STEPS,
};

type Legacy = Partial<OrgProfile> & { documents?: Record<string, { status?: string; note?: string }>; samRegistered?: TriState; taxId?: string };
const LEGACY_DOCS: Record<string, ReqId> = { irs_letter: "irs_501c3", w9: "w9", board_list: "board_list", budget_doc: "annual_budget", financials: "financials", policies: "coi_policy" };

/** Reads any earlier hope:state:v1 profile: new fields start empty/pending; old document checkmarks become declarations. */
export function normalizeProfile(raw: Legacy | undefined): OrgProfile {
  const { documents, samRegistered, ...rest } = raw ?? {};
  const p: OrgProfile = { ...emptyProfile(), ...rest, reviews: rest.reviews ?? {}, dossier: { ...rest.dossier } };
  p.programs = (p.programs ?? []).map((x) => ({ ...x, outcomes: x.outcomes ?? "" }));
  for (const [k, v] of Object.entries(documents ?? {})) {
    const id = LEGACY_DOCS[k];
    if (id && v?.status === "declared" && !p.dossier[id]) p.dossier[id] = rec({ evidenceRef: v.note ?? "" });
  }
  if (samRegistered === "yes" && !p.dossier.sam) p.dossier.sam = rec({});
  p.completedSteps = Math.min(p.completedSteps ?? 0, PROFILE_STEPS);
  return p;
}

const initial = (): HopeState => ({ version: 1, profile: emptyProfile(), decisions: {}, history: [], applications: {} });

export const applicationId = (orgId: string, oppId: string) => `app:${orgId}:${oppId}`;

const now = () => new Date().toISOString();

/** The stored state as of now (a hook's render-time copy can be one write behind). */
function latestState(): HopeState {
  try {
    const raw = window.localStorage.getItem(HOPE_KEY);
    if (raw) return JSON.parse(raw) as HopeState;
  } catch {
    // unreadable storage: start from empty
  }
  return initial();
}

/** Sync adapters run after the local write and can never break a page. */
function safely(call: () => void) {
  try {
    call();
  } catch (err) {
    console.warn("hope sync:", err);
  }
}

function newApplication(orgId: string, opp: Pick<Opportunity, "id">): Application {
  const at = now();
  const sections = Object.fromEntries(SECTION_IDS.map((id) => [id, { text: "", origin: "empty", updatedAt: null }])) as Application["sections"];
  return {
    id: applicationId(orgId, opp.id), orgId, opportunityId: opp.id, stage: "saved",
    approvals: { program: "pending", director: "pending" },
    evidence: {}, sections, comments: [], activity: [{ at, event: "saved" }],
    createdAt: at, updatedAt: at,
  };
}

/** An application nobody has worked on yet (undo and a server reset may remove it). */
const untouched = (a: Application | undefined) => !!a && a.activity.length <= 1 && a.stage === "saved";

/**
 * Applies the server's saved/passed grants to the browser state. Backend grants (UUID ids) follow the server,
 * except ones this browser decided during the load or still has in the outbox. Demo ids are left alone, and an
 * application with work in it is kept.
 */
export function mergeRemoteDecisions(s: HopeState, remote: RemoteDecisions): HopeState {
  const local = remote.localIds();
  const decisions = { ...s.decisions };
  const applications = { ...s.applications };
  for (const id of Object.keys(decisions)) {
    if (!isGrantId(id) || local.has(id) || remote.decisions[id]) continue;
    delete decisions[id];
    const appId = applicationId(s.profile.id, id);
    if (untouched(applications[appId])) delete applications[appId];
  }
  for (const [id, decision] of Object.entries(remote.decisions)) {
    if (local.has(id)) continue;
    if (decisions[id]?.decision !== decision) decisions[id] = { decision, at: now() };
    const appId = applicationId(s.profile.id, id);
    if (decision === "saved" && !applications[appId]) applications[appId] = newApplication(s.profile.id, { id });
  }
  return { ...s, decisions, applications, history: s.history.filter((id) => decisions[id]) };
}

/** Recorded evidence wins; otherwise known profile facts are checked; anything unanswered stays Unknown ("Needs review"). */
export function requirementStatus(req: Opportunity["requirements"][number], p: OrgProfile, app?: Application): TriState {
  const ev = app?.evidence[req.id];
  if (ev) return ev.status;
  if (req.field === "has501c3") return p.has501c3;
  if (req.id === "sam") return record(p, "sam").status === "declared" ? "yes" : "unknown";
  if (req.field === "annualBudget") return p.annualBudget == null ? "unknown" : p.annualBudget >= (req.expect as number) ? "yes" : "no";
  if (req.id === "geo") return p.serviceArea ? (p.serviceArea.toLowerCase().includes("miami") ? "yes" : "unknown") : "unknown";
  return "unknown";
}

export function eligibility(opp: Opportunity, p: OrgProfile, app?: Application): Eligibility {
  const st = opp.requirements.map((r) => requirementStatus(r, p, app));
  if (st.includes("no")) return "not_qualified";
  if (st.includes("unknown")) return "needs_review";
  return "meets";
}

const REGION: Record<string, string[]> = {
  "Miami-Dade": ["Miami-Dade", "South Florida", "Florida", "United States"],
  Broward: ["Broward", "South Florida", "Florida", "United States"],
};

export function geographyFits(opp: Opportunity, p: OrgProfile): TriState {
  if (!p.serviceArea) return "unknown";
  const areas = REGION[p.serviceArea] ?? [p.serviceArea, "United States"];
  return opp.geography.some((g) => areas.includes(g)) ? "yes" : "no";
}

export type MatchReason = { key: "focus" | "geo" | "purpose" | "size"; detail: string };

export function matchReasons(opp: Opportunity, p: OrgProfile): { score: number; reasons: MatchReason[] } {
  const reasons: MatchReason[] = [];
  const shared = opp.focusAreas.filter((f) => p.focusAreas.includes(f));
  if (shared.length) reasons.push({ key: "focus", detail: shared.join(", ") });
  if (geographyFits(opp, p) === "yes") reasons.push({ key: "geo", detail: opp.geography.join(", ") });
  if (p.intendedUse.includes(opp.purpose)) reasons.push({ key: "purpose", detail: opp.purpose });
  if (p.annualBudget && opp.amountMax <= p.annualBudget * 0.4) reasons.push({ key: "size", detail: String(opp.amountMax) });
  return { score: reasons.length, reasons };
}

export function useHope() {
  const [stored, setState] = useStoredJson<HopeState>(HOPE_KEY, initial());
  const state = useMemo(() => ({ ...stored, profile: normalizeProfile(stored.profile) }), [stored]);

  const update = useCallback((fn: (s: HopeState) => HopeState) => setState(fn(state)), [state, setState]);

  const saveProfile = useCallback(
    (profile: OrgProfile) => {
      const saved = { ...profile, updatedAt: now() };
      update((s) => ({ ...s, profile: saved }));
      safely(() => saveRemoteProfile(saved));
    },
    [update],
  );

  /** Writes a profile that came from the server; never echoes it back. */
  const hydrateProfile = useCallback(
    (profile: OrgProfile) => update((s) => ({ ...s, profile: normalizeProfile(profile) })),
    [update],
  );

  /** Writes decisions that came from the server onto the latest stored state; never echoes them back. */
  const hydrateDecisions = useCallback(
    (remote: RemoteDecisions) => setState(mergeRemoteDecisions(latestState(), remote)),
    [setState],
  );

  const decide = useCallback(
    (opp: Opportunity, decision: "saved" | "passed") => {
      update((s) => {
        const id = applicationId(s.profile.id, opp.id);
        const applications = { ...s.applications };
        if (decision === "saved" && !applications[id]) applications[id] = newApplication(s.profile.id, opp);
        else if (decision === "saved") applications[id] = touch(applications[id]!, "saved_again");
        return { ...s, decisions: { ...s.decisions, [opp.id]: { decision, at: now() } }, history: [...s.history, opp.id], applications };
      });
      safely(() => mirrorDecision(opp.id, decision));
    },
    [update],
  );

  /** Undo removes the last swipe decision; a saved application with no work is removed too. */
  const undo = useCallback(() => {
    const lastId = state.history.at(-1);
    update((s) => {
        const last = s.history.at(-1);
        if (!last) return s;
        const decisions = { ...s.decisions };
        delete decisions[last];
        const applications = { ...s.applications };
        const id = applicationId(s.profile.id, last);
        const a = applications[id];
        if (untouched(a)) delete applications[id];
        return { ...s, decisions, history: s.history.slice(0, -1), applications };
    });
    if (lastId) safely(() => mirrorDecision(lastId, "new"));
  }, [state, update]);

  const updateApplication = useCallback(
    (id: string, fn: (a: Application) => Application, event: string) =>
      update((s) => (s.applications[id] ? { ...s, applications: { ...s.applications, [id]: touch(fn(s.applications[id]), event) } } : s)),
    [update],
  );

  const reset = useCallback(() => setState(initial()), [setState]);

  return useMemo(
    () => ({ state, saveProfile, hydrateProfile, hydrateDecisions, decide, undo, updateApplication, reset }),
    [state, saveProfile, hydrateProfile, hydrateDecisions, decide, undo, updateApplication, reset],
  );
}

function touch(a: Application, event: string): Application {
  const at = now();
  const prev = a.activity.at(-1);
  const activity = prev?.event === event ? [...a.activity.slice(0, -1), { at, event }] : [...a.activity, { at, event }];
  return { ...a, updatedAt: at, activity: activity.slice(-50) };
}
