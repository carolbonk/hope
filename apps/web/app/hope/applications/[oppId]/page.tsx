"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ClientOnly, Panel, StageBar, btnPrimary, btnSecondary, daysUntil, focusRing, input, money } from "@/components/hope/ui";
import { useToday } from "@/components/useToday";
import { DraftPanel, type Up } from "@/components/hope/draft/DraftPanel";
import { ApplyWorkspace, ServerNotice } from "@/components/hope/apply/ApplyWorkspace";
import { ReadyGate } from "@/components/hope/apply/ReadyGate";
import { useServerCopy } from "@/components/hope/apply/copy";
import { useServerApplication } from "@/components/hope/apply/useServerApplication";
import { ErrorNotice, Loading } from "@/components/ui/States";
import { online } from "@/api/http";
import { useSession } from "@/api/session";
import * as api from "@/lib/hope/sync/applications";
import type { ApplicationView, Step } from "@/lib/hope/sync/applications";
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
  const opp = useOpportunities().find((o) => o.id === oppId);
  const { state } = useHope();
  const app = state.applications[applicationId(state.profile.id, oppId)];
  if (opp && online && GRANT_ID.test(opp.id)) return <ServerWorkspace opp={opp} app={app} />;
  if (!opp || !app) return <NotFound />;
  return <LocalWorkspace opp={opp} app={app} />;
}

function NotFound() {
  const { h } = useHopeT();
  return (
    <Panel>
      <p role="alert" className="mb-3">
        {h.app.notFound}
      </p>
      <Link href="/hope/saved" className={btnPrimary}>
        {h.saved.title}
      </Link>
    </Panel>
  );
}

/** What the panels can do; the browser store (demo mode) or the server (online) does it. */
type Actions = {
  advance: () => void;
  evidence: (id: string, status: TriState, note: string) => void;
  review: (step: Step, decision: "approve" | "send_back", comment: string) => Promise<boolean>;
  comment: (text: string) => Promise<boolean>;
  busy: boolean;
};

function LocalWorkspace({ opp, app }: { opp: Opportunity; app: Application }) {
  const { h } = useHopeT();
  const a = h.app;
  const { updateApplication } = useHope();
  const up: Up = (fn, event) => updateApplication(app.id, fn, event);
  const actions: Actions = {
    advance: () => {
      const to = NEXT_STAGE[app.stage as keyof typeof NEXT_STAGE];
      up((x) => ({ ...x, stage: to }), `stage:${to}`);
    },
    evidence: (id, status, note) => up((x) => ({ ...x, evidence: { ...x.evidence, [id]: { status, note } } }), `evidence:${id}`),
    review: async (role, decision, note) => {
      const comment = note ? [{ id: crypto.randomUUID(), author: `${role === "program" ? a.programReview : a.directorReview} (${a.you})`, text: note, at: new Date().toISOString() }] : [];
      up((x) => {
        if (decision === "send_back") return { ...x, stage: "eligibility", approvals: { program: "sent_back", director: "pending" }, comments: [...x.comments, ...comment] };
        const approvals = { ...x.approvals, [role]: "approved" as const };
        const both = approvals.program === "approved" && approvals.director === "approved";
        return { ...x, approvals, stage: both ? "drafting" : x.stage, comments: [...x.comments, ...comment] };
      }, `${role}:${decision === "approve" ? "approved" : "sent_back"}`);
      return true;
    },
    comment: async (text) => {
      up((x) => ({ ...x, comments: [...x.comments, { id: crypto.randomUUID(), author: a.you, text, at: new Date().toISOString() }] }), "comment");
      return true;
    },
    busy: false,
  };
  return <Body opp={opp} app={app} actions={actions} draft={<DraftPanel opp={opp} app={app} up={up} />} />;
}

