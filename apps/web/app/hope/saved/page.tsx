"use client";

import Link from "next/link";
import { useBidsCopy } from "@/components/hope/bids/copy";
import { useBidIds } from "@/components/hope/bids/useBidIds";
import { byDeadline, useGrantFacts } from "@/components/hope/discovery/facts";
import { btnPrimary, btnSecondary, ClientOnly, focusRing, PageIntro, Panel, StageBar } from "@/components/hope/ui";
import { useHopeT } from "@/lib/hope/i18n";
import { useOpportunities } from "@/lib/hope/opportunities";
import { useHope } from "@/lib/hope/store";

export default function SavedPage() {
  return (
    <ClientOnly>
      <SavedList />
    </ClientOnly>
  );
}

function SavedList() {
  const { h } = useHopeT();
  const opps = useOpportunities();
  const facts = useGrantFacts();
  const { state } = useHope();
  const bidIds = useBidIds();
  const openBid = useBidsCopy().matrix.open;
  const apps = Object.values(state.applications)
    .map((a) => ({ a, o: opps.find((o) => o.id === a.opportunityId) }))
    .filter((x) => x.o && state.decisions[x.a.opportunityId]?.decision !== "passed")
    .sort((x, y) => byDeadline(x.o!, y.o!));

  return (
    <div className="space-y-4">
      <PageIntro kicker={h.look.savedEyebrow} title={h.look.savedHeading} sub={h.look.savedSub} />
      <h2 className="sr-only">{h.saved.title}</h2>
      {apps.length === 0 ? (
        <Panel>
          <p className="mb-3">{h.saved.empty}</p>
          <Link href="/hope/discover" className={btnPrimary}>
            {h.nav.discover}
          </Link>
        </Panel>
      ) : (
        <ul className="grid gap-5 sm:grid-cols-2">
          {apps.map(({ a, o }) => (
            <li key={a.id} className="space-y-2">
              <Link href={`/hope/applications/${o!.id}`} className={`block h-full rounded-[0.9rem] glass-panel p-6 hover:border-teal-ink ${focusRing}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.16em] text-muted">{o!.funder}</p>
                    <p className="mt-2 font-display text-[1.75rem] leading-tight">{o!.name}</p>
                  </div>
                  {o!.source.kind === "demo" && <span className="rounded-full bg-[#f1ead8] px-2.5 py-1 text-xs font-semibold text-[#6b5520]">{h.demo}</span>}
                </div>
                <p className="mt-1 text-sm">
                  {facts.amount(o!, false)} · {facts.due(o!)}
                </p>
                <StageBar stage={a.stage} />
                <span className="mt-5 inline-flex min-h-11 items-center justify-center gap-2 rounded-lg glass-nav px-5 py-2.5 font-semibold text-teal-ink">{h.look.openWorkspace} ↗</span>
              </Link>
              {bidIds.has(o!.id) && (
                <Link href={`/hope/bids/${o!.id}`} className={btnSecondary}>
                  {openBid} ↗
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
