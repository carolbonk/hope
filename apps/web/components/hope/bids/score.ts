// The matrix's sample score: a fixed, documented formula in the browser. Not a model and not a chance of winning.
import { daysUntil } from "@/components/hope/ui";
import { ALL_REQS, applicability, record } from "@/lib/hope/dossier";
import { geographyFits } from "@/lib/hope/store";
import type { Eligibility, Opportunity, OrgProfile } from "@/lib/hope/types";

export type Rec = "pursue" | "consider" | "watch" | "skip";
export type Dims = Record<"focus" | "geo" | "size" | "effort" | "time", number>;
export type Row = { o: Opportunity; dims: Dims; score: number; elig: Eligibility; days: number | null; rec: Rec };

export const WEIGHTS = { focus: 0.35, geo: 0.2, size: 0.2, effort: 0.15, time: 0.1 } as const;
/** Unknown inputs (no amount, no budget, no date) score in the middle rather than guessing. */
const UNKNOWN = 50;

export function scoreRow(o: Opportunity, p: OrgProfile, today: Date, elig: Eligibility): Row {
  const focus = o.focusAreas.length ? Math.round((100 * o.focusAreas.filter((f) => p.focusAreas.includes(f)).length) / o.focusAreas.length) : 0;
  const g = geographyFits(o, p);
  const geo = g === "yes" ? 100 : g === "unknown" ? UNKNOWN : 0;
  const size = !p.annualBudget || o.amountMax === null ? UNKNOWN : o.amountMax <= p.annualBudget * 0.4 ? 100 : o.amountMax <= p.annualBudget ? 60 : 20;
  const pending = ALL_REQS.filter((id) => {
    const a = applicability(id, p, o);
    return a.level !== "auto_na" && (a.level !== "when_asked" || o.docs?.includes(id)) && record(p, id).status === "pending";
  }).length;
  const effort = Math.min(100, pending * 10);
  const days = o.deadline ? daysUntil(o.deadline, today) : null;
  const time = days === null ? UNKNOWN : days < 0 ? 0 : Math.min(100, Math.round((days / 60) * 100));
  const dims = { focus, geo, size, effort, time };
  const raw = WEIGHTS.focus * focus + WEIGHTS.geo * geo + WEIGHTS.size * size + WEIGHTS.effort * (100 - effort) + WEIGHTS.time * time;
  const score = Math.round(raw * 10) / 10;
  const rec: Rec = elig === "not_qualified" || (days !== null && days < 0) ? "skip" : score >= 70 ? "pursue" : score >= 55 ? "consider" : "watch";
  return { o, dims, score, elig, days, rec };
}
