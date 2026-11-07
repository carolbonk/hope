import type { DimensionScores, EligibilityClause, Funder, GrantOpportunity, Source } from "@hope/schemas";
import { addDays } from "@/lib/time";
import type { CapacityFit, EligibilityStatus, MatrixRow, Recommendation } from "../types";

interface ClauseSpec {
  text: string;
  page: number;
  quote: string;
  status?: EligibilityClause["rule_status"];
}

interface OpportunitySpec {
  id: string;
  title: string;
  summary: string;
  funder: Funder;
  source: Source;
  dueInDays: number;
  ceilingUsd: number;
  floorUsd?: number;
  totalProgramUsd?: number;
  expectedAwards?: number;
  costShareBps?: number;
  indirectCapBps?: number;
  applicantTypes: string[];
  geography: string[];
  registrations: NonNullable<GrantOpportunity["eligibility"]["required_registrations"]>;
  clauses: ClauseSpec[];
  priorities: string[];
  parseConfidence: number;
  eligibility: EligibilityStatus;
  scores: Required<DimensionScores>;
  capacity: CapacityFit;
  recommendation: Recommendation;
  hours: number;
  expectedValueUsd: number;
  programs: string[];
  risks: string[];
  explanation: string;
}

const usd = (major: number) => ({ amount_minor: major * 100, currency: "USD" });
const INTERNAL_BUFFER_DAYS = 7;

/** Cold-start heuristic from blueprint 5.3; used here only so fixture scores are self-consistent. */
export function heuristicComposite(s: Required<DimensionScores>, eligibility: EligibilityStatus): number {
  if (eligibility === "ineligible") return 0;
  const raw =
    0.35 * s.mission_alignment +
    0.15 * s.funding_fit +
    0.15 * s.effort_to_funding +
    0.15 * 100 * s.win_probability +
    0.1 * s.deadline_feasibility +
    0.05 * s.funder_relationship +
    0.05 * s.strategic_priority_boost;
  return Math.round(raw * 10) / 10;
}

