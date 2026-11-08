"use client";

import Link from "next/link";
import { useState } from "react";
import { DeadlineCalendar } from "@/components/hope/deadlines/DeadlineCalendar";
import { DeadlineTable } from "@/components/hope/deadlines/DeadlineTable";
import { DeadlineViewTabs, panelId, tabId, type DeadlineView } from "@/components/hope/deadlines/DeadlineViewTabs";
import type { DeadlineItem } from "@/components/hope/deadlines/items";
import { btnPrimary, ClientOnly, daysUntil, focusRing, PageIntro, Panel } from "@/components/hope/ui";
import { useToday } from "@/components/useToday";
import { useHopeT } from "@/lib/hope/i18n";
import { useOpportunities } from "@/lib/hope/opportunities";
import { useHope } from "@/lib/hope/store";
import { isRolling } from "@/lib/hope/sync/opportunities";
import { useNoDateCopy } from "./copy";

export default function DeadlinesPage() {
  return (
    <ClientOnly>
      <Deadlines />
    </ClientOnly>
  );
}

function Deadlines() {
  const { h } = useHopeT();
  const today = useToday()!;
  const opps = useOpportunities();
  const { state } = useHope();
  const [view, setView] = useState<DeadlineView>("table");
  const c = useNoDateCopy();
  const open = Object.values(state.applications)
    .map((a) => ({ a, o: opps.find((o) => o.id === a.opportunityId)! }))
    .filter((x) => x.o && x.a.stage !== "ready" && state.decisions[x.a.opportunityId]?.decision !== "passed");
  const items: DeadlineItem[] = open
    .flatMap(({ a, o }) => (o.deadline ? [{ id: a.id, oppId: o.id, name: o.name, funder: o.funder, stage: a.stage, deadline: o.deadline, days: daysUntil(o.deadline, today) }] : []))
    .sort((x, y) => x.days - y.days);
  // No date found (or rolling): listed after the dated ones, never on the calendar or in the urgency counts.
  const undated = open.filter(({ o }) => !o.deadline);

  return (
    <div className="space-y-4">
      <PageIntro
        kicker={h.look.deadlinesEyebrow}
        title={h.deadlines.title}
        aside={items.length > 0 && <DeadlineViewTabs value={view} onChange={setView} label={h.deadlines.view} labels={{ table: h.deadlines.table, calendar: h.deadlines.calendar }} />}
      />
      {items.length === 0 && undated.length === 0 ? (
        <Panel>
          <p className="mb-3">{h.deadlines.empty}</p>
          <Link href="/hope/discover" className={btnPrimary}>
            {h.nav.discover}
          </Link>
        </Panel>
      ) : items.length === 0 ? null : (
        <div key={view} id={panelId(view)} role="tabpanel" aria-labelledby={tabId(view)} className="animate-view-in">
          {view === "table" ? <DeadlineTable items={items} /> : <DeadlineCalendar items={items} today={today} />}
        </div>
      )}
      {undated.length > 0 && (
        <Panel>
          <h2 className="mb-1 text-lg font-semibold">{c.title}</h2>
          <p className="mb-3 text-sm text-muted">{c.hint}</p>
          <ul className="divide-y divide-line" data-testid="no-date">
            {undated.map(({ a, o }) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <Link href={`/hope/applications/${o.id}`} className={`font-semibold text-teal-ink underline ${focusRing}`}>
                  {o.name}
                </Link>
                <span className="text-sm text-muted">
                  {o.funder} · {isRolling(o) ? c.rolling : c.unknown}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}
