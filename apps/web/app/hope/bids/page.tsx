"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { btnPrimary, btnSecondary, ClientOnly, daysUntil, focusRing, PageIntro, Panel } from "@/components/hope/ui";
import { listBids, type BidSummary } from "@/components/hope/bids/api";
import { useBidsCopy } from "@/components/hope/bids/copy";
import { useToday } from "@/components/useToday";
import { ErrorNotice, Loading } from "@/components/ui/States";
import { online } from "@/lib/api/http";

export default function BidsPage() {
  return (
    <ClientOnly>
      <Bids />
    </ClientOnly>
  );
}

function Bids() {
  const t = useBidsCopy().bids;
  const today = useToday()!;
  const [bids, setBids] = useState<BidSummary[] | null>(null);
  const [failed, setFailed] = useState(false);
  const load = useCallback(() => {
    listBids().then(
      (b) => (setBids(b), setFailed(false)),
      () => setFailed(true),
    );
  }, []);
  useEffect(() => {
    if (online) load();
  }, [load]);

  const intro = <PageIntro kicker={t.eyebrow} title={t.title} sub={t.sub} />;
  if (!online)
    return (
      <>
        {intro}
        <Panel>
          <p data-testid="bids-offline">{t.offline}</p>
        </Panel>
      </>
    );
  if (failed)
    return (
      <>
        {intro}
        <ErrorNotice title={t.loadFailed} onRetry={load}>
          {t.retry}
        </ErrorNotice>
      </>
    );
  if (!bids)
    return (
      <>
        {intro}
        <Loading label={t.loading} />
      </>
    );

  const counts: [string, number][] = [
    [t.active, bids.filter((b) => b.phase === "preparing").length],
    [t.readyFinal, bids.filter((b) => b.phase === "final_reviewed").length],
    [t.submitted, bids.filter((b) => b.phase === "submitted").length],
  ];
  return (
    <div className="space-y-5">
      {intro}
      <div className="grid grid-cols-3 gap-3">
        {counts.map(([label, n]) => (
          <div key={label} className="rounded-2xl glass-panel p-4">
            <p className="font-display text-3xl tabular-nums text-navy">{n}</p>
            <p className="text-xs text-muted">{label}</p>
          </div>
        ))}
      </div>
      {bids.length === 0 ? (
        <Panel>
          <p className="mb-3">{t.empty}</p>
          <Link href="/hope/matrix" className={btnPrimary}>
            {t.toMatrix}
          </Link>
        </Panel>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {bids.map((b) => (
            <li key={b.application_id}>
              <Link href={`/hope/bids/${b.grant_id}`} className={`block h-full rounded-2xl glass-panel p-5 hover:border-teal-ink ${focusRing}`} data-testid="bid-card">
                <p className="text-[11px] uppercase tracking-[0.16em] text-muted">{b.funder}</p>
                <p className="mt-1 font-display text-2xl leading-tight text-navy">{b.title}</p>
                <p className="mt-1 text-sm">{b.deadline ? t.due(b.deadline, daysUntil(b.deadline, today)) : t.noDeadline}</p>
                <p className="mt-2 text-sm text-muted">{t.progress(b.ready, b.total)}</p>
                <div className="mt-2 h-1.5 rounded-full bg-line">
                  <div className="h-1.5 rounded-full bg-teal-ink" style={{ width: `${b.total ? (100 * b.ready) / b.total : 0}%` }} />
                </div>
                <p className="mt-2 text-xs text-muted">
                  {t.phase[b.phase]}
                  {b.phase !== "submitted" && b.blockers > 0 && ` · ${t.blockers(b.blockers)}`}
                </p>
                <span className={`${btnSecondary} mt-4`}>{t.continue} ↗</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
