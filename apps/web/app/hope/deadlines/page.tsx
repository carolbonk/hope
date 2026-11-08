"use client";

import Link from "next/link";
import { useState } from "react";
import { DeadlineCalendar } from "@/components/hope/deadlines/DeadlineCalendar";
import { DeadlineTable } from "@/components/hope/deadlines/DeadlineTable";
import { DeadlineViewTabs, panelId, tabId, type DeadlineView } from "@/components/hope/deadlines/DeadlineViewTabs";
import type { DeadlineItem } from "@/components/hope/deadlines/items";
import { btnPrimary, ClientOnly, daysUntil, PageIntro, Panel } from "@/components/hope/ui";
import { useToday } from "@/components/useToday";
import { useHopeT } from "@/lib/hope/i18n";
import { useOpportunities } from "@/lib/hope/opportunities";
import { useHope } from "@/lib/hope/store";

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
  const items: DeadlineItem[] = Object.values(state.applications)
    .map((a) => ({ a, o: opps.find((o) => o.id === a.opportunityId)! }))
    .filter((x) => x.o && x.a.stage !== "ready" && state.decisions[x.a.opportunityId]?.decision !== "passed")
    .map(({ a, o }) => ({ id: a.id, oppId: o.id, name: o.name, funder: o.funder, stage: a.stage, deadline: o.deadline, days: daysUntil(o.deadline, today) }))
    .sort((x, y) => x.days - y.days);

  return (
    <div className="space-y-4">
      <PageIntro
        kicker={h.look.deadlinesEyebrow}
        title={h.deadlines.title}
        aside={items.length > 0 && <DeadlineViewTabs value={view} onChange={setView} label={h.deadlines.view} labels={{ table: h.deadlines.table, calendar: h.deadlines.calendar }} />}
      />
      {items.length === 0 ? (
        <Panel>
          <p className="mb-3">{h.deadlines.empty}</p>
          <Link href="/hope/discover" className={btnPrimary}>
            {h.nav.discover}
          </Link>
        </Panel>
      ) : (
        <div key={view} id={panelId(view)} role="tabpanel" aria-labelledby={tabId(view)} className="animate-view-in">
          {view === "table" ? <DeadlineTable items={items} /> : <DeadlineCalendar items={items} today={today} />}
        </div>
      )}
    </div>
  );
}
