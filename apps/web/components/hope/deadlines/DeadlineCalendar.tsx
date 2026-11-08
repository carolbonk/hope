"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { btnSecondary, focusRing } from "@/components/hope/ui";
import { useHopeT } from "@/lib/hope/i18n";
import { DeadlineBadge, DOT } from "./DeadlineBadge";
import { appHref, intlLocale, parseDay, urgency, type DeadlineItem } from "./items";

const dayKey = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** Month grid of deadlines. Each deadline is a glass chip linking to its application. */
export function DeadlineCalendar({ items, today }: { items: DeadlineItem[]; today: Date }) {
  const { h, locale } = useHopeT();
  const first = items.find((i) => i.days >= 0) ?? items[0];
  const start = first ? parseDay(first.deadline) : today;
  const [month, setMonth] = useState(() => new Date(start.getFullYear(), start.getMonth(), 1));
  const weekStart = locale === "es" ? 1 : 0;
  const loc = intlLocale(locale);

  const byDay = useMemo(() => {
    const map = new Map<string, DeadlineItem[]>();
    for (const item of items) map.set(item.deadline, [...(map.get(item.deadline) ?? []), item]);
    return map;
  }, [items]);

  const cells = useMemo(() => {
    const lead = (month.getDay() - weekStart + 7) % 7;
    const days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
    const out: (Date | null)[] = Array.from({ length: lead }, () => null);
    for (let d = 1; d <= days; d++) out.push(new Date(month.getFullYear(), month.getMonth(), d));
    while (out.length % 7) out.push(null);
    return out;
  }, [month, weekStart]);

  const weekdays = useMemo(() => {
    const f = new Intl.DateTimeFormat(loc, { weekday: "short" });
    return Array.from({ length: 7 }, (_, i) => f.format(new Date(2024, 0, 7 + ((i + weekStart) % 7))));
  }, [loc, weekStart]);

  const monthKey = dayKey(month).slice(0, 7);
  const inMonth = items.filter((i) => i.deadline.startsWith(monthKey));
  const todayKey = dayKey(today);
  const shift = (n: number) => setMonth((m) => new Date(m.getFullYear(), m.getMonth() + n, 1));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <button type="button" onClick={() => shift(-1)} aria-label={h.deadlines.prevMonth} className={`${btnSecondary} !min-h-10 !px-3`}>
          <span aria-hidden>‹</span>
        </button>
        <h2 aria-live="polite" className="font-display text-2xl capitalize text-navy">
          {new Intl.DateTimeFormat(loc, { month: "long", year: "numeric" }).format(month)}
        </h2>
        <button type="button" onClick={() => shift(1)} aria-label={h.deadlines.nextMonth} className={`${btnSecondary} !min-h-10 !px-3`}>
          <span aria-hidden>›</span>
        </button>
      </div>

      <div key={monthKey} className="animate-view-in rounded-2xl glass-panel p-2 sm:p-3">
        <div className="grid grid-cols-7 gap-1 pb-1 text-center text-[11px] font-semibold uppercase tracking-wide text-muted">
          {weekdays.map((w) => (
            <span key={w}>{w}</span>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {cells.map((d, i) => {
            if (!d) return <div key={`e${i}`} aria-hidden className="min-h-14 rounded-xl sm:min-h-24" />;
            const key = dayKey(d);
            const due = byDay.get(key) ?? [];
            const isToday = key === todayKey;
            return (
              <div key={key} className={`min-h-14 rounded-xl glass-inset p-1 sm:min-h-24 sm:p-1.5 ${isToday ? "ring-2 ring-teal-ink/60" : ""}`}>
                <span className={`block text-xs tabular-nums ${isToday ? "font-bold text-teal-ink" : "text-navy/60"}`}>{d.getDate()}</span>
                {due.length > 0 && (
                  <ul className="mt-1 space-y-1">
                    {due.map((item) => (
                      <li key={item.id}>
                        <Link
                          href={appHref(item)}
                          title={item.name}
                          className={`flex items-center gap-1 rounded-lg glass-control px-1 py-0.5 text-[11px] font-medium leading-tight text-navy transition duration-200 hover:-translate-y-0.5 hover:shadow-md sm:px-1.5 ${focusRing}`}
                        >
                          <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${DOT[urgency(item.days)]}`} />
                          <span className="sr-only sm:not-sr-only sm:truncate">{item.name}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <ul key={`list-${monthKey}`} className="space-y-2 sm:hidden">
        {inMonth.length === 0 ? (
          <li className="rounded-2xl glass-panel p-4 text-sm text-muted">{h.deadlines.noneThisMonth}</li>
        ) : (
          inMonth.map((item, i) => (
            <li key={item.id} className="animate-view-in" style={{ animationDelay: `${i * 40}ms` }}>
              <Link href={appHref(item)} tabIndex={-1} aria-hidden className={`flex items-center justify-between gap-3 rounded-2xl glass-panel p-4 ${focusRing}`}>
                <span className="min-w-0">
                  <span className="block truncate font-semibold">{item.name}</span>
                  <span className="block text-sm text-navy/70">{h.stage[item.stage]}</span>
                </span>
                <DeadlineBadge days={item.days} />
              </Link>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}