const SPECS: OpportunitySpec[] = [
  {
    id: "opp-hrsa-rhcso-2027",
    title: "Rural Health Care Services Outreach Program",
    summary:
      "Supports rural community partnerships that expand access to preventive and primary care, including mobile and school-based services.",
    funder: { name: "Health Resources and Services Administration", type: "federal", aln: ["93.912"], funder_id: "hrsa" },
    source: { system: "grants_gov", source_id: "HRSA-27-021", url: "https://www.grants.gov/search-results-detail/HRSA-27-021" },
    dueInDays: 34,
    ceilingUsd: 300_000,
    floorUsd: 150_000,
    totalProgramUsd: 18_000_000,
    expectedAwards: 60,
    indirectCapBps: 1500,
    applicantTypes: ["501c3_public_charity", "government", "tribal"],
    geography: ["Non-metropolitan counties (FORHP rural eligibility)"],
    registrations: ["sam", "uei", "grants_gov"],
    clauses: [
      {
        text: "Applicant must be located in a HRSA-designated rural area or be a rural-serving organization with a rural service site.",
        page: 6,
        quote: "The applicant organization must be located in a rural area or in a rural census tract of an urban county…",
        status: "approved",
      },
      {
        text: "Consortium of at least three separately owned health care entities is required.",
        page: 7,
        quote: "Applicants must be part of a consortium composed of at least three (3) separately owned entities…",
        status: "approved",
      },
    ],
    priorities: ["Preventive dental care", "Behavioral health integration", "Care coordination"],
    parseConfidence: 0.96,
    eligibility: "eligible",
    scores: {
      mission_alignment: 92,
      funding_fit: 84,
      effort_to_funding: 71,
      win_probability: 0.42,
      deadline_feasibility: 78,
      funder_relationship: 65,
      strategic_priority_boost: 90,
    },
    capacity: "fits",
    recommendation: "pursue",
    hours: 120,
    expectedValueUsd: 126_000,
    programs: ["Mobile Dental Clinic", "Community Health Worker Network"],
    risks: ["Consortium letters of commitment needed from 3 partners", "Indirect costs capped at 15%"],
    explanation:
      "Strong mission alignment (92) with the Mobile Dental Clinic and CHW Network; ask size sits inside the agency's budget band and the 34-day runway leaves room for consortium letters.",
  },
  {
    id: "opp-samhsa-aware-2027",
    title: "Project AWARE: Advancing Wellness and Resiliency in Education",
    summary:
      "Builds school-community partnerships that identify youth mental health needs early and connect students to services.",
    funder: {
      name: "Substance Abuse and Mental Health Services Administration",
      type: "federal",
      aln: ["93.243"],
      funder_id: "samhsa",
    },
    source: { system: "grants_gov", source_id: "SM-27-006", url: "https://www.grants.gov/search-results-detail/SM-27-006" },
    dueInDays: 21,
    ceilingUsd: 1_800_000,
    floorUsd: 900_000,
    expectedAwards: 20,
    applicantTypes: ["501c3_public_charity", "government"],
    geography: ["United States"],
    registrations: ["sam", "uei", "grants_gov"],
    clauses: [
      {
        text: "Applicants must partner with at least three local education agencies.",
        page: 11,
        quote: "Recipients must partner with a minimum of three (3) local education agencies (LEAs)…",
        status: "approved",
      },
    ],
    priorities: ["Youth Mental Health First Aid", "School-based referral pathways"],
    parseConfidence: 0.93,
    eligibility: "eligible",
    scores: {
      mission_alignment: 88,
      funding_fit: 72,
      effort_to_funding: 66,
      win_probability: 0.31,
      deadline_feasibility: 64,
      funder_relationship: 80,
      strategic_priority_boost: 85,
    },
    capacity: "tight",
    recommendation: "pursue",
    hours: 180,
    expectedValueUsd: 279_000,
    programs: ["Youth Mental Health First Aid"],
    risks: ["Requires three LEA partnership MOUs", "Overlaps with HRSA outreach drafting window"],
    explanation:
      "High alignment with Youth Mental Health First Aid and a prior SAMHSA award (relationship 80). Capacity is tight because drafting overlaps the HRSA outreach application.",
  },
  {
    id: "opp-cascade-resilience-2027",
    title: "Community Resilience Grants",
    summary: "Two-year general and project support for community health organizations serving rural and tribal communities.",
    funder: { name: "Cascade Health Foundation", type: "private_foundation", funder_id: "cascade-health" },
    source: { system: "funder_site", source_id: "CHF-CRG-2027", url: "https://example.org/cascade-health/resilience" },
    dueInDays: 48,
    ceilingUsd: 150_000,
    applicantTypes: ["501c3_public_charity"],
    geography: ["WA", "OR", "ID"],
    registrations: [],
    clauses: [
      {
        text: "Organizations must have an annual operating budget below $5 million.",
        page: 2,
        quote: "Eligible organizations have annual operating budgets under $5 million.",
        status: "approved",
      },
    ],
    priorities: ["Rural health access", "Workforce development"],
    parseConfidence: 0.89,
    eligibility: "eligible",
    scores: {
      mission_alignment: 81,
      funding_fit: 76,
      effort_to_funding: 82,
      win_probability: 0.36,
      deadline_feasibility: 88,
      funder_relationship: 40,
      strategic_priority_boost: 50,
    },
    capacity: "fits",
    recommendation: "consider",
    hours: 45,
    expectedValueUsd: 54_000,
    programs: ["Community Health Worker Network"],
    risks: ["No prior relationship with this funder"],
    explanation:
      "Low effort for the award size and a comfortable deadline; alignment is good but there is no prior relationship with the foundation.",
  },
  {
    id: "opp-state-oral-health-2027",
    title: "Oral Health Access Expansion Grants",
    summary: "State funding for community dental programs that serve Medicaid-enrolled children and adults.",
    funder: { name: "State Department of Health, Office of Oral Health", type: "state", funder_id: "state-doh" },
    source: { system: "state_portal", source_id: "DOH-OH-27-04" },
    dueInDays: 12,
    ceilingUsd: 250_000,
    costShareBps: 1000,
    applicantTypes: ["501c3_public_charity", "government"],
    geography: ["Statewide"],
    registrations: ["state_charity"],
    clauses: [
      {
        text: "Applicant must be enrolled as a Medicaid dental provider or partner with one.",
        page: 4,
        quote: "Applicants must be an enrolled Medicaid dental provider, or demonstrate a formal partnership…",
        status: "needs_review",
      },
      {
        text: "A 10% cash or in-kind match is required.",
        page: 5,
        quote: "A minimum ten percent (10%) match of total project costs is required.",
        status: "approved",
      },
    ],
    priorities: ["Pediatric sealant programs", "Mobile dental services"],
    parseConfidence: 0.81,
    eligibility: "needs_review",
    scores: {
      mission_alignment: 86,
      funding_fit: 70,
      effort_to_funding: 60,
      win_probability: 0.38,
      deadline_feasibility: 45,
      funder_relationship: 55,
      strategic_priority_boost: 70,
    },
    capacity: "tight",
    recommendation: "consider",
    hours: 70,
    expectedValueUsd: 95_000,
    programs: ["Mobile Dental Clinic"],
    risks: ["Medicaid provider enrollment clause needs human review", "10% match required", "12 days to deadline"],
    explanation:
      "Strong program fit for the Mobile Dental Clinic, but eligibility depends on Medicaid provider enrollment and the deadline is close.",
  },
  {
    id: "opp-cdc-chw-2027",
    title: "Community Health Workers for Public Health Response and Resilient Communities",
    summary: "Trains and deploys community health workers to support chronic disease prevention and emergency response.",
    funder: { name: "Centers for Disease Control and Prevention", type: "federal", aln: ["93.495"], funder_id: "cdc" },
    source: { system: "grants_gov", source_id: "CDC-RFA-DP-27-0013" },
    dueInDays: 9,
    ceilingUsd: 1_000_000,
    floorUsd: 250_000,
    expectedAwards: 70,
    indirectCapBps: 1000,
    applicantTypes: ["501c3_public_charity", "government", "tribal"],
    geography: ["United States"],
    registrations: ["sam", "uei", "grants_gov"],
    clauses: [
      {
        text: "Applicants must document a current CHW workforce of at least five FTE.",
        page: 14,
        quote: "Applicants should describe an existing CHW workforce of no fewer than five (5) full-time equivalents.",
        status: "approved",
      },
    ],
    priorities: ["CHW training", "Chronic disease self-management"],
    parseConfidence: 0.91,
    eligibility: "eligible",
    scores: {
      mission_alignment: 79,
      funding_fit: 58,
      effort_to_funding: 52,
      win_probability: 0.22,
      deadline_feasibility: 60,
      funder_relationship: 30,
      strategic_priority_boost: 60,
    },
    capacity: "tight",
    recommendation: "watch",
    hours: 160,
    expectedValueUsd: 88_000,
    programs: ["Community Health Worker Network"],
    risks: ["Ask is above the agency's typical award size", "High writing effort for expected value"],
    explanation:
      "Relevant to the CHW Network, but the effort-to-funding ratio is weak and the agency has no CDC award history.",
  },
  {
    id: "opp-northside-capacity-2027",
    title: "Nonprofit Capacity Building Fund",
    summary: "One-year grants for technology, data systems and staff development at small and mid-sized nonprofits.",
    funder: { name: "Northside Community Foundation", type: "community_foundation", funder_id: "northside-cf" },
    source: { system: "funder_site", source_id: "NCF-CB-27" },
    dueInDays: 63,
    ceilingUsd: 40_000,
    applicantTypes: ["501c3_public_charity"],
    geography: ["Northside County"],
    registrations: [],
    clauses: [
      {
        text: "Applicant must be headquartered in Northside County.",
        page: 1,
        quote: "Organizations must be headquartered and primarily operate in Northside County.",
        status: "approved",
      },
    ],
    priorities: ["Data systems", "Staff training"],
    parseConfidence: 0.95,
    eligibility: "eligible",
    scores: {
      mission_alignment: 44,
      funding_fit: 52,
      effort_to_funding: 74,
      win_probability: 0.48,
      deadline_feasibility: 92,
      funder_relationship: 70,
      strategic_priority_boost: 20,
    },
    capacity: "fits",
    recommendation: "watch",
    hours: 20,
    expectedValueUsd: 19_000,
    programs: [],
    risks: ["Small award; general operating focus rather than programs"],
    explanation: "Good odds and low effort, but the award is small and does not fund a specific program.",
  },
  {
    id: "opp-uw-youth-2027",
    title: "Youth Opportunity Fund",
    summary: "Grants for out-of-school-time programs that improve high-school completion.",
    funder: { name: "Greater Valley United Way", type: "other", funder_id: "gvuw" },
    source: { system: "email", source_id: "GVUW-YOF-2027" },
    dueInDays: 16,
    ceilingUsd: 75_000,
    applicantTypes: ["501c3_public_charity"],
    geography: ["Greater Valley region"],
    registrations: [],
    clauses: [
      {
        text: "Programs must deliver at least 100 hours of out-of-school-time services per participant each year.",
        page: 3,
        quote: "Funded programs provide a minimum of 100 program hours per youth annually.",
        status: "approved",
      },
    ],
    priorities: ["Academic support", "Mentoring"],
    parseConfidence: 0.77,
    eligibility: "eligible",
    scores: {
      mission_alignment: 31,
      funding_fit: 60,
      effort_to_funding: 40,
      win_probability: 0.18,
      deadline_feasibility: 50,
      funder_relationship: 20,
      strategic_priority_boost: 0,
    },
    capacity: "conflicts",
    recommendation: "skip",
    hours: 60,
    expectedValueUsd: 13_500,
    programs: [],
    risks: ["Outside the agency's health focus", "Conflicts with Project AWARE drafting"],
    explanation: "Weak alignment with health programs and the writing window conflicts with higher-value work.",
  },
  {
    id: "opp-usda-cf-2027",
    title: "Community Facilities Direct Loan and Grant Program",
    summary: "Funds essential community facilities in rural areas with populations of 20,000 or fewer.",
    funder: { name: "USDA Rural Development", type: "federal", aln: ["10.766"], funder_id: "usda-rd" },
    source: { system: "grants_gov", source_id: "RD-CF-27-01" },
    dueInDays: 40,
    ceilingUsd: 500_000,
    applicantTypes: ["government", "tribal", "501c3_public_charity"],
    geography: ["Rural areas, population ≤ 20,000"],
    registrations: ["sam", "uei"],
    clauses: [
      {
        text: "Facility must be located in a rural area with a population of 20,000 or less.",
        page: 3,
        quote: "Eligible areas are rural areas including cities, villages, townships… with no more than 20,000 residents.",
        status: "approved",
      },
    ],
    priorities: ["Health care facilities", "Public safety"],
    parseConfidence: 0.94,
    eligibility: "ineligible",
    scores: {
      mission_alignment: 62,
      funding_fit: 40,
      effort_to_funding: 35,
      win_probability: 0.1,
      deadline_feasibility: 70,
      funder_relationship: 0,
      strategic_priority_boost: 10,
    },
    capacity: "fits",
    recommendation: "skip",
    hours: 200,
    expectedValueUsd: 0,
    programs: ["Mobile Dental Clinic"],
    risks: ["Headquarters city exceeds the 20,000 population limit"],
    explanation: "Hard eligibility rule failed: the agency's service facility is in a city above the population limit.",
  },
];

