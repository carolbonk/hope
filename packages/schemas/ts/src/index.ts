/* Generated from packages/schemas/json/bundle.schema.json. Do not edit; run `pnpm --filter @hope/schemas gen`. */

/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Gate".
 */
export type Gate =
  "HITL-0" | "HITL-1" | "HITL-2" | "HITL-3" | "HITL-4" | "HITL-5" | "REVIEW-ELIGIBILITY" | "REVIEW-PARSE";
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "EventType".
 */
export type EventType =
  | "opportunity.raw_ingested"
  | "opportunity.normalized"
  | "opportunity.parse_incomplete"
  | "opportunity.amended"
  | "opportunity.eligibility_evaluated"
  | "opportunity.alignment_scored"
  | "opportunity.state_changed"
  | "recommendation.updated"
  | "profile.updated"
  | "profile.change_proposed"
  | "profile.stale_field"
  | "framework.drafted"
  | "framework.locked"
  | "verification.reported"
  | "hitl.requested"
  | "hitl.decided"
  | "submission.authorized"
  | "application.submitted"
  | "notification.requested";

export interface HopeContracts {
  [k: string]: unknown | undefined;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Activity".
 */
export interface Activity {
  activity_id: string;
  description: string;
  end_month?: number | null;
  responsible_role?: string | null;
  start_month?: number | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "AgencyProfile".
 */
export interface AgencyProfile {
  agency_id: string;
  /**
   * @minItems 1
   */
  approval_hierarchy: [ApprovalRule, ...ApprovalRule[]];
  capacity?: Capacity | null;
  compliance_calendar?: ComplianceItem[];
  data_governance?: DataGovernance;
  financials: Financials;
  grant_history?: GrantHistoryItem[];
  legal: Legal;
  mission: Mission;
  programs?: Program[];
  tenant_id: string;
  valid_from?: string | null;
  version: number;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "ApprovalRule".
 */
export interface ApprovalRule {
  /**
   * @minItems 1
   */
  approver_roles: [string, ...string[]];
  /**
   * JSON Logic over the gate payload
   */
  condition?: {
    [k: string]: unknown | undefined;
  } | null;
  escalate_to_role?: string | null;
  gate: Gate;
  min_approvals?: number;
  sla_hours?: number | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Capacity".
 */
export interface Capacity {
  cost_share_capacity?: Money | null;
  grant_writer_fte?: number | null;
  max_concurrent_applications?: number | null;
  monthly_hours_available?: number | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Money".
 */
export interface Money {
  amount_minor: number;
  currency?: string;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "ComplianceItem".
 */
export interface ComplianceItem {
  due_on: string;
  item:
    | "sam_renewal"
    | "form_990"
    | "single_audit"
    | "state_charity_registration"
    | "insurance_renewal"
    | "nicra_renewal"
    | "board_meeting"
    | "custom";
  owner_user_id?: string | null;
}
export interface DataGovernance {
  allow_cross_tenant_learning?: boolean;
  allow_style_finetune?: boolean;
  data_residency?: "us" | "eu" | "ca";
  retention_days?: number | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Financials".
 */
export interface Financials {
  annual_operating_budget: Money;
  budget_band?: ("<250k" | "250k-1m" | "1m-5m" | "5m-25m" | ">25m") | null;
  fiscal_year_end: string;
  fringe_rate_bps?: number | null;
  indirect_rate?: IndirectRate | null;
  last_audit?: LastAudit | null;
  provenance?: Provenance | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "IndirectRate".
 */
export interface IndirectRate {
  agreement_expires_on?: string | null;
  base?: ("MTDC" | "TDC" | "salaries_wages") | null;
  rate_bps?: number | null;
  type: "negotiated_nicra" | "de_minimis" | "none";
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "LastAudit".
 */
export interface LastAudit {
  artifact_id?: string | null;
  findings?: boolean | null;
  fiscal_year?: number | null;
  type: "single_audit" | "financial_audit" | "review" | "none";
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Provenance".
 */
export interface Provenance {
  captured_at: string;
  confidence?: number | null;
  source: "user_input" | "document_extraction" | "crm_sync" | "erp_sync" | "sam_gov" | "irs" | "system";
  /**
   * artifact_id, record id or URL
   */
  source_ref?: string | null;
  /**
   * user_id if confirmed by a human
   */
  verified_by?: string | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "GrantHistoryItem".
 */
export interface GrantHistoryItem {
  /**
   * Assistance Listing Number, e.g. 93.243
   */
  aln?: string | null;
  amount?: Money | null;
  funder_id: string;
  outcome: "awarded" | "declined" | "withdrawn" | "pending";
  period_end?: string | null;
  period_start?: string | null;
  program_name?: string | null;
  reviewer_feedback_artifact_id?: string | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Legal".
 */
export interface Legal {
  dba?: string[];
  ein: string;
  fiscal_sponsor_id?: string | null;
  legal_name: string;
  provenance?: Provenance | null;
  sam_registration?: SamRegistration | null;
  state_of_incorporation?: string | null;
  tax_status:
    | "501c3_public_charity"
    | "501c3_private_foundation"
    | "501c4"
    | "501c6"
    | "fiscally_sponsored"
    | "government"
    | "tribal"
    | "other";
  uei?: string | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "SamRegistration".
 */
export interface SamRegistration {
  exclusions_flag?: boolean;
  expires_on?: string | null;
  status: "active" | "expired" | "pending" | "none";
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Mission".
 */
export interface Mission {
  focus_areas?: string[];
  mission_statement: string;
  ntee_codes?: string[];
  theory_of_change?: string | null;
  vision_statement?: string | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Program".
 */
export interface Program {
  annual_cost?: Money | null;
  description: string;
  /**
   * FIPS or ISO-3166-2 codes
   */
  geography?: string[];
  name: string;
  outcomes?: Outcome[];
  program_id: string;
  status?: "active" | "pilot" | "planned" | "sunset";
  target_demographics?: Demographic[];
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Outcome".
 */
export interface Outcome {
  label: string;
  metric_id: string;
  period: string;
  provenance?: Provenance | null;
  unit?: string | null;
  value: number;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Demographic".
 */
export interface Demographic {
  age_range?: string | null;
  annual_served?: number | null;
  population: string;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Approval".
 */
export interface Approval {
  approved_hash: string;
  approver_user_id: string;
  at: string;
  esign_envelope_id?: string | null;
  gate: Gate;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "BudgetLedger".
 */
export interface BudgetLedger {
  cap_checks: CapCheck[];
  /**
   * ledgers from any other producer are rejected
   */
  computed_by?: "budget-engine";
  currency?: string;
  engine_version: string;
  ledger_id: string;
  line_items: LineItem[];
  periods?: number;
  sf424a_mapping?: {
    [k: string]: number | undefined;
  };
  totals: Totals;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "CapCheck".
 */
export interface CapCheck {
  actual_minor?: number | null;
  adjustment_note?: string | null;
  limit_minor?: number | null;
  rule:
    | "award_ceiling"
    | "award_floor"
    | "indirect_cap"
    | "cost_share_ratio"
    | "category_cap"
    | "unallowable_cost"
    | "period_cap";
  status: "pass" | "fail" | "adjusted";
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "LineItem".
 */
export interface LineItem {
  allowability?: "allowable" | "unallowable" | "needs_review";
  amount_minor: number;
  basis: LineItemBasis;
  category:
    | "personnel"
    | "fringe"
    | "travel"
    | "equipment"
    | "supplies"
    | "contractual"
    | "construction"
    | "other"
    | "indirect";
  description?: string | null;
  funding_source?: "request" | "cost_share_cash" | "cost_share_in_kind";
  justification?: string | null;
  line_id: string;
  period?: number;
}
/**
 * What an LLM may propose. Amounts are never part of the basis.
 *
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "LineItemBasis".
 */
export interface LineItemBasis {
  /**
   * e.g. hris:position:PM-02 or erp:vendor-quote:Q-118
   */
  cost_basis_ref: string;
  effort_pct_bps?: number | null;
  /**
   * decimal string
   */
  quantity?: string;
  unit?: string | null;
  /**
   * resolved by the engine from the ref
   */
  unit_rate_minor?: number | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Totals".
 */
export interface Totals {
  cost_share_minor: number;
  direct_minor: number;
  indirect_minor: number;
  mtdc_base_minor: number;
  project_total_minor: number;
  request_minor: number;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "CostShare".
 */
export interface CostShare {
  in_kind_allowed?: boolean | null;
  ratio_bps?: number | null;
  required: boolean;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "DataGovernance".
 */
export interface DataGovernance1 {
  allow_cross_tenant_learning?: boolean;
  allow_style_finetune?: boolean;
  data_residency?: "us" | "eu" | "ca";
  retention_days?: number | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Deadlines".
 */
export interface Deadlines {
  anticipated_award_date?: string | null;
  application_due?: ExtractedDeadline | null;
  loi_due?: ExtractedDeadline | null;
  project_period_months?: number | null;
  questions_due?: ExtractedDeadline | null;
  rolling?: boolean;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "ExtractedDeadline".
 */
export interface ExtractedDeadline {
  confidence: number;
  /**
   * @minItems 1
   */
  evidence: [Evidence, ...Evidence[]];
  /**
   * model or parser id + version
   */
  extractor?: string | null;
  /**
   * IANA tz, e.g. America/New_York
   */
  timezone: string;
  value: string;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Evidence".
 */
export interface Evidence {
  artifact_id: string;
  char_end?: number | null;
  char_start?: number | null;
  page: number;
  quote?: string | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "DimensionScores".
 */
export interface DimensionScores {
  deadline_feasibility: number;
  /**
   * normalized inverse of EFR
   */
  effort_to_funding: number;
  funder_relationship?: number;
  funding_fit: number;
  mission_alignment: number;
  strategic_priority_boost?: number;
  win_probability: number;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Eligibility".
 */
export interface Eligibility {
  applicant_types?: string[];
  budget_band_restrictions?: string[];
  clauses?: EligibilityClause[];
  geographic_restrictions?: string[];
  required_registrations?: ("sam" | "uei" | "grants_gov" | "state_charity" | "other")[];
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "EligibilityClause".
 */
export interface EligibilityClause {
  /**
   * JSON Logic, once approved
   */
  compiled_rule?: {
    [k: string]: unknown | undefined;
  } | null;
  /**
   * @minItems 1
   */
  evidence: [Evidence, ...Evidence[]];
  rule_status?: "draft" | "approved" | "needs_review";
  text: string;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Estimates".
 */
export interface Estimates {
  days_to_internal_deadline?: number | null;
  expected_hours?: number | null;
  expected_value?: Money | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "ExtractedStrings".
 */
export interface ExtractedStrings {
  confidence: number;
  /**
   * @minItems 1
   */
  evidence: [Evidence, ...Evidence[]];
  /**
   * model or parser id + version
   */
  extractor?: string | null;
  value: string[];
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Formatting".
 */
export interface Formatting {
  file_types?: string[];
  font_min_pt?: number | null;
  margins_in?: number | null;
  spacing?: string | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Funder".
 */
export interface Funder {
  aln?: string[];
  contact_email?: string | null;
  funder_id?: string | null;
  name: string;
  type: "federal" | "state" | "local" | "private_foundation" | "community_foundation" | "corporate" | "other";
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Funding".
 */
export interface Funding {
  award_ceiling?: Money | null;
  award_floor?: Money | null;
  cost_share?: CostShare | null;
  evidence?: Evidence[];
  expected_awards?: number | null;
  indirect_cost_policy?: IndirectCostPolicy | null;
  total_program_funding?: Money | null;
  unallowable_costs?: string[];
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "IndirectCostPolicy".
 */
export interface IndirectCostPolicy {
  allowed: boolean;
  base?: "MTDC" | "TDC" | "salaries_wages" | "unspecified";
  cap_bps?: number | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Goal".
 */
export interface Goal {
  goal_id: string;
  /**
   * @minItems 1
   */
  objectives: [Objective, ...Objective[]];
  statement: string;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Objective".
 */
export interface Objective {
  activities?: Activity[];
  /**
   * @minItems 1
   */
  kpis: [Kpi, ...Kpi[]];
  objective_id: string;
  smart_statement: string;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Kpi".
 */
export interface Kpi {
  /**
   * profile metric_id; never a free number
   */
  baseline_ref?: string | null;
  metric: string;
  target?: number | null;
  unit?: string | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "GrantOpportunity".
 */
export interface GrantOpportunity {
  deadlines: Deadlines;
  eligibility: Eligibility;
  funder: Funder;
  funding: Funding;
  funding_priorities?: ExtractedStrings | null;
  opportunity_id: string;
  parse_quality: ParseQuality;
  requirements?: Requirements;
  source: Source;
  summary?: string | null;
  title: string;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "ParseQuality".
 */
export interface ParseQuality {
  injection_suspected?: boolean;
  missing_critical_fields?: string[];
  overall_confidence: number;
  pipeline_path?: ("native_text" | "layout_model" | "ocr" | "vision_llm" | "human")[];
  warnings?: string[];
}
export interface Requirements {
  attachments?: string[];
  formatting?: Formatting | null;
  /**
   * e.g. SF-424, SF-424A, SF-LLL
   */
  forms?: string[];
  sections?: RequirementSection[];
  submission_channel?: ("grants_gov" | "funder_portal" | "email" | "mail" | "other") | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "RequirementSection".
 */
export interface RequirementSection {
  evaluation_criteria?: string[];
  instructions?: string | null;
  page_limit?: number | null;
  scoring_weight_points?: number | null;
  section_id: string;
  title: string;
  word_limit?: number | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Source".
 */
export interface Source {
  amendment_seq?: number;
  artifact_ids?: string[];
  /**
   * e.g. Grants.gov opportunity number
   */
  source_id: string;
  system: "grants_gov" | "sam_gov" | "candid" | "funder_site" | "state_portal" | "email" | "upload";
  url?: string | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "HitlDecision".
 */
export interface HitlDecision {
  artifact_hash: string;
  comment?: string | null;
  decided_at: string;
  decided_by: string;
  decision: "approve" | "reject" | "request_changes" | "go" | "no_go" | "defer";
  details?: {
    [k: string]: unknown | undefined;
  };
  gate: Gate;
  request_id: string;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "HitlRequest".
 */
export interface HitlRequest {
  approver_roles: string[];
  /**
   * approval is void if the artifact changes
   */
  artifact_hash: string;
  due_at?: string | null;
  gate: Gate;
  payload_ref?: string | null;
  request_id: string;
  summary: string;
  tenant_id: string;
  workflow_id: string;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "LogicModel".
 */
export interface LogicModel {
  activities?: string[];
  inputs?: string[];
  outcomes_long?: string[];
  outcomes_short?: string[];
  outputs?: string[];
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "MatrixRow".
 */
export interface MatrixRow {
  capacity_fit?: ("fits" | "tight" | "conflicts") | null;
  composite_score: number;
  eligibility: "eligible" | "needs_review" | "ineligible";
  estimates?: Estimates1;
  /**
   * generated only from the values above
   */
  explanation?: string | null;
  opportunity_id: string;
  rank: number;
  recommendation: "pursue" | "consider" | "watch" | "skip";
  risks?: string[];
  scores: DimensionScores;
  top_matched_programs?: string[];
}
export interface Estimates1 {
  days_to_internal_deadline?: number | null;
  expected_hours?: number | null;
  expected_value?: Money | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "OpportunityMatrix".
 */
export interface OpportunityMatrix {
  agency_id: string;
  generated_at: string;
  model_version: string;
  rows: MatrixRow[];
  weights_profile?: string | null;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "PillarEnvelope".
 */
export interface PillarEnvelope {
  data_classification?: "public" | "internal" | "confidential" | "restricted";
  /**
   * idempotency key
   */
  event_id?: string;
  event_type: EventType;
  occurred_at?: string;
  payload?: {
    [k: string]: unknown | undefined;
  } | null;
  /**
   * S3 URI when payload > 256 KB
   */
  payload_ref?: string | null;
  producer: Producer;
  schema_ref: string;
  /**
   * partition key, usually opportunity_id
   */
  subject_id: string;
  /**
   * None only for public, cross-tenant data
   */
  tenant_id?: string | null;
  trace?: Trace;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Producer".
 */
export interface Producer {
  agent_id?: string | null;
  model_ids?: string[];
  prompt_version?: string | null;
  service: string;
  version?: string;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Trace".
 */
export interface Trace {
  causation_id?: string | null;
  /**
   * workflow id
   */
  correlation_id?: string | null;
  trace_id?: string;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "ProposalFramework".
 */
export interface ProposalFramework {
  agency_id: string;
  approvals?: Approval[];
  budget: BudgetLedger;
  /**
   * sha256 of canonical JSON
   */
  content_hash?: string | null;
  extra?: {
    [k: string]: unknown | undefined;
  };
  framework_id: string;
  opportunity_id: string;
  scope: Scope;
  status: "draft" | "verified" | "approved_locked" | "superseded";
  version: number;
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Scope".
 */
export interface Scope {
  /**
   * @minItems 1
   */
  goals: [Goal, ...Goal[]];
  logic_model?: LogicModel | null;
  problem_statement_ref?: string | null;
  program_ids?: string[];
  project_title: string;
  requirement_coverage?: RequirementCoverage[];
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "RequirementCoverage".
 */
export interface RequirementCoverage {
  covered_by?: string[];
  section_id: string;
  status: "covered" | "partial" | "missing";
}
/**
 * This interface was referenced by `HopeContracts`'s JSON-Schema
 * via the `definition` "Requirements".
 */
export interface Requirements1 {
  attachments?: string[];
  formatting?: Formatting | null;
  /**
   * e.g. SF-424, SF-424A, SF-LLL
   */
  forms?: string[];
  sections?: RequirementSection[];
  submission_channel?: ("grants_gov" | "funder_portal" | "email" | "mail" | "other") | null;
}