/** H4 + H6 on the server: every write sends `If-Match`, and the page shows what the server returns. */
function ServerWorkspace({ opp, app }: { opp: Opportunity; app?: Application }) {
  const { h } = useHopeT();
  const t = h.apply;
  const c = useServerCopy();
  const { state, updateApplication } = useHope();
  const { me } = useSession();
  const server = useServerApplication(opp.id);
  const { view, run } = server;
  const [gate, setGate] = useState<string | null>(null);

  const who = useCallback((actor: string | null) => (actor === null ? c.hope : actor === me?.user_id ? me.display_name || c.you : c.teammate), [c, me]);
  const display = useMemo(() => (view ? api.mirror(view, app ?? blank(opp, state.profile.id), who) : null), [view, app, opp, state.profile.id, who]);

  // Mirror the server's state into the browser store, once per server change.
  const synced = useRef("");
  useEffect(() => {
    if (!view || !app) return;
    const key = `${view.application_id}:${view.version}:${view.events[0]?.at ?? ""}`;
    if (synced.current === key) return;
    synced.current = key;
    const next = api.mirror(view, app, who);
    updateApplication(app.id, () => next, next.activity.at(-1)?.event ?? "sync");
  }, [view, app, who, updateApplication]);

  if (view === undefined && !server.loadError) return <Loading label={c.loading} />;
  if (!view && server.loadError)
    return (
      <ErrorNotice title={t.loadFailed} onRetry={() => void server.reload()}>
        {t.failed}
      </ErrorNotice>
    );
  if (!view || !display)
    return (
      <Panel>
        <p>{t.notOnServer}</p>
      </Panel>
    );

  const id = view.application_id;
  const ready = (reason?: string) =>
    run(
      (v) => api.moveStage(id, "ready", v, reason),
      (e) => {
        if (e.code !== "stage_blocked" || reason || !view.approvals.program || !view.approvals.director) return false;
        setGate(api.problemMessage(e));
        return true;
      },
    );

  const actions: Actions = {
    advance: async () => {
      if (view.stage === "drafting") {
        if (api.readyGaps(view).length) return setGate("");
        return void ready();
      }
      if (view.stage === "eligibility") {
        // Requirements answered from the profile are recorded too, so the server holds the full evidence.
        for (const r of opp.requirements) {
          if (view.evidence[r.id]) continue;
          const ok = await run((v) => api.recordEvidence(id, { requirement_id: r.id, status: requirementStatus(r, state.profile, display) }, v));
          if (!ok) return;
        }
      }
      const to = NEXT_STAGE[view.stage as keyof typeof NEXT_STAGE];
      if (to) await run((v) => api.moveStage(id, to, v));
    },
    evidence: (rid, status, note) => void run((v) => api.recordEvidence(id, { requirement_id: rid, status, ...(note ? { note } : {}) }, v)),
    review: (step, decision, comment) => run((v) => api.review(id, { step, decision, ...(comment ? { comment } : {}) }, v)),
    comment: (text) => run(() => api.addComment(id, text)),
    busy: server.pending,
  };

  return (
    <>
      <Body
        opp={opp}
        app={display}
        actions={actions}
        view={view}
        who={who}
        notice={<ServerNotice notice={server.notice} onDismiss={server.clearNotice} />}
        draft={
          view.stage === "drafting" || view.stage === "ready" ? (
            <ApplyWorkspace view={view} run={run} />
          ) : (
            <Panel title={h.app.sectionsTitle}>
              <p className="rounded-xl bg-cream px-3 py-2 text-sm">🔒 {h.app.locked}</p>
            </Panel>
          )
        }
      />
      {gate !== null && (
        <ReadyGate
          view={view}
          reason={gate}
          onCancel={() => setGate(null)}
          onConfirm={async (why) => {
            if (await ready(why)) setGate(null);
          }}
        />
      )}
    </>
  );
}

function blank(opp: Opportunity, orgId: string): Application {
  const at = new Date().toISOString();
  return { id: applicationId(orgId, opp.id), orgId, opportunityId: opp.id, stage: "saved", approvals: { program: "pending", director: "pending" }, evidence: {}, sections: {} as Application["sections"], comments: [], activity: [], createdAt: at, updatedAt: at };
}

const NEXT_STAGE = { saved: "eligibility", eligibility: "approval", drafting: "ready" } as const;

type BodyProps = { opp: Opportunity; app: Application; actions: Actions; draft: React.ReactNode; view?: ApplicationView; who?: (actor: string | null) => string; notice?: React.ReactNode };

