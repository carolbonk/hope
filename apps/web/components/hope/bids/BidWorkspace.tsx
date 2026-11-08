"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { btnPrimary, btnSecondary, daysUntil, focusRing, input, Panel } from "@/components/hope/ui";
import { useToday } from "@/components/useToday";
import { AutoDismiss } from "@/components/ui/AutoDismiss";
import { ErrorNotice, Loading } from "@/components/ui/States";
import { useSession } from "@/lib/api/session";
import { useHopeT } from "@/lib/hope/i18n";
import * as api from "./api";
import type { BidItem, BidView, Blocker, ItemChanges, ItemStatus, Member } from "./api";
import { useBidsCopy, type BidsCopy } from "./copy";
import { matches, namer, statusTone, type ItemFilter } from "./shared";
import { useBid, type RunBid } from "./useBid";

type Tab = "requirements" | "plan" | "review";
type Ctx = { bid: BidView; run: RunBid; busy: boolean; closed: boolean; who: (id: string | null) => string; when: (iso: string) => string; t: BidsCopy["bid"] };

/** One bid: assign and track each requirement, follow the plan, then the final review and the receipt. */
export function BidWorkspace({ grantId }: { grantId: string }) {
  const c = useBidsCopy();
  const t = c.bid;
  const { locale } = useHopeT();
  const { me } = useSession();
  const today = useToday()!;
  const { view, members, loadError, notice, clearNotice, pending, reload, run } = useBid(grantId);
  const [tab, setTab] = useState<Tab>("requirements");
  const [open, setOpen] = useState<string | null>(null);

  const back = (
    <Link href="/hope/bids" className={`text-sm text-teal-ink underline ${focusRing}`}>
      {t.all}
    </Link>
  );
  if (loadError)
    return (
      <div className="space-y-4">
        {back}
        <ErrorNotice title={t.failed} onRetry={() => void reload()}>
          {c.bids.retry}
        </ErrorNotice>
      </div>
    );
  if (view === undefined) return <Loading label={t.loading} />;
  if (view === null)
    return (
      <Panel>
        <p role="alert" className="mb-3">
          {t.notFound}
        </p>
        <Link href="/hope/bids" className={btnPrimary}>
          {t.all}
        </Link>
      </Panel>
    );

  const ctx: Ctx = {
    bid: view,
    run,
    busy: pending,
    closed: view.phase === "submitted",
    who: namer(members, me?.user_id, t),
    when: (iso) => new Date(iso).toLocaleString(locale),
    t,
  };
  const resolve = (key?: string | null) => {
    setTab("requirements");
    setOpen(key ?? null);
    setTimeout(() => document.getElementById(key ? `item-${key}` : "bid-tabs")?.scrollIntoView({ block: "start" }), 0);
  };

  return (
    <div className="space-y-5">
      {back}
      <header className="rounded-2xl glass-panel p-5 sm:p-6">
        <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-teal-ink">{t.workspace}</p>
        <h1 className="mt-1 font-display text-3xl leading-tight text-navy sm:text-4xl">{view.title}</h1>
        <p className="mt-1 text-sm text-muted">{view.funder}</p>
        <p className="mt-2 text-sm">
          {view.deadline ? c.bids.due(view.deadline, daysUntil(view.deadline, today)) : c.bids.noDeadline} · {c.bids.phase[view.phase]}
        </p>
        <dl className="mt-4 grid grid-cols-2 gap-3 sm:max-w-md">
          <div>
            <dt className="text-xs text-muted">{t.statuses.ready}</dt>
            <dd className="font-display text-2xl tabular-nums text-navy" data-testid="ready-count">
              {view.ready}/{view.total}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{t.blockerTitle}</dt>
            <dd className="font-display text-2xl tabular-nums text-navy" data-testid="blocker-count">
              {view.blockers}
            </dd>
          </div>
        </dl>
        <Link href={`/hope/applications/${view.grant_id}`} className={`mt-3 inline-block text-sm font-semibold text-teal-ink underline ${focusRing}`}>
          {t.openApplication}
        </Link>
      </header>

      {notice && (
        <AutoDismiss key={notice.text} onDismiss={clearNotice}>
          <Notice text={notice.text} ok={notice.ok} />
        </AutoDismiss>
      )}
      {ctx.closed && <p className="rounded-xl bg-gold/15 px-3 py-2 text-sm">{t.readOnly}</p>}

      <div id="bid-tabs" role="tablist" aria-label={t.workspace} className="flex gap-1 overflow-x-auto">
        {(["requirements", "plan", "review"] as const).map((k) => (
          <button
            key={k}
            role="tab"
            type="button"
            aria-selected={tab === k}
            className={`whitespace-nowrap rounded-full px-4 py-2.5 text-sm ${focusRing} ${tab === k ? "bg-navy text-white" : "glass-control text-navy"}`}
            onClick={() => setTab(k)}
          >
            {t.tabs[k]}
          </button>
        ))}
      </div>

      {tab === "requirements" && <Requirements ctx={ctx} members={members} open={open} setOpen={setOpen} />}
      {tab === "plan" && <Plan ctx={ctx} edit={resolve} />}
      {tab === "review" && <FinalReview ctx={ctx} resolve={resolve} />}
    </div>
  );
}

