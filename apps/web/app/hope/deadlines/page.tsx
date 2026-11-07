"use client";

import Link from "next/link";
import { btnPrimary, ClientOnly, daysUntil, focusRing, PageIntro, Panel } from "@/components/hope/ui";
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
  const items = Object.values(state.applications)
    .map((a) => ({ a, o: opps.find((o) => o.id === a.opportunityId)! }))
    .filter((x) => x.o && x.a.stage !== "ready")
    .map((x) => ({ ...x, days: daysUntil(x.o.deadline, today) }))
    .sort((x, y) => x.days - y.days);

  return (
    <div className="space-y-4">
      <PageIntro kicker={h.look.deadlinesEyebrow} title={h.deadlines.title} />
      {items.length === 0 ? (
        <Panel>
          <p className="mb-3">{h.deadlines.empty}</p>
          <Link href="/hope/discover" className={btnPrimary}>
            {h.nav.discover}
          </Link>
        </Panel>
      ) : (
        <ul className="space-y-2">
          {items.map(({ a, o, days }) => (
            <li key={a.id}>
              <Link href={`/hope/applications/${o.id}`} className={`flex items-center justify-between gap-3 rounded-2xl border glass-control p-4 ${days < 0 ? "border-red-300" : days <= 14 ? "border-gold" : "border-line"} ${focusRing}`}>
                <div>
                  <p className="font-semibold">{o.name}</p>
                  <p className="text-sm text-navy/70">
                    {h.stage[a.stage]} · {h.app.next[a.stage]}
                  </p>
                </div>
                <span className={`shrink-0 rounded-full px-3 py-1 text-sm font-semibold ${days < 0 ? "bg-red-100 text-red-800" : days <= 14 ? "bg-gold text-navy" : "bg-cream"}`}>
                  {days < 0 ? h.deadlines.overdue : days <= 14 ? `${h.deadlines.soon} · ${days}d` : `${days}d`}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
