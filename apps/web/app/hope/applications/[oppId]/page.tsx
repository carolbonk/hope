"use client";

import Link from "next/link";
import { use, useState } from "react";
import { ClientOnly, Panel, StageBar, btnPrimary, btnSecondary, daysUntil, focusRing, input, money } from "@/components/hope/ui";
import { useToday } from "@/components/useToday";
import { DraftPanel, type Up } from "@/components/hope/draft/DraftPanel";
import { ApplyWorkspace } from "@/components/hope/apply/ApplyWorkspace";
import { online } from "@/api/http";
import { useHopeT } from "@/lib/hope/i18n";
import { useOpportunities } from "@/lib/hope/opportunities";
import { factStatus, oppDocs, reqStatus, type FieldKey } from "@/lib/hope/dossier";
import { applicationId, eligibility, requirementStatus, useHope } from "@/lib/hope/store";
import type { Application, Opportunity, TriState } from "@/lib/hope/types";
import { AutoDismiss } from "@/components/ui/AutoDismiss";

export default function ApplicationPage({ params }: { params: Promise<{ oppId: string }> }) {
  const { oppId } = use(params);
  return (
    <ClientOnly>
      <Workspace oppId={decodeURIComponent(oppId)} />
    </ClientOnly>
  );
}

function Workspace({ oppId }: { oppId: string }) {
  const { h, locale } = useHopeT();
  const a = h.app;
  const today = useToday()!;
  const opp = useOpportunities().find((o) => o.id === oppId);
  const { state, updateApplication } = useHope();
  const app = state.applications[applicationId(state.profile.id, oppId)];

  if (!opp || !app)
    return (
      <Panel>
        <p role="alert" className="mb-3">
          {a.notFound}
        </p>
        <Link href="/hope/saved" className={btnPrimary}>
          {h.saved.title}
        </Link>
      </Panel>
    );

  const up = (fn: (x: Application) => Application, event: string) => updateApplication(app.id, fn, event);
  const elig = eligibility(opp, state.profile, app);
  const days = daysUntil(opp.deadline, today);
  const canAdvance = app.stage === "saved" || (app.stage === "eligibility" && elig === "meets") || app.stage === "drafting";
  const nextStage = { saved: "eligibility", eligibility: "approval", drafting: "ready" } as const;

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <Link href="/hope/saved" className={`text-sm text-teal-ink underline ${focusRing}`}>
          ← {h.saved.title}
        </Link>
        <p className="pt-3 text-[11px] uppercase tracking-[0.16em] text-muted">
          {opp.funder}
          {opp.source.kind === "demo" && (
            <>
              {" · "}
              <span className="rounded bg-[#f1ead8] px-1.5 font-semibold normal-case tracking-normal text-[#6b5520]">{h.demo}</span>
            </>
          )}
        </p>
        <h1 className="font-display text-4xl leading-tight sm:text-5xl">{opp.name}</h1>
        <p className="text-sm">
          {money(opp.amountMin, opp.currency, locale)}–{money(opp.amountMax, opp.currency, locale)} ·{" "}
          <span className={days <= 14 ? "font-semibold text-red-800" : ""}>
            {a.deadline}: {h.discover.due(opp.deadline, days)}
          </span>
        </p>
        <StageBar stage={app.stage} />
      </header>

      <section className="rounded-2xl bg-navy p-5 text-cream" aria-labelledby="next-action">
        <h2 id="next-action" className="text-xs font-semibold uppercase tracking-wide text-gold-light">
          {a.nextAction}
        </h2>
        <p className="mt-1 text-lg">{a.next[app.stage]}</p>
        {app.stage in nextStage && (
          <div className="mt-3">
            <button
              className={btnPrimary}
              disabled={!canAdvance}
              onClick={() => up((x) => ({ ...x, stage: nextStage[app.stage as keyof typeof nextStage] }), `stage:${nextStage[app.stage as keyof typeof nextStage]}`)}
            >
              {a.advance[app.stage]}
            </button>
            {!canAdvance && app.stage === "eligibility" && <p className="mt-2 text-sm text-gold-light">{a.blocked}</p>}
          </div>
        )}
        {app.stage === "ready" && <p className="mt-2 text-sm text-cream/80">{a.humanSubmit}</p>}
      </section>

      <EligibilityPanel opp={opp} app={app} up={up} />
      <ApprovalPanel app={app} up={up} />
      {online && GRANT_ID.test(opp.id) ? (
        app.stage === "drafting" || app.stage === "ready" ? (
          <ApplyWorkspace grantId={opp.id} />
        ) : (
          <Panel title={a.sectionsTitle}>
            <p className="rounded-xl bg-cream px-3 py-2 text-sm">🔒 {a.locked}</p>
          </Panel>
        )
      ) : (
        <DraftPanel opp={opp} app={app} up={up} />
      )}

      <details className="rounded-2xl glass-panel p-5">
        <summary className={`cursor-pointer font-display text-xl ${focusRing}`}>{a.documentsTitle}</summary>
        <p className="mt-2 text-sm text-muted">{a.docsFromDossier}</p>
        {oppDocs(opp, state.profile).length === 0 ? (
          <p className="mt-3 text-sm">{a.docsNone}</p>
        ) : (
          <ul className="mt-3 divide-y divide-line" data-testid="call-docs">
            {oppDocs(opp, state.profile).map((d) => (
              <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 py-2" data-doc={d.id}>
                <span>{h.profile.req[d.id]}</span>
                <span className="text-sm font-semibold" data-level={d.level}>
                  {d.level === "auto_na" || d.level === "needs_info" ? `${h.profile.level[d.level]} · ` : ""}
                  {d.expired ? h.profile.expired : h.profile.status[d.status]}
                </span>
              </li>
            ))}
          </ul>
        )}
        <Link href="/hope/profile" className={`mt-3 inline-block text-sm font-semibold text-teal-ink underline ${focusRing}`}>
          {a.docsEdit}
        </Link>
      </details>

      <CommentsPanel app={app} up={up} />

      <details className="rounded-2xl glass-panel p-5">
        <summary className={`cursor-pointer font-display text-xl ${focusRing}`}>{a.activity}</summary>
        <ul className="mt-3 space-y-1 text-sm text-navy/80">
          {[...app.activity].reverse().map((ev, i) => (
            <li key={i}>
              <time dateTime={ev.at}>{new Date(ev.at).toLocaleString(locale)}</time> — {ev.event}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-navy/60">ID: {app.id}</p>
      </details>
    </div>
  );
}

const GRANT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const REQ_FACT: Record<string, FieldKey> = { c3: "has501c3", budget: "annualBudget", geo: "serviceArea" };


function EligibilityPanel({ opp, app, up }: { opp: Opportunity; app: Application; up: Up }) {
  const { h } = useHopeT();
  const { state } = useHope();
  const elig = eligibility(opp, state.profile, app);
  return (
    <Panel title={h.app.eligibilityTitle}>
      <p className="mb-1 text-sm font-semibold">{h.discover.elig[elig]}</p>
      <p className="mb-3 text-xs text-muted">{h.app.eligSeparate}</p>
      {opp.requirements.length === 0 && <p className="text-sm">—</p>}
      <ul className="space-y-4">
        {opp.requirements.map((r) => {
          const status = requirementStatus(r, state.profile, app);
          const ev = app.evidence[r.id] ?? { status, note: "" };
          const fromProfile = !app.evidence[r.id] && status !== "unknown";
          return (
            <li key={r.id} className="rounded-xl border border-line p-3">
              <fieldset>
                <legend className="font-semibold">{r.label}</legend>
                <div className="mt-2 flex flex-wrap gap-2">
                  {(["yes", "no", "unknown"] as TriState[]).map((v) => (
                    <label key={v} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-full border px-3 text-sm ${status === v ? "border-teal-ink bg-sage" : "border-navy/20"}`}>
                      <input
                        type="radio"
                        name={`ev-${r.id}`}
                        className={focusRing}
                        checked={status === v}
                        onChange={() => up((x) => ({ ...x, evidence: { ...x.evidence, [r.id]: { ...ev, status: v } } }), `evidence:${r.id}`)}
                      />
                      {h[v]}
                    </label>
                  ))}
                </div>
                {fromProfile && <p className="mt-1 text-xs text-navy/60">{h.app.fromProfile(h.profile.status[r.id === "sam" ? reqStatus(state.profile, "sam") : factStatus(state.profile, REQ_FACT[r.id] ?? (r.field as FieldKey))] ?? "")}</p>}
                <label htmlFor={`note-${r.id}`} className="mt-2 block text-sm">
                  {h.app.evidence}
                </label>
                <input
                  id={`note-${r.id}`}
                  className={input}
                  value={ev.note}
                  onChange={(e) => up((x) => ({ ...x, evidence: { ...x.evidence, [r.id]: { ...ev, note: e.target.value } } }), `evidence_note:${r.id}`)}
                />
              </fieldset>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function ApprovalPanel({ app, up }: { app: Application; up: Up }) {
  const { h } = useHopeT();
  const a = h.app;
  const [note, setNote] = useState("");
  const [err, setErr] = useState(false);
  const active = app.stage === "approval";

  function decide(role: "program" | "director", decision: "approved" | "sent_back") {
    if (decision === "sent_back" && !note.trim()) return setErr(true);
    setErr(false);
    const comment = note.trim() ? [{ id: crypto.randomUUID(), author: `${role === "program" ? a.programReview : a.directorReview} (${a.you})`, text: note.trim(), at: new Date().toISOString() }] : [];
    up((x) => {
      const approvals = { ...x.approvals, [role]: decision };
      if (decision === "sent_back") return { ...x, stage: "eligibility", approvals: { program: "sent_back", director: "pending" }, comments: [...x.comments, ...comment] };
      const both = approvals.program === "approved" && approvals.director === "approved";
      return { ...x, approvals, stage: both ? "drafting" : x.stage, comments: [...x.comments, ...comment] };
    }, `${role}:${decision}`);
    setNote("");
  }

  const row = (role: "program" | "director", label: string, enabled: boolean) => (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line p-3">
      <div>
        <p className="font-semibold">{label}</p>
        <p className="text-sm">{a[app.approvals[role]]}</p>
      </div>
      <div className="flex gap-2">
        <button className={btnSecondary} disabled={!enabled} onClick={() => decide(role, "sent_back")}>
          {a.sendBack}
        </button>
        <button className={btnPrimary} disabled={!enabled} onClick={() => decide(role, "approved")}>
          {a.approve}
        </button>
      </div>
    </div>
  );

  return (
    <Panel title={a.approvalsTitle}>
      <p className="mb-3 rounded-xl bg-gold/15 px-3 py-2 text-sm">{a.simulated}</p>
      <div className="space-y-2">
        {row("program", a.programReview, active && app.approvals.program !== "approved")}
        {row("director", a.directorReview, active && app.approvals.program === "approved")}
        {active && app.approvals.program !== "approved" && <p className="text-xs text-navy/60">{a.directorReview}: {a.needsProgram}</p>}
      </div>
      {active && (
        <div className="mt-3">
          <label htmlFor="approval-note" className="block text-sm font-semibold">
            {a.commentsTitle}
          </label>
          <textarea id="approval-note" rows={2} className={input} value={note} onChange={(e) => setNote(e.target.value)} aria-invalid={err} />
          {err && (
            <AutoDismiss>
              <p role="alert" className="mt-1 text-sm text-red-800">
                {a.commentRequired}
              </p>
            </AutoDismiss>
          )}
        </div>
      )}
    </Panel>
  );
}

function CommentsPanel({ app, up }: { app: Application; up: Up }) {
  const { h, locale } = useHopeT();
  const [text, setText] = useState("");
  return (
    <Panel title={h.app.commentsTitle}>
      <ul className="mb-3 space-y-2">
        {app.comments.map((c) => (
          <li key={c.id} className="rounded-xl bg-cream p-3 text-sm">
            <p className="text-xs text-navy/70">
              {c.author} · {new Date(c.at).toLocaleString(locale)}
            </p>
            <p>{c.text}</p>
          </li>
        ))}
      </ul>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!text.trim()) return;
          up((x) => ({ ...x, comments: [...x.comments, { id: crypto.randomUUID(), author: h.app.you, text: text.trim(), at: new Date().toISOString() }] }), "comment");
          setText("");
        }}
      >
        <label htmlFor="new-comment" className="sr-only">
          {h.app.commentPlaceholder}
        </label>
        <input id="new-comment" className={input} placeholder={h.app.commentPlaceholder} value={text} onChange={(e) => setText(e.target.value)} />
        <button className={btnSecondary} type="submit">
          {h.app.addComment}
        </button>
      </form>
    </Panel>
  );
}
