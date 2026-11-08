// Hope shared data contract. See docs/hope/data-contract.md.
export type TriState = "yes" | "no" | "unknown";
export type Currency = "USD" | "EUR" | "MXN" | "COP";

export type FactStatus = "pending" | "declared" | "reviewed";
export type Country = "" | "US" | "MX" | "CO" | "other";
export type Program = { id: string; name: string; description: string; outcomes: string; served: number | null };
/** A team review of one declared fact or requirement. Always simulated in this prototype: no sign-in, no authorized reviewer, no official lookup. */
export type Review = { by: string; at: string; note: string; value: string; simulated: true };

export type ReqId =
  | "incorporation" | "irs_501c3" | "ein_letter" | "bylaws" | "good_standing" | "board_list"
  | "w9" | "uei" | "sam"
  | "annual_report" | "form_990" | "financials" | "annual_budget"
  | "coi_policy" | "child_protection";
export type ReqStatus = "pending" | "declared" | "not_applicable";
export type ReviewComment = { id: string; by: string; at: string; text: string };
/** One dossier requirement. `evidenceRef` is a reference or example file NAME only — nothing is uploaded. */
export type RequirementRecord = {
  status: ReqStatus;
  naReason: string;
  evidenceRef: string;
  period: string;
  expires: string;
  comments: ReviewComment[];
};
/** "Request review": recorded in this browser only; no server receives it. */
export type ReviewRequest = { at: string; delivery: "local_only" };

export type OrgProfile = {
  id: string;
  // 1 identity
  legalName: string;
  publicName: string;
  country: Country;
  jurisdiction: string;
  website: string;
  contactName: string;
  contactEmail: string;
  responsibleName: string;
  responsibleRole: string;
  legalStatus: "501c3" | "other_nonprofit" | "fiscal_sponsor" | "unknown";
  has501c3: TriState;
  usTaxStatus: TriState;
  // 2 mission & programs
  mission: string;
  vision: string;
  targetPopulation: string;
  servesMinors: TriState;
  serviceArea: string;
  focusAreas: string[];
  programs: Program[];
  // 3 capacity
  annualBudget: number | null;
  currency: Currency;
  fiscalYear: string;
  staffCount: number | null;
  volunteerCount: number | null;
  foundedYear: number | null;
  experience: string;
  fundingNeed: string;
  intendedUse: string[];
  // 4 dossier
  dossier: Partial<Record<ReqId, RequirementRecord>>;
  // 5 review
  reviews: Record<string, Review>;
  reviewRequest: ReviewRequest | null;
  completedSteps: number;
  updatedAt: string;
};

export type FundingType = "grant" | "contract" | "sponsorship" | "in_kind";
export type Purpose = "general_operating" | "program" | "capacity" | "capital";

export type Opportunity = {
  id: string;
  funder: string;
  name: string;
  /** Major units; `null` when the funder's page gave no amount Hope can show. */
  amountMin: number | null;
  amountMax: number | null;
  currency: Currency;
  geography: string[];
  fundingType: FundingType;
  focusAreas: string[];
  purpose: Purpose;
  /** `null` when the page gave no date (or a rolling one). */
  deadline: string | null;
  /** Live finds only: the page's own words for the amount/deadline, and a currency the UI doesn't show. */
  amountText?: string | null;
  deadlineText?: string | null;
  otherCurrency?: string | null;
  summary?: string | null;
  requirements: { id: string; label: string; field?: keyof OrgProfile; expect?: unknown }[];
  /** Dossier items this call asks for (W-9, UEI, SAM.gov…). */
  docs?: ReqId[];
  /** Uses federal funds (directly or pass-through): UEI + SAM.gov apply. */
  federal?: boolean;
  source: { kind: "demo" | "verified"; url?: string; verifiedAt?: string };
  funderContext: { previousGrantees: string[]; awardHistory: string[]; sourceUrl?: string } | null;
};

export type Eligibility = "meets" | "needs_review" | "not_qualified";
export type Stage = "saved" | "eligibility" | "approval" | "drafting" | "ready";
export type SectionId = "program" | "alignment" | "logicModel" | "objectives" | "budget" | "budgetNarrative";

export type Section = { text: string; origin: "empty" | "ai" | "template" | "human"; updatedAt: string | null };

export type Application = {
  id: string;
  orgId: string;
  opportunityId: string;
  stage: Stage;
  approvals: { program: "pending" | "approved" | "sent_back"; director: "pending" | "approved" | "sent_back" };
  evidence: Record<string, { status: TriState; note: string }>;
  sections: Record<SectionId, Section>;
  comments: { id: string; author: string; text: string; at: string }[];
  activity: { at: string; event: string }[];
  createdAt: string;
  updatedAt: string;
};

export type HopeState = {
  version: 1;
  profile: OrgProfile;
  decisions: Record<string, { decision: "saved" | "passed"; at: string }>;
  history: string[];
  applications: Record<string, Application>;
};
