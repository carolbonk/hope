"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { btnPrimary, btnSecondary, ClientOnly, focusRing, input, money, PageIntro, Panel } from "@/components/hope/ui";
import { listBids, startBid } from "@/components/hope/bids/api";
import { useBidsCopy } from "@/components/hope/bids/copy";
import { scoreRow, type Rec, type Row } from "@/components/hope/bids/score";
import { GRANT_ID } from "@/components/hope/bids/shared";
import { useToday } from "@/components/useToday";
import { AutoDismiss } from "@/components/ui/AutoDismiss";
import { online } from "@/lib/api/http";
import { useHopeT } from "@/lib/hope/i18n";
import { useOpportunities } from "@/lib/hope/opportunities";
import { applicationId, eligibility, useHope } from "@/lib/hope/store";
import type { Eligibility } from "@/lib/hope/types";

export default function MatrixPage() {
  return (
    <ClientOnly>
      <Matrix />
    </ClientOnly>
  );
}

const pill = (active: boolean) => `whitespace-nowrap rounded-full px-3 py-2 text-sm ${focusRing} ${active ? "bg-navy text-white" : "glass-control text-navy"}`;
const recTone: Record<Rec, string> = { pursue: "bg-[#dcefe9] text-teal-ink", consider: "bg-[#f1ead8] text-[#6b5520]", watch: "bg-[#e8eaf0] text-navy", skip: "bg-[#f6e3df] text-red-800" };

