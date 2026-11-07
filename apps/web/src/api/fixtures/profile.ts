import type { AgencyProfile } from "@hope/schemas";

export const FIXTURE_TENANT_ID = "6f1c2b9e-4d3a-4f7e-9a51-2c8d0e7b4a10";
export const FIXTURE_AGENCY_ID = "b2e7d4c1-8a5f-4b3e-9d2c-7f6a1e0c5b38";

export const FIXTURE_PROFILE: AgencyProfile = {
  agency_id: FIXTURE_AGENCY_ID,
  tenant_id: FIXTURE_TENANT_ID,
  version: 14,
  valid_from: "2026-09-30T14:00:00Z",
  legal: {
    legal_name: "Riverbend Community Health Alliance",
    dba: ["Riverbend Health"],
    ein: "84-3917265",
    uei: "R7KX4M2N9P1Q",
    tax_status: "501c3_public_charity",
    state_of_incorporation: "WA",
    sam_registration: { status: "active", expires_on: "2027-05-18", exclusions_flag: false },
    provenance: { source: "sam_gov", captured_at: "2026-09-12T10:04:00Z", confidence: 1, verified_by: "u-dana" },
  },
  mission: {
    mission_statement:
      "Riverbend Community Health Alliance brings preventive care, dental services and mental health support to rural families in the Columbia River valley, regardless of ability to pay.",
    vision_statement: "Every rural family can reach the care they need within thirty minutes of home.",
    theory_of_change:
      "Mobile services and trusted community health workers remove distance and cost barriers, which raises preventive visit rates and lowers emergency use.",
    focus_areas: ["Rural health access", "Oral health", "Youth mental health", "Community health workers"],
    ntee_codes: ["E32", "F30"],
  },
  programs: [
    {
      program_id: "prg-mobile-dental",
      name: "Mobile Dental Clinic",
      description: "Two mobile units provide cleanings, sealants and restorative care at schools and farmworker housing.",
      status: "active",
      geography: ["53077", "53039"],
      annual_cost: { amount_minor: 68_500_000, currency: "USD" },
      target_demographics: [{ population: "Children and adults on Medicaid", annual_served: 3200 }],
    },
    {
      program_id: "prg-chw",
      name: "Community Health Worker Network",
      description: "Bilingual community health workers coordinate chronic disease care and benefits enrollment.",
      status: "active",
      geography: ["53077"],
      annual_cost: { amount_minor: 41_200_000, currency: "USD" },
      target_demographics: [{ population: "Adults with diabetes or hypertension", annual_served: 950 }],
    },
    {
      program_id: "prg-ymhfa",
      name: "Youth Mental Health First Aid",
      description: "Trains school staff and parents to recognise and respond to youth mental health crises.",
      status: "pilot",
      geography: ["53077"],
      annual_cost: { amount_minor: 12_000_000, currency: "USD" },
      target_demographics: [{ population: "Middle and high school students", age_range: "11-18", annual_served: 4100 }],
    },
  ],
  financials: {
    annual_operating_budget: { amount_minor: 312_000_000, currency: "USD" },
    budget_band: "1m-5m",
    fiscal_year_end: "06-30",
    fringe_rate_bps: 2450,
    indirect_rate: { type: "negotiated_nicra", rate_bps: 1820, base: "MTDC", agreement_expires_on: "2027-06-30" },
    last_audit: { type: "single_audit", fiscal_year: 2026, findings: false },
    provenance: { source: "erp_sync", captured_at: "2026-10-01T08:00:00Z", confidence: 0.98 },
  },
  capacity: {
    grant_writer_fte: 1.5,
    monthly_hours_available: 220,
    max_concurrent_applications: 3,
    cost_share_capacity: { amount_minor: 4_500_000, currency: "USD" },
  },
  approval_hierarchy: [
    { gate: "HITL-0", approver_roles: ["org_admin", "finance_director"], sla_hours: 72, escalate_to_role: "org_admin" },
    { gate: "HITL-1", approver_roles: ["development_director", "program_lead"], sla_hours: 120, min_approvals: 1 },
    { gate: "HITL-2", approver_roles: ["finance_director"], sla_hours: 72, escalate_to_role: "cfo" },
    { gate: "HITL-3", approver_roles: ["compliance_officer"], sla_hours: 48, escalate_to_role: "executive_director" },
    { gate: "HITL-4", approver_roles: ["executive_director"], sla_hours: 48, escalate_to_role: "board_chair" },
    { gate: "HITL-5", approver_roles: ["aor"], sla_hours: 24 },
  ],
  data_governance: { data_residency: "us", allow_cross_tenant_learning: false, allow_style_finetune: false },
};