function Requirements({ ctx, members, open, setOpen }: { ctx: Ctx; members: Member[]; open: string | null; setOpen: (k: string | null) => void }) {
  const { bid, t } = ctx;
  const [filter, setFilter] = useState<ItemFilter>("all");
  if (bid.items.length === 0)
    return (
      <Panel>
        <p className="mb-3">{t.noRequirements}</p>
        <Link href={`/hope/applications/${bid.grant_id}`} className={btnPrimary}>
          {t.openApplication}
        </Link>
      </Panel>
    );
  const shown = bid.items.filter((i) => matches(i, filter));
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <label className="text-xs font-semibold text-muted">
          {t.filter}
          <select className={`${input} mt-1 min-w-48`} value={filter} onChange={(e) => setFilter(e.target.value as ItemFilter)}>
            {(["all", "missing", "unassigned", "unreviewed"] as const).map((f) => (
              <option key={f} value={f}>
                {t.filters[f]}
              </option>
            ))}
          </select>
        </label>
      </div>
      {shown.length === 0 ? (
        <Panel>
          <p>{t.none}</p>
        </Panel>
      ) : (
        <ul className="space-y-3">
          {shown.map((i) => (
            <ItemCard key={`${i.key}:${bid.version}`} ctx={ctx} item={i} members={members} open={open === i.key} toggle={() => setOpen(open === i.key ? null : i.key)} />
          ))}
        </ul>
      )}
    </div>
  );
}

const FIELDS = ["owner", "due", "status", "note", "evidence_ref"] as const;

/** A failed write (stale copy, conflict) can land while the user is scrolled far down a long form:
 * bring it into view and focus it so it's read before it dismisses. */
function Notice({ text, ok }: { text: string; ok: boolean }) {
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (ok || !ref.current) return;
    ref.current.scrollIntoView?.({ block: "center" });
    ref.current.focus();
  }, [text, ok]);
  return (
    <p ref={ref} tabIndex={-1} role={ok ? "status" : "alert"} className={`rounded-xl border p-3 text-sm ${focusRing} ${ok ? "border-teal-ink/30 bg-[#eef6f3] text-teal-ink" : "border-red-200 bg-red-50 text-red-800"}`}>
      {text}
    </p>
  );
}