function Matrix() {
  const { locale } = useHopeT();
  const m = useBidsCopy().matrix;
  const today = useToday()!;
  const opps = useOpportunities();
  const { state } = useHope();
  const router = useRouter();
  const [bidIds, setBidIds] = useState<Set<string>>(new Set());
  const [sort, setSort] = useState<"score" | "deadline">("score");
  const [rec, setRec] = useState<Rec | "all">("all");
  const [elig, setElig] = useState<Eligibility | "all">("all");
  const [win, setWin] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!online) return;
    listBids().then((bids) => setBidIds(new Set(bids.map((b) => b.grant_id))), () => undefined);
  }, []);

  const rows = opps
    .map((o) => scoreRow(o, state.profile, today, eligibility(o, state.profile, state.applications[applicationId(state.profile.id, o.id)])))
    .sort((x, y) => (sort === "score" ? y.score - x.score : (x.days ?? Infinity) - (y.days ?? Infinity)));
  const rank = new Map([...rows].sort((x, y) => y.score - x.score).map((r, i) => [r.o.id, i + 1]));
  const shown = rows.filter((r) => (rec === "all" || r.rec === rec) && (elig === "all" || r.elig === elig) && (!win || (r.days !== null && r.days >= 0 && r.days <= win)));
  const canBid = (r: Row) => online && GRANT_ID.test(r.o.id);

  async function prepare(id: string) {
    setBusy(id);
    setFailed(false);
    try {
      await startBid(id);
      router.push(`/hope/bids/${id}`);
    } catch {
      setFailed(true);
      setBusy(null);
    }
  }

  const action = (r: Row) =>
    bidIds.has(r.o.id) ? (
      <Link href={`/hope/bids/${r.o.id}`} className={btnSecondary}>
        {m.open}
      </Link>
    ) : (
      <button type="button" className={btnPrimary} disabled={!canBid(r) || busy !== null || r.rec === "skip"} onClick={() => void prepare(r.o.id)}>
        {m.prepare}
      </button>
    );
  const amount = (r: Row) => (r.o.amountMax === null ? m.noAmount : money(r.o.amountMax, r.o.currency, locale));
  const dims = (r: Row) => (
    <dl className="grid grid-cols-5 gap-1 text-[10px] text-muted">
      {(Object.keys(r.dims) as (keyof Row["dims"])[]).map((k) => (
        <div key={k}>
          <dt className="truncate">{m.dims[k]}</dt>
          <dd className="font-semibold tabular-nums text-navy">{r.dims[k]}</dd>
        </div>
      ))}
    </dl>
  );
  const recBadge = (r: Row) => <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${recTone[r.rec]}`}>{m.recs[r.rec]}</span>;

  return (
    <div className="space-y-5">
      <PageIntro
        kicker={m.eyebrow}
        title={m.title}
        sub={m.sub}
        aside={
          <Link href="/hope/discover" className={btnSecondary}>
            {m.toCards}
          </Link>
        }
      />
      <details className="rounded-2xl glass-panel p-4 text-sm" data-testid="matrix-how">
        <summary className={`cursor-pointer font-semibold text-navy ${focusRing}`}>{m.howTitle}</summary>
        <p className="mt-2 text-muted">{m.how}</p>
      </details>
      {!online && <p className="rounded-xl bg-gold/15 px-3 py-2 text-sm">{m.offline}</p>}

      <div className="flex flex-wrap items-end gap-3">
        <fieldset className="flex flex-wrap gap-1">
          <legend className="mb-1 text-xs font-semibold text-muted">{m.sort}</legend>
          {(["score", "deadline"] as const).map((s) => (
            <button key={s} type="button" aria-pressed={sort === s} className={pill(sort === s)} onClick={() => setSort(s)}>
              {s === "score" ? m.sortScore : m.sortDeadline}
            </button>
          ))}
        </fieldset>
        <fieldset className="flex flex-wrap gap-1">
          <legend className="mb-1 text-xs font-semibold text-muted">{m.rec}</legend>
          {(["all", "pursue", "consider", "watch", "skip"] as const).map((r) => (
            <button key={r} type="button" aria-pressed={rec === r} className={pill(rec === r)} onClick={() => setRec(r)}>
              {r === "all" ? m.all : m.recs[r]}
            </button>
          ))}
        </fieldset>
        <label className="text-xs font-semibold text-muted">
          {m.elig}
          <select className={`${input} mt-1 min-w-44`} value={elig} onChange={(e) => setElig(e.target.value as Eligibility | "all")}>
            <option value="all">{m.all}</option>
            {(["meets", "needs_review", "not_qualified"] as const).map((x) => (
              <option key={x} value={x}>
                {m.eligs[x]}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-semibold text-muted">
          {m.window}
          <select className={`${input} mt-1 min-w-36`} value={win} onChange={(e) => setWin(Number(e.target.value))}>
            <option value={0}>{m.any}</option>
            {[30, 60, 90].map((d) => (
              <option key={d} value={d}>
                {m.within(d)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p role="status" className="text-sm text-muted">
        {m.showing(shown.length, rows.length)} · {m.sample}
      </p>
      {failed && (
        <AutoDismiss onDismiss={() => setFailed(false)}>
          <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            {m.failed}
          </p>
        </AutoDismiss>
      )}

      {shown.length === 0 ? (
        <Panel>
          <p className="mb-3">{m.none}</p>
          <button type="button" className={btnSecondary} onClick={() => (setRec("all"), setElig("all"), setWin(0))}>
            {m.clear}
          </button>
        </Panel>
      ) : (
        <>
          <div className="hidden overflow-x-auto rounded-2xl glass-panel md:block">
            <table className="w-full min-w-[56rem] text-left text-sm" data-testid="matrix-table">
              <thead className="border-b border-line text-xs uppercase tracking-wider text-muted">
                <tr>
                  {m.cols.map((c, i) => (
                    <th key={i} scope="col" className="px-3 py-3 font-semibold">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.o.id} className="border-b border-line align-top last:border-0" data-testid="matrix-row">
                    <td className="px-3 py-3 tabular-nums text-muted">#{rank.get(r.o.id)}</td>
                    <td className="px-3 py-3">
                      <p className="text-[11px] uppercase tracking-wider text-muted">{r.o.funder}</p>
                      <p className="font-semibold text-navy">{r.o.name}</p>
                      <p className="text-xs text-muted">{amount(r)}</p>
                    </td>
                    <td className="px-3 py-3 font-display text-2xl tabular-nums text-navy">{r.score.toFixed(1)}</td>
                    <td className="w-56 px-3 py-3">{dims(r)}</td>
                    <td className="px-3 py-3">{m.eligs[r.elig]}</td>
                    <td className="px-3 py-3 tabular-nums">{m.days(r.days)}</td>
                    <td className="px-3 py-3">{recBadge(r)}</td>
                    <td className="px-3 py-3">{action(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="grid gap-3 md:hidden">
            {shown.map((r) => (
              <li key={r.o.id} className="rounded-2xl glass-panel p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-wider text-muted">
                      #{rank.get(r.o.id)} · {r.o.funder}
                    </p>
                    <p className="font-semibold text-navy">{r.o.name}</p>
                  </div>
                  <p className="font-display text-3xl tabular-nums text-navy">{r.score.toFixed(1)}</p>
                </div>
                <p className="mt-1 text-xs text-muted">
                  {amount(r)} · {m.days(r.days)} · {m.eligs[r.elig]}
                </p>
                <div className="mt-3">{dims(r)}</div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                  {recBadge(r)}
                  {action(r)}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