function Body({ opp, app, actions, draft, view, who, notice }: BodyProps) {
  const { h, locale } = useHopeT();
  const a = h.app;
  const today = useToday()!;
  const { state } = useHope();
  const elig = eligibility(opp, state.profile, app);
  const days = daysUntil(opp.deadline, today);
  const canAdvance = !actions.busy && (app.stage === "saved" || (app.stage === "eligibility" && elig === "meets") || app.stage === "drafting");

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

      {notice}

      <section className="rounded-2xl bg-navy p-5 text-cream" aria-labelledby="next-action">
        <h2 id="next-action" className="text-xs font-semibold uppercase tracking-wide text-gold-light">
          {a.nextAction}
        </h2>
        <p className="mt-1 text-lg">{a.next[app.stage]}</p>
        {app.stage in NEXT_STAGE && (
          <div className="mt-3">
            <button className={btnPrimary} disabled={!canAdvance} onClick={actions.advance}>
              {a.advance[app.stage]}
            </button>
            {app.stage === "eligibility" && elig !== "meets" && <p className="mt-2 text-sm text-gold-light">{a.blocked}</p>}
          </div>
        )}
        {app.stage === "ready" && <p className="mt-2 text-sm text-cream/80">{a.humanSubmit}</p>}
      </section>

      <EligibilityPanel opp={opp} app={app} actions={actions} locked={!!view && !["saved", "eligibility"].includes(view.stage)} />
      <ApprovalPanel app={app} actions={actions} view={view} who={who} />
      {draft}

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

      <CommentsPanel app={app} actions={actions} />

      <details className="rounded-2xl glass-panel p-5">
        <summary className={`cursor-pointer font-display text-xl ${focusRing}`}>{a.activity}</summary>
        <ul className="mt-3 space-y-1 text-sm text-navy/80">
          {[...app.activity].reverse().map((ev, i) => (
            <li key={i}>
              <time dateTime={ev.at}>{new Date(ev.at).toLocaleString(locale)}</time> — {ev.event}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-navy/60">ID: {view?.application_id ?? app.id}</p>
      </details>
    </div>
  );
}

const GRANT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const REQ_FACT: Record<string, FieldKey> = { c3: "has501c3", budget: "annualBudget", geo: "serviceArea" };


function EligibilityPanel({ opp, app, actions, locked }: { opp: Opportunity; app: Application; actions: Actions; locked: boolean }) {
  const { h } = useHopeT();
  const c = useServerCopy();
  const { state } = useHope();
  const elig = eligibility(opp, state.profile, app);
  return (
    <Panel title={h.app.eligibilityTitle}>
      <p className="mb-1 text-sm font-semibold">{h.discover.elig[elig]}</p>
      <p className="mb-3 text-xs text-muted">{h.app.eligSeparate}</p>
      {locked && <p className="mb-3 text-xs text-navy/70">{c.evidenceLocked}</p>}
      {opp.requirements.length === 0 && <p className="text-sm">—</p>}
      <ul className="space-y-4">
        {opp.requirements.map((r) => {
          const status = requirementStatus(r, state.profile, app);
          const fromProfile = !app.evidence[r.id] && status !== "unknown";
          return (
            <li key={r.id} className="rounded-xl border border-line p-3">
              <fieldset disabled={locked || actions.busy}>
                <legend className="font-semibold">{r.label}</legend>
                <div className="mt-2 flex flex-wrap gap-2">
                  {(["yes", "no", "unknown"] as TriState[]).map((v) => (
                    <label key={v} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-full border px-3 text-sm ${status === v ? "border-teal-ink bg-sage" : "border-navy/20"}`}>
                      <input type="radio" name={`ev-${r.id}`} className={focusRing} checked={status === v} onChange={() => actions.evidence(r.id, v, app.evidence[r.id]?.note ?? "")} />
                      {h[v]}
                    </label>
                  ))}
                </div>
                {fromProfile && <p className="mt-1 text-xs text-navy/60">{h.app.fromProfile(h.profile.status[r.id === "sam" ? reqStatus(state.profile, "sam") : factStatus(state.profile, REQ_FACT[r.id] ?? (r.field as FieldKey))] ?? "")}</p>}
                <EvidenceNote key={online ? `${r.id}:${app.evidence[r.id]?.note ?? ""}` : r.id} id={r.id} note={app.evidence[r.id]?.note ?? ""} onSave={(note) => actions.evidence(r.id, status, note)} live={!online} />
              </fieldset>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

/** Demo mode saves every keystroke in the browser; online the note is sent when the field loses focus. */
function EvidenceNote({ id, note, onSave, live }: { id: string; note: string; onSave: (note: string) => void; live: boolean }) {
  const { h } = useHopeT();
  const [draft, setDraft] = useState(note);
  return (
    <>
      <label htmlFor={`note-${id}`} className="mt-2 block text-sm">
        {h.app.evidence}
      </label>
      <input
        id={`note-${id}`}
        className={input}
        maxLength={500}
        value={live ? note : draft}
        onChange={(e) => (live ? onSave(e.target.value) : setDraft(e.target.value))}
        onBlur={() => !live && draft.trim() !== note && onSave(draft.trim())}
      />
    </>
  );
}

function ApprovalPanel({ app, actions, view, who }: { app: Application; actions: Actions; view?: ApplicationView; who?: (actor: string | null) => string }) {
  const { h, locale } = useHopeT();
  const a = h.app;
  const c = useServerCopy();
  const [note, setNote] = useState("");
  const [err, setErr] = useState(false);
  const active = app.stage === "approval" && !actions.busy;

  async function decide(role: Step, decision: "approve" | "send_back") {
    if (decision === "send_back" && !note.trim()) return setErr(true);
    setErr(false);
    if (await actions.review(role, decision, note.trim())) setNote("");
  }

  const status = (role: Step) => {
    const done = view?.approvals[role];
    if (done && who) return c.approvedBy(who(done.by), new Date(done.at).toLocaleString(locale));
    return view && app.approvals[role] === "approved" ? c.approved : a[app.approvals[role]];
  };

  const row = (role: Step, label: string, enabled: boolean) => (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line p-3">
      <div>
        <p className="font-semibold">{label}</p>
        <p className="text-sm" data-testid={`approval-${role}`}>
          {status(role)}
        </p>
      </div>
      <div className="flex gap-2">
        <button className={btnSecondary} disabled={!enabled} onClick={() => void decide(role, "send_back")}>
          {a.sendBack}
        </button>
        <button className={btnPrimary} disabled={!enabled} onClick={() => void decide(role, "approve")}>
          {a.approve}
        </button>
      </div>
    </div>
  );

  return (
    <Panel title={a.approvalsTitle}>
      <p className="mb-3 rounded-xl bg-gold/15 px-3 py-2 text-sm">{view ? c.recorded : a.simulated}</p>
      <div className="space-y-2">
        {row("program", a.programReview, active && app.approvals.program !== "approved")}
        {row("director", a.directorReview, active && app.approvals.program === "approved")}
        {app.stage === "approval" && app.approvals.program !== "approved" && (
          <p className="text-xs text-navy/60">
            {a.directorReview}: {a.needsProgram}
          </p>
        )}
      </div>
      {app.stage === "approval" && (
        <div className="mt-3">
          <label htmlFor="approval-note" className="block text-sm font-semibold">
            {a.commentsTitle}
          </label>
          <textarea id="approval-note" rows={2} maxLength={1000} className={input} value={note} onChange={(e) => setNote(e.target.value)} aria-invalid={err} />
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

function CommentsPanel({ app, actions }: { app: Application; actions: Actions }) {
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
        onSubmit={async (e) => {
          e.preventDefault();
          if (!text.trim()) return;
          if (await actions.comment(text.trim())) setText("");
        }}
      >
        <label htmlFor="new-comment" className="sr-only">
          {h.app.commentPlaceholder}
        </label>
        <input id="new-comment" className={input} maxLength={2000} placeholder={h.app.commentPlaceholder} value={text} onChange={(e) => setText(e.target.value)} />
        <button className={btnSecondary} type="submit" disabled={actions.busy}>
          {h.app.addComment}
        </button>
      </form>
    </Panel>
  );
}
