"use client";

import Link from "next/link";
import { focusRing } from "@/components/hope/ui";
import { useHopeT } from "@/lib/hope/i18n";
import { DeadlineBadge } from "./DeadlineBadge";
import { appHref, intlLocale, parseDay, urgency, type DeadlineItem } from "./items";

const EDGE = { overdue: "border-l-red-400", soon: "border-l-gold", later: "border-l-transparent" } as const;
const COLS = "sm:grid sm:grid-cols-[minmax(0,2.2fr)_minmax(0,1.4fr)_minmax(0,1fr)_11rem] sm:items-center sm:gap-4";

export function DeadlineTable({ items }: { items: DeadlineItem[] }) {
  const { h, locale } = useHopeT();
  const fmt = new Intl.DateTimeFormat(intlLocale(locale), { month: "short", day: "numeric", year: "numeric" });
  return (
    <div className="space-y-2">
      <div aria-hidden className={`hidden px-5 text-xs font-semibold uppercase tracking-wide text-muted ${COLS}`}>
        <span>{h.deadlines.colGrant}</span>
        <span>{h.deadlines.colStage}</span>
        <span>{h.deadlines.colDue}</span>
        <span className="text-right">{h.deadlines.colStatus}</span>
      </div>
      <ul className="space-y-2">
        {items.map((item, i) => (
          <li key={item.id}>
            <Link
              href={appHref(item)}
              style={{ animationDelay: `${i * 40}ms` }}
              className={`animate-view-in flex flex-col gap-2 rounded-2xl border-l-4 glass-panel p-4 transition duration-200 hover:-translate-y-0.5 hover:shadow-lg sm:px-5 ${EDGE[urgency(item.days)]} ${COLS} ${focusRing}`}
            >
              <span className="min-w-0">
                <span className="block truncate font-semibold">{item.name}</span>
                <span className="block truncate text-sm text-navy/60">{item.funder}</span>
              </span>
              <span className="text-sm text-navy/70">
                <span className="font-medium text-navy">{h.stage[item.stage]}</span> · {h.app.next[item.stage]}
              </span>
              <span className="text-sm tabular-nums text-navy/80">
                <time dateTime={item.deadline}>{fmt.format(parseDay(item.deadline))}</time>
              </span>
              <span className="sm:justify-self-end">
                <DeadlineBadge days={item.days} />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
