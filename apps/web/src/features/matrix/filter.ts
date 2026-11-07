import type { DimensionScores, GrantOpportunity } from "@hope/schemas";
import type { EligibilityStatus, MatrixRow, Recommendation } from "@/api/types";
import { daysUntil } from "@/lib/time";

export type DeadlineWindow = "any" | "14" | "30" | "60";

export interface MatrixFilters {
  recommendation: Recommendation | "all";
  eligibility: EligibilityStatus | "all";
  deadline: DeadlineWindow;
}

export const DEFAULT_FILTERS: MatrixFilters = { recommendation: "all", eligibility: "all", deadline: "any" };

export const DIMENSIONS: readonly { key: keyof DimensionScores; label: string; short: string; max: number }[] = [
  { key: "mission_alignment", label: "Mission alignment", short: "Alignment", max: 100 },
  { key: "funding_fit", label: "Funding fit", short: "Funding", max: 100 },
  { key: "effort_to_funding", label: "Effort to funding", short: "Effort", max: 100 },
  { key: "win_probability", label: "Win probability", short: "Win prob.", max: 1 },
  { key: "deadline_feasibility", label: "Deadline feasibility", short: "Deadline", max: 100 },
  { key: "funder_relationship", label: "Funder relationship", short: "Relation", max: 100 },
  { key: "strategic_priority_boost", label: "Strategic priority", short: "Strategy", max: 100 },
];

export const dueDate = (opp: GrantOpportunity | undefined): string | undefined => opp?.deadlines.application_due?.value;

export function filterRows(
  rows: readonly MatrixRow[],
  opportunities: ReadonlyMap<string, GrantOpportunity>,
  filters: MatrixFilters,
  now: Date,
): MatrixRow[] {
  return rows
    .filter((r) => filters.recommendation === "all" || r.recommendation === filters.recommendation)
    .filter((r) => filters.eligibility === "all" || r.eligibility === filters.eligibility)
    .filter((r) => {
      if (filters.deadline === "any") return true;
      const due = dueDate(opportunities.get(r.opportunity_id));
      if (!due) return false;
      const days = daysUntil(due, now);
      return days >= 0 && days <= Number(filters.deadline);
    })
    .toSorted((a, b) => a.rank - b.rank);
}