function ItemCard({ ctx, item, members, open, toggle }: { ctx: Ctx; item: BidItem; members: Member[]; open: boolean; toggle: () => void }) {
  const { bid, run, busy, closed, who, when, t } = ctx;
  const initial = { owner: item.owner ?? "", due: item.due ?? "", status: item.status, note: item.note, evidence_ref: item.evidence_ref };
  const [f, setF] = useState(initial);
  const [comment, setComment] = useState("");
  const [needComment, setNeedComment] = useState(false);
  const changes: ItemChanges = {};
  for (const k of FIELDS) {
    if (f[k] === initial[k]) continue;
    if (k === "owner" || k === "due") changes[k] = f[k] || null;
    else if (k === "status") changes.status = f.status;
    else changes[k] = f[k];
  }
  const dirty = Object.keys(changes).length > 0;
  const id = (s: string) => `item-${item.key}-${s}`;
  const review = item.review;

  function decide(decision: api.Decision) {
    if (decision === "changes_requested" && !comment.trim()) return setNeedComment(true);
    setNeedComment(false);
    void run((v) => api.reviewItem(bid.grant_id, item.key, decision, comment.trim(), v), t.saved);
  }

  return (
    <li id={`item-${item.key}`} className="rounded-2xl glass-panel p-4 sm:p-5" data-testid={`item-${item.key}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[11px] uppercase tracking-wider text-muted">{t.kind[item.kind] ?? item.kind}</p>
          <p className="font-semibold text-navy">{item.label}</p>
          <p className="text-xs text-muted">
            {who(item.owner) || t.unassigned} · {t.dueLabel}: {item.due ?? "—"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusTone[item.status]}`}>{t.statuses[item.status]}</span>
          {review?.decision === "approved" && !review.stale && <span className="rounded-full bg-teal-ink px-2.5 py-1 text-xs font-semibold text-white">{t.approve}</span>}
        </div>
      </div>
      {review?.stale && (
        <p role="alert" className="mt-2 rounded-lg bg-[#f6e3df] p-2 text-sm text-red-800">
          {t.staleReview}
        </p>
      )}
      {review && !review.stale && (
        <p className="mt-2 text-sm text-muted" data-testid="review-line">
          {review.decision === "approved" ? t.approvedBy(who(review.by), when(review.at)) : t.changesBy(who(review.by), review.comment)}
        </p>
      )}
      {item.quote && (
        <blockquote className="mt-2 rounded-xl border-l-4 border-gold bg-white/50 p-3 text-sm italic">
          <span className="not-italic font-semibold text-navy">{t.source}: </span>“{item.quote}”
          {item.url && (
            <a href={item.url} target="_blank" rel="noreferrer" className={`ml-1 not-italic text-teal-ink underline ${focusRing}`}>
              ↗
            </a>
          )}
        </blockquote>
      )}
      {closed && (item.evidence_ref || item.note) && (
        <dl className="mt-3 space-y-1 text-sm" data-testid="item-record">
          {item.evidence_ref && (
            <div>
              <dt className="font-semibold text-navy">{t.evidence}</dt>
              <dd className="break-words">{item.evidence_ref}</dd>
            </div>
          )}
          {item.note && (
            <div>
              <dt className="font-semibold text-navy">{t.note}</dt>
              <dd className="whitespace-pre-line break-words">{item.note}</dd>
            </div>
          )}
        </dl>
      )}
      {!closed && (
        <button type="button" className={`mt-3 text-sm text-teal-ink underline ${focusRing}`} aria-expanded={open} onClick={toggle}>
          {open ? t.close : t.edit}
        </button>
      )}
      {open && !closed && (
        <div className="mt-4 space-y-4 border-t border-line pt-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <label htmlFor={id("owner")} className="text-sm font-semibold text-navy">
              {t.owner}
              <select id={id("owner")} className={`${input} mt-1`} value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })}>
                <option value="">{t.unassigned}</option>
                {members.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {who(m.user_id)}
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor={id("due")} className="text-sm font-semibold text-navy">
              {t.dueLabel}
              <input id={id("due")} type="date" className={`${input} mt-1`} value={f.due} max={bid.deadline ?? undefined} onChange={(e) => setF({ ...f, due: e.target.value })} />
            </label>
            <label htmlFor={id("status")} className="text-sm font-semibold text-navy">
              {t.status}
              <select id={id("status")} className={`${input} mt-1`} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as ItemStatus })}>
                {(["missing", "working", "ready"] as const).map((s) => (
                  <option key={s} value={s}>
                    {t.statuses[s]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label htmlFor={id("evidence")} className="block text-sm font-semibold text-navy">
            {t.evidence}
            <input id={id("evidence")} className={`${input} mt-1`} maxLength={500} value={f.evidence_ref} onChange={(e) => setF({ ...f, evidence_ref: e.target.value })} />
          </label>
          <label htmlFor={id("note")} className="block text-sm font-semibold text-navy">
            {t.note}
            <textarea id={id("note")} rows={2} maxLength={2000} className={`${input} mt-1`} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
          </label>
          <button type="button" className={btnPrimary} disabled={!dirty || busy} onClick={() => void run((v) => api.updateItem(bid.grant_id, item.key, changes, v), t.saved)}>
            {t.save}
          </button>

          <div className="rounded-xl border border-line p-3">
            <p className="text-sm font-semibold text-navy">{t.reviewTitle}</p>
            <p className="text-xs text-muted">{t.reviewHelp}</p>
            {item.status !== "ready" ? (
              <p className="mt-2 text-sm text-muted">{t.needsReady}</p>
            ) : (
              <>
                <label htmlFor={id("review")} className="mt-2 block text-sm">
                  {t.reviewComment}
                  <textarea id={id("review")} rows={2} maxLength={2000} className={`${input} mt-1`} value={comment} onChange={(e) => setComment(e.target.value)} aria-invalid={needComment} />
                </label>
                {needComment && (
                  <AutoDismiss onDismiss={() => setNeedComment(false)}>
                    <p role="alert" className="mt-1 text-sm text-red-800">
                      {t.commentRequired}
                    </p>
                  </AutoDismiss>
                )}
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" className={btnPrimary} disabled={busy || dirty || (review?.decision === "approved" && !review.stale)} onClick={() => decide("approved")}>
                    {t.approve}
                  </button>
                  <button type="button" className={btnSecondary} disabled={busy || dirty} onClick={() => decide("changes_requested")}>
                    {t.requestChanges}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

function Plan({ ctx, edit }: { ctx: Ctx; edit: (key: string) => void }) {
  const { bid, who, t } = ctx;
  const dated = bid.items.filter((i) => i.due).sort((p, q) => p.due!.localeCompare(q.due!));
  return (
    <Panel title={t.tabs.plan}>
      <p className="mb-4 text-sm text-muted">{bid.deadline ? t.planHelp : t.noPlan}</p>
      <ol className="space-y-2" data-testid="plan">
        {bid.plan.map((m) => (
          <li key={m.key} className="flex flex-wrap items-center gap-3 rounded-xl border border-line p-3" data-milestone={m.key}>
            <span className="w-24 shrink-0 font-semibold tabular-nums text-navy">{m.due}</span>
            <span className="min-w-40 flex-1 font-medium text-navy">{t.milestones[m.key]}</span>
            <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${m.done ? statusTone.ready : statusTone.working}`}>{m.done ? t.done : t.open}</span>
          </li>
        ))}
        {dated.map((i) => (
          <li key={i.key} className="flex flex-wrap items-center gap-3 rounded-xl border border-line p-3">
            <span className="w-24 shrink-0 tabular-nums text-navy">{i.due}</span>
            <span className="min-w-40 flex-1">
              <span className="block text-navy">{i.label}</span>
              <span className="text-xs text-muted">{who(i.owner) || t.unassigned}</span>
            </span>
            <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusTone[i.status]}`}>{t.statuses[i.status]}</span>
            {!ctx.closed && (
              <button type="button" className={btnSecondary} onClick={() => edit(i.key)}>
                {t.edit}
              </button>
            )}
          </li>
        ))}
        {bid.deadline && (
          <li className="flex flex-wrap items-center gap-3 rounded-xl bg-navy p-3 text-white">
            <span className="w-24 shrink-0 font-semibold tabular-nums">{bid.deadline}</span>
            <span className="flex-1">
              <span className="block font-medium">{t.deadline}</span>
              <span className="text-xs text-white/80">{t.verify}</span>
            </span>
          </li>
        )}
      </ol>
    </Panel>
  );
}

function FinalReview({ ctx, resolve }: { ctx: Ctx; resolve: (key?: string | null) => void }) {
  const { bid, run, busy, who, when, t } = ctx;
  const [comment, setComment] = useState("");
  const [receipt, setReceipt] = useState({ receipt: "", portal: "", date: "" });
  const label = (b: Blocker) => t.blocker[b.code](bid.items.find((i) => i.key === b.key)?.label ?? b.key ?? "");
  const sub = bid.submission;
  return (
    <div className="space-y-4">
      <Panel title={t.finalTitle}>
        <p className="text-sm text-muted">{t.finalHelp}</p>
        {bid.blocker_list.length > 0 && (
          <>
            <h3 className="mt-4 font-semibold text-navy">{t.blockerTitle}</h3>
            <ul className="mt-2 space-y-2" data-testid="blockers">
              {bid.blocker_list.map((b, i) => (
                <li key={i} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line p-3 text-sm">
                  <span>{label(b)}</span>
                  {b.key && (
                    <button type="button" className={btnSecondary} onClick={() => resolve(b.key)}>
                      {t.resolve}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
        {bid.final_review ? (
          <p className="mt-3 text-sm text-teal-ink" data-testid="final-done">
            ✓ {t.finalDone(who(bid.final_review.by), when(bid.final_review.at))}
          </p>
        ) : (
          bid.blocker_list.length === 0 && (
            <div className="mt-3 space-y-2">
              <label className="block text-sm font-semibold text-navy">
                {t.finalComment}
                <textarea rows={2} maxLength={2000} className={`${input} mt-1`} value={comment} onChange={(e) => setComment(e.target.value)} />
              </label>
              <button type="button" className={btnPrimary} disabled={busy} onClick={() => void run((v) => api.finalReview(bid.grant_id, comment.trim(), v), t.saved)}>
                {t.finalApprove}
              </button>
            </div>
          )
        )}
      </Panel>

      {(bid.final_review || sub) && (
        <Panel title={t.receiptTitle}>
          <p className="text-sm text-muted">{t.receiptHelp}</p>
          {sub ? (
            <div className="mt-3 text-sm" data-testid="receipt-done">
              <p className="text-teal-ink">✓ {t.receiptDone(sub.receipt, when(sub.submitted_at), who(sub.recorded_by))}</p>
              <p className="text-muted">
                {t.portal}: {sub.portal} · {t.notSentByHope}
              </p>
            </div>
          ) : (
            <form
              className="mt-3 grid gap-3 sm:grid-cols-3"
              onSubmit={(e) => {
                e.preventDefault();
                const body = { receipt: receipt.receipt.trim(), portal: receipt.portal.trim(), submitted_at: new Date(`${receipt.date}T12:00:00`).toISOString() };
                void run((v) => api.recordSubmission(bid.grant_id, body, v), t.saved);
              }}
            >
              <label className="text-sm font-semibold text-navy">
                {t.receipt}
                <input required maxLength={200} className={`${input} mt-1`} value={receipt.receipt} onChange={(e) => setReceipt({ ...receipt, receipt: e.target.value })} />
              </label>
              <label className="text-sm font-semibold text-navy">
                {t.portal}
                <input required maxLength={200} className={`${input} mt-1`} value={receipt.portal} onChange={(e) => setReceipt({ ...receipt, portal: e.target.value })} />
              </label>
              <label className="text-sm font-semibold text-navy">
                {t.submittedAt}
                <input required type="date" className={`${input} mt-1`} value={receipt.date} onChange={(e) => setReceipt({ ...receipt, date: e.target.value })} />
              </label>
              <button type="submit" className={`${btnPrimary} sm:col-span-3 sm:justify-self-start`} disabled={busy || !receipt.receipt.trim() || !receipt.portal.trim() || !receipt.date}>
                {t.record}
              </button>
            </form>
          )}
        </Panel>
      )}
    </div>
  );
}