export interface OpportunityFixtures {
  opportunities: GrantOpportunity[];
  rows: MatrixRow[];
}

export function buildOpportunities(now: Date): OpportunityFixtures {
  const opportunities = SPECS.map((s): GrantOpportunity => {
    const artifact = `art-${s.id}`;
    const due = addDays(now, s.dueInDays);
    return {
      opportunity_id: s.id,
      title: s.title,
      summary: s.summary,
      funder: s.funder,
      source: { ...s.source, artifact_ids: [artifact] },
      deadlines: {
        application_due: {
          value: due,
          timezone: "America/New_York",
          confidence: s.parseConfidence,
          evidence: [{ artifact_id: artifact, page: 1, quote: `Applications are due ${due.slice(0, 10)} by 11:59 p.m. Eastern Time.` }],
        },
        project_period_months: 24,
      },
      eligibility: {
        applicant_types: s.applicantTypes,
        geographic_restrictions: s.geography,
        required_registrations: s.registrations,
        clauses: s.clauses.map((c) => ({
          text: c.text,
          rule_status: c.status ?? "approved",
          evidence: [{ artifact_id: artifact, page: c.page, quote: c.quote }],
        })),
      },
      funding: {
        award_ceiling: usd(s.ceilingUsd),
        award_floor: s.floorUsd ? usd(s.floorUsd) : null,
        total_program_funding: s.totalProgramUsd ? usd(s.totalProgramUsd) : null,
        expected_awards: s.expectedAwards ?? null,
        cost_share: s.costShareBps ? { required: true, ratio_bps: s.costShareBps, in_kind_allowed: true } : { required: false },
        indirect_cost_policy: s.indirectCapBps ? { allowed: true, base: "MTDC", cap_bps: s.indirectCapBps } : null,
      },
      funding_priorities: {
        value: s.priorities,
        confidence: s.parseConfidence,
        evidence: [{ artifact_id: artifact, page: 2 }],
      },
      parse_quality: { overall_confidence: s.parseConfidence, pipeline_path: ["native_text"] },
    };
  });

  const rows = SPECS.map(
    (s): MatrixRow => ({
      opportunity_id: s.id,
      rank: 0,
      composite_score: heuristicComposite(s.scores, s.eligibility),
      eligibility: s.eligibility,
      scores: s.scores,
      estimates: {
        expected_hours: s.hours,
        expected_value: usd(s.expectedValueUsd),
        days_to_internal_deadline: s.dueInDays - INTERNAL_BUFFER_DAYS,
      },
      capacity_fit: s.capacity,
      recommendation: s.recommendation,
      explanation: s.explanation,
      top_matched_programs: s.programs,
      risks: s.risks,
    }),
  )
    .sort((a, b) => b.composite_score - a.composite_score)
    .map((row, i) => ({ ...row, rank: i + 1 }));

  return { opportunities, rows };
}
