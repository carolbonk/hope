"use client";

import { useHopeT } from "@/lib/hope/i18n";
import { urgency } from "./items";

const TONE = {
  overdue: "border-red-200/80 bg-red-100/70 text-red-800",
  soon: "border-gold/60 bg-gold/70 text-navy",
  later: "border-white/70 bg-white/45 text-navy",
} as const;

export const DOT = { overdue: "bg-red-500", soon: "bg-gold", later: "bg-teal-ink" } as const;

export function DeadlineBadge({ days }: { days: number }) {
  const { h } = useHopeT();
  const u = urgency(days);
  const label = u === "overdue" ? h.deadlines.overdue : u === "soon" ? `${h.deadlines.soon} · ${days}d` : `${days}d`;
  return <span className={`inline-flex shrink-0 items-center rounded-full border px-3 py-1 text-sm font-semibold tabular-nums backdrop-blur-md ${TONE[u]}`}>{label}</span>;
}
