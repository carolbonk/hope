"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ProblemError } from "@/api/http";
import { Panel, btnPrimary, btnSecondary, focusRing, input } from "@/components/hope/ui";
import { AutoDismiss } from "@/components/ui/AutoDismiss";
import { Badge, type Tone } from "@/components/ui/Badge";
import type { IconName } from "@/components/ui/Icon";
import { Modal } from "@/components/ui/Modal";
import { ErrorNotice, Loading } from "@/components/ui/States";
import { useHopeT } from "@/lib/hope/i18n";
import * as api from "@/lib/hope/sync/applications";
import type { Answer, ApplicationView, Change, ChecklistItem, InputNeeded, Question, Rule, Term } from "@/lib/hope/sync/applications";

type Run = (call: () => Promise<ApplicationView>, onConflict?: () => boolean) => Promise<boolean>;

const TERM_ORDER = ["at_risk", "action_needed", "check", "have", "info"];
const TERM_TONE: Record<string, [Tone, IconName]> = {
  at_risk: ["bad", "alert"],
  action_needed: ["warn", "alert"],
  check: ["info", "eye"],
  have: ["good", "check"],
  info: ["neutral", "dot"],
};
const Q_TONE: Record<string, [Tone, IconName]> = {
  missing: ["neutral", "minus"],
  drafted: ["info", "check"],
  edited: ["good", "user"],
  over_limit: ["bad", "alert"],
  to_confirm: ["warn", "alert"],
};
const RULE_ORDER = ["not_met", "unknown", "applies", "met", "not_applicable"];
const RULE_TONE: Record<string, [Tone, IconName]> = {
  met: ["good", "check"],
  not_met: ["bad", "alert"],
  unknown: ["warn", "eye"],
  applies: ["info", "alert"],
  not_applicable: ["neutral", "minus"],
};
const POLL_MS = 2000;

/** SC29: the funder's own form, translated, with drafted answers and a to-do list. */
export function ApplyWorkspace({ grantId }: { grantId: string }) {
  const { h } = useHopeT();
  const t = h.apply;
  const [view, setView] = useState<ApplicationView | null | undefined>(undefined);
  const [loadError, setLoadError] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const latest = useRef<ApplicationView | null>(null);

  const show = useCallback((v: ApplicationView | null) => {
    latest.current = v;
    setView(v);
  }, []);

  const reload = useCallback(async () => {
    const id = latest.current?.application_id;
    try {
      show(id ? await api.getApplication(id) : await api.findApplication(grantId));
      setLoadError(false);
    } catch {
      setLoadError(true);
    }
  }, [grantId, show]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const working = !!view && (api.running(view.requirements_job) || api.running(view.answers_job));
  useEffect(() => {
    if (!working) return;
    const timer = setTimeout(() => void reload(), POLL_MS);
    return () => clearTimeout(timer);
  }, [working, view, reload]);

  const run: Run = useCallback(
    async (call, onConflict) => {
      setNotice(null);
      try {
        show(await call());
        return true;
      } catch (err) {
        const e = err instanceof ProblemError ? err : null;
        if (e?.status === 412) {
          setNotice(t.stale);
          await reload();
        } else if (e?.status === 409 && e.code === "human_edit" && onConflict?.()) {
          return true;
        } else if (e?.status === 409) setNotice(t.busy);
        else if (e?.code === "profile_incomplete") setNotice(t.profileIncomplete);
        else setNotice(t.failed);
        return false;
      }
    },
    [reload, show, t],
  );

  if (view === undefined && !loadError) return <Loading label={t.loading} />;
  if (loadError)
    return (
      <ErrorNotice title={t.loadFailed} onRetry={() => void reload()}>
        {t.failed}
      </ErrorNotice>
    );
  if (!view)
    return (
      <Panel>
        <p>{t.notOnServer}</p>
      </Panel>
    );

  return (
    <div className="space-y-4" data-testid="apply-workspace">
      {notice && (
        <AutoDismiss key={notice} onDismiss={() => setNotice(null)}>
          <p role="alert" className="rounded-xl glass-panel px-3 py-2 text-sm text-navy">
            {notice}
          </p>
        </AutoDismiss>
      )}
      <FormSource view={view} run={run} />
      <ChangesPanel changes={view.changes ?? []} />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <RulesPanel view={view} run={run} latest={latest} />
          <TermsPanel terms={view.terms} />
          <QuestionList view={view} run={run} latest={latest} />
          <Uploads items={view.checklist.items.filter((i) => i.kind === "attachment")} />
        </div>
        <TodoPanel view={view} run={run} latest={latest} />
      </div>
      <ReadyPanel view={view} />
    </div>
  );
}

function FormSource({ view, run }: { view: ApplicationView; run: Run }) {
  const { h } = useHopeT();
  const t = h.apply;
  const [pasting, setPasting] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const id = view.application_id;
  const req = view.requirements;
  const pages = req?.pages ?? [];
  const blocked = pages.filter((p) => p.status === "failed");
  const reading = api.running(view.requirements_job) || view.questions_status === "reading";
  const standard = view.questions.some((q) => q.source === "standard");

  async function submitPaste() {
    if (text.trim().length < 20) return setError(t.tooShort);
    if (await run(() => api.pasteForm(id, { text }))) {
      setPasting(false);
      setText("");
    }
  }

  async function uploadPdf(f: File | undefined) {
    if (!f) return;
    if (f.size > 8_000_000) return setError(t.pdfTooBig);
    const pdf_base64 = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
      reader.onerror = reject;
      reader.readAsDataURL(f);
    });
    if (!(await run(() => api.pasteForm(id, { pdf_base64 })))) setError(t.pdfFailed);
  }

  return (
    <Panel title={t.formTitle}>
      {reading ? (
        <p role="status" className="animate-pulse text-sm">
          {t.reading}
        </p>
      ) : view.questions_status === "unread" ? (
        <p className="text-sm">{t.unread}</p>
      ) : (
        <p className="text-sm">{t.readFrom(pages.filter((p) => p.status !== "failed").length, view.questions.length, req?.attachments.length ?? 0)}</p>
      )}
      {!reading && (view.questions_status === "not_found" || standard) && <p className="mt-2 rounded-xl bg-gold/15 px-3 py-2 text-sm">{view.questions_status === "not_found" ? t.notFound : t.standard}</p>}
      {blocked.length > 0 && (
        <details className="mt-2 text-sm">
          <summary className={`cursor-pointer ${focusRing}`}>{t.blocked(blocked.length)}</summary>
          <ul className="mt-1 list-inside list-disc break-all text-xs text-muted">
            {blocked.map((p) => (
              <li key={p.url}>{p.url}</li>
            ))}
          </ul>
        </details>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted">{t.behindLogin}</span>
        <button className={btnSecondary} disabled={reading} onClick={() => setPasting(true)}>
          {t.paste}
        </button>
        <button className={btnSecondary} disabled={reading} onClick={() => file.current?.click()}>
          {t.upload}
        </button>
        <input ref={file} type="file" accept="application/pdf" className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => void uploadPdf(e.target.files?.[0])} />
        <button className={btnSecondary} disabled={reading} onClick={() => void run(() => api.readRequirements(id))}>
          {view.questions_status === "unread" ? t.readNow : t.readAgain}
        </button>
      </div>
      {error && (
        <AutoDismiss key={error} onDismiss={() => setError(null)}>
          <p role="alert" className="mt-2 text-sm text-bad">
            {error}
          </p>
        </AutoDismiss>
      )}
      <Modal
        open={pasting}
        title={t.pasteTitle}
        description={t.pasteHint}
        onClose={() => setPasting(false)}
        footer={
          <div className="flex justify-end gap-2">
            <button className={btnSecondary} onClick={() => setPasting(false)}>
              {t.cancel}
            </button>
            <button className={btnPrimary} onClick={() => void submitPaste()}>
              {t.pasteSave}
            </button>
          </div>
        }
      >
        <label htmlFor="paste-form" className="block text-sm font-semibold">
          {t.pasteLabel}
        </label>
        <p className="mb-2 text-xs text-muted">{t.pasteHint}</p>
        <textarea id="paste-form" rows={12} className={input} value={text} onChange={(e) => setText(e.target.value)} />
      </Modal>
    </Panel>
  );
}

function ChangesPanel({ changes }: { changes: Change[] }) {
  const { h } = useHopeT();
  const t = h.apply;
  if (changes.length === 0) return null;
  return (
    <Panel title={t.changesTitle(changes.length)}>
      <p className="text-sm text-muted">{t.changesIntro}</p>
      <ul className="mt-2 space-y-2 text-sm" data-testid="changes">
        {changes.map((c, i) => (
          <li key={`${c.what}:${c.text}:${i}`} className="flex flex-wrap items-baseline gap-2" data-change={c.what}>
            <Badge tone={c.change === "removed" ? "bad" : c.change === "added" ? "info" : "warn"} icon={c.change === "removed" ? "minus" : "alert"}>
              {t.changeKind[c.change]}
            </Badge>
            <span>
              <span className="font-semibold">{t.changeWhat[c.what]}:</span> {c.text}
              {c.before && <span className="text-muted"> {t.was(c.before)}</span>}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function RulesPanel({ view, run, latest }: { view: ApplicationView; run: Run; latest: React.RefObject<ApplicationView | null> }) {
  const { h } = useHopeT();
  const t = h.apply;
  if (!view.requirements) return null;
  const rules = view.rules ?? [];
  const kinds = ["eligibility", "budget", "conditional"] as const;
  return (
    <Panel title={t.rulesTitle}>
      <p className="text-sm text-muted">{t.rulesIntro}</p>
      <AskForm view={view} run={run} latest={latest} />
      {rules.length === 0 && <p className="mt-3 text-sm">{t.noRules}</p>}
      {kinds.map((kind) => {
        const mine = rules.filter((r) => r.kind === kind).sort((a, b) => RULE_ORDER.indexOf(a.status) - RULE_ORDER.indexOf(b.status));
        if (mine.length === 0) return null;
        return (
          <section key={kind} className="mt-4" aria-label={t.ruleGroup[kind]}>
            <h3 className="text-sm font-semibold">
              {t.ruleGroup[kind]} ({mine.length})
            </h3>
            <ul className="mt-1 space-y-2">
              {mine.map((rule) => (
                <RuleRow key={rule.key} rule={rule} view={view} run={run} latest={latest} />
              ))}
            </ul>
          </section>
        );
      })}
    </Panel>
  );
}

function AskForm({ view, run, latest }: { view: ApplicationView; run: Run; latest: React.RefObject<ApplicationView | null> }) {
  const { h } = useHopeT();
  const t = h.apply;
  const current = view.ask ? view.ask.amount_minor / 100 : null;
  const [value, setValue] = useState(current === null ? "" : String(current));
  const dollars = Number(value.replace(/[$,\s]/g, ""));
  const valid = value.trim() !== "" && Number.isFinite(dollars) && dollars > 0;
  return (
    <form
      className="mt-3 flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) void run(() => api.setAsk(view.application_id, Math.round(dollars * 100), latest.current?.version ?? view.version));
      }}
    >
      <label htmlFor="ask-amount" className="text-sm">
        <span className="block font-semibold">{t.askLabel}</span>
        <input id="ask-amount" inputMode="decimal" className={`${input} w-40`} placeholder="$25,000" value={value} onChange={(e) => setValue(e.target.value)} aria-describedby="ask-help" />
      </label>
      <button type="submit" className={btnSecondary} disabled={!valid || dollars === current}>
        {t.save}
      </button>
      <p id="ask-help" className="w-full text-xs text-muted">
        {t.askHelp}
      </p>
    </form>
  );
}

function RuleRow({ rule, view, run, latest }: { rule: Rule; view: ApplicationView; run: Run; latest: React.RefObject<ApplicationView | null> }) {
  const { h } = useHopeT();
  const t = h.apply;
  const [tone, icon] = RULE_TONE[rule.status] ?? (["neutral", "dot"] as [Tone, IconName]);
  const canConfirm = rule.status === "unknown" && (view.stage === "saved" || view.stage === "eligibility");
  const conditional = rule.kind === "conditional";
  const confirm = (yes: boolean) => void run(() => api.confirmRule(view.application_id, rule.key, yes, latest.current?.version ?? view.version));
  return (
    <li className="rounded-xl border border-line p-3 text-sm" data-rule={rule.key} data-status={rule.status}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{rule.label}</span>
        <Badge tone={tone} icon={icon}>
          {t.ruleStatus[rule.status]}
        </Badge>
        <span className="text-xs text-muted">{t.owner[rule.owner]}</span>
      </div>
      <p className="mt-1">{rule.reason}</p>
      {rule.todo && !conditional && rule.status !== "met" && <p className="mt-1">{t.whatToDo(rule.todo)}</p>}
      <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-muted">{t.funderSaid}</p>
      <blockquote className="border-l-2 border-line pl-2 italic">“{rule.quote}”</blockquote>
      {rule.url === api.PASTED ? (
        <p className="text-xs text-muted">{t.fromPasted}</p>
      ) : (
        <a href={rule.url} target="_blank" rel="noreferrer" className={`text-xs text-teal-ink underline ${focusRing}`}>
          {t.viewOnPage}
        </a>
      )}
      <p className="mt-1 text-xs text-muted">{rule.confirmed_by_staff ? t.checkedByStaff : t.checkedByHope}</p>
      {canConfirm && (
        <div className="mt-2 flex flex-wrap gap-2">
          <button className={btnSecondary} onClick={() => confirm(true)}>
            {conditional ? t.appliesToUs : t.weMeetIt}
          </button>
          <button className={btnSecondary} onClick={() => confirm(false)}>
            {conditional ? t.doesntApply : t.weDont}
          </button>
        </div>
      )}
    </li>
  );
}

function TermsPanel({ terms }: { terms: Term[] }) {
  const { h } = useHopeT();
  const t = h.apply;
  const [all, setAll] = useState(false);
  if (terms.length === 0) return null;
  const sorted = [...terms].sort((a, b) => TERM_ORDER.indexOf(a.status) - TERM_ORDER.indexOf(b.status));
  const urgent = sorted.filter((x) => x.status !== "info");
  const shown = all || urgent.length === 0 ? sorted : urgent;
  return (
    <Panel title={t.termsTitle(terms.length)}>
      <ul className="space-y-3">
        {shown.map((term) => (
          <TermRow key={`${term.key ?? term.term}:${term.quote}`} term={term} />
        ))}
      </ul>
      {shown.length < sorted.length || all ? (
        <button className={`mt-3 text-sm font-semibold text-teal-ink underline ${focusRing}`} aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? t.showFewer : t.showAll(sorted.length)}
        </button>
      ) : null}
    </Panel>
  );
}

function TermRow({ term }: { term: Term }) {
  const { h } = useHopeT();
  const t = h.apply;
  const [tone, icon] = TERM_TONE[term.status] ?? (["neutral", "dot"] as [Tone, IconName]);
  const host = term.source_url ? new URL(term.source_url).host.replace(/^www\./, "") : "";
  return (
    <li className="rounded-xl border border-line p-3 text-sm" data-term={term.key ?? term.term}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{term.term}</span>
        <Badge tone={tone} icon={icon}>
          {t.termStatus[term.status]}
        </Badge>
        {term.owner && <span className="text-xs text-muted">{t.owner[term.owner]}</span>}
      </div>
      <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-muted">{t.funderSaid}</p>
      <blockquote className="border-l-2 border-line pl-2 italic">“{term.quote}”</blockquote>
      {term.url === api.PASTED ? (
        <p className="text-xs text-muted">{t.fromPasted}</p>
      ) : (
        <a href={term.url} target="_blank" rel="noreferrer" className={`text-xs text-teal-ink underline ${focusRing}`}>
          {t.viewOnPage}
        </a>
      )}
      <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-muted">{t.means}</p>
      <p>{term.plain}</p>
      {term.todo && <p className="mt-1">{t.whatToDo(term.todo)}</p>}
      {term.detail && <p className="mt-1 font-semibold">{term.detail}</p>}
      <p className="mt-2 text-xs text-muted" data-source={term.explained_by}>
        {term.explained_by === "official" && term.source_url ? (
          <a href={term.source_url} target="_blank" rel="noreferrer" className={`underline ${focusRing}`}>
            {t.sourceOfficial(host)}
          </a>
        ) : term.explained_by === "funder" ? (
          t.sourceFunder
        ) : term.explained_by === "ai" ? (
          <Badge tone="info" icon="eye">
            {t.sourceAi}
          </Badge>
        ) : (
          t.sourceHope
        )}
      </p>
    </li>
  );
}

function QuestionList({ view, run, latest }: { view: ApplicationView; run: Run; latest: React.RefObject<ApplicationView | null> }) {
  const { h } = useHopeT();
  const t = h.apply;
  const drafting = api.running(view.answers_job);
  const status = new Map(view.checklist.items.filter((i) => i.kind === "question").map((i) => [i.key, i.status]));
  const answers = new Map(view.answers.map((a) => [a.question_key, a]));
  return (
    <Panel title={t.questionsTitle}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button className={btnPrimary} disabled={drafting || view.questions.length === 0} onClick={() => void run(() => api.draftAll(view.application_id))}>
          {t.draftAll}
        </button>
        {drafting && (
          <p role="status" className="animate-pulse text-sm">
            {t.draftingAll}
          </p>
        )}
      </div>
      <ol className="space-y-2">
        {view.questions.map((q, i) => (
          <QuestionRow key={q.key} n={i + 1} q={q} answer={answers.get(q.key)} status={status.get(q.key) ?? "missing"} view={view} run={run} latest={latest} busy={drafting} />
        ))}
      </ol>
    </Panel>
  );
}

function QuestionRow({ n, q, answer, status, view, run, latest, busy }: { n: number; q: Question; answer?: Answer; status: string; view: ApplicationView; run: Run; latest: React.RefObject<ApplicationView | null>; busy: boolean }) {
  const { h } = useHopeT();
  const t = h.apply;
  const [open, setOpen] = useState(n === 1);
  const [text, setText] = useState(answer?.text ?? "");
  const [saving, setSaving] = useState<"idle" | "saving" | "saved">("idle");
  const dirty = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [tone, icon] = Q_TONE[status] ?? (["neutral", "minus"] as [Tone, IconName]);

  useEffect(() => {
    if (!dirty.current) setText(answer?.text ?? "");
  }, [answer?.text, answer?.updated_at]);
  useEffect(() => () => clearTimeout(timer.current), []);

  function edit(value: string) {
    setText(value);
    dirty.current = true;
    setSaving("saving");
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      const ok = await run(() => api.editAnswer(view.application_id, q.key, value, latest.current?.version ?? view.version));
      dirty.current = false;
      setSaving(ok ? "saved" : "idle");
    }, 1000);
  }

  const redraft = () =>
    void run(
      () => api.draftOne(view.application_id, q.key),
      () => {
        if (window.confirm(t.confirmOverwrite)) void run(() => api.draftOne(view.application_id, q.key, true));
        return true;
      },
    );

  const count = q.limit ? api.measure(text, q.limit) : null;
  const over = q.limit && count !== null ? count - q.limit.max : 0;
  const countId = `count-${q.key}`;
  const citations = answer?.citations ?? [];
  return (
    <li className="rounded-xl border border-line" data-question={q.key}>
      <button className={`flex w-full flex-wrap items-center justify-between gap-2 p-3 text-left ${focusRing}`} aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="font-semibold">
          {n}. {q.prompt}
        </span>
        <Badge tone={tone} icon={icon}>
          {t.status[status] ?? status}
        </Badge>
      </button>
      {open && (
        <div className="space-y-2 border-t border-line p-3">
          {q.limit_text && q.limit_text !== q.prompt && <p className="text-xs text-muted">“{q.limit_text}”</p>}
          <label htmlFor={`answer-${q.key}`} className="sr-only">
            {t.answerFor(q.prompt)}
          </label>
          <textarea id={`answer-${q.key}`} rows={7} className={input} value={text} aria-describedby={countId} onChange={(e) => edit(e.target.value)} />
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
            <span id={countId} className={over > 0 ? "font-semibold text-bad" : "text-muted"}>
              {q.limit && count !== null ? t.count(count, q.limit.max, t.units[q.limit.unit] ?? q.limit.unit) : t.words(text.split(/\s+/).filter(Boolean).length)}
              {over > 0 && ` · ${t.over(over)}`}
              {answer && ` · ${t.origin[answer.origin]}`}
            </span>
            <span className="text-muted" aria-live="polite">
              {saving === "saving" ? t.saving : saving === "saved" ? t.saved : ""}
            </span>
          </div>
          {answer && answer.to_confirm.length > 0 && (
            <div className="rounded-xl bg-gold/15 px-3 py-2 text-sm">
              <p className="font-semibold">{t.toConfirm(answer.to_confirm.length)}</p>
              <ul className="list-inside list-disc">
                {answer.to_confirm.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <button className={btnSecondary} disabled={busy} onClick={redraft}>
              {t.redraft}
            </button>
            {citations.length > 0 && (
              <details className="text-sm">
                <summary className={`cursor-pointer ${focusRing}`}>{t.sources(citations.length)}</summary>
                <ul className="mt-1 space-y-1">
                  {citations.map((c, i) => (
                    <li key={i} className="text-xs">
                      <span className="font-semibold">{t.sourceKind[c.kind]}:</span> {c.text}
                      {c.url && c.url !== api.PASTED && (
                        <>
                          {" "}
                          <a href={c.url} target="_blank" rel="noreferrer" className={`text-teal-ink underline ${focusRing}`}>
                            ↗
                          </a>
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

function Uploads({ items }: { items: ChecklistItem[] }) {
  const { h } = useHopeT();
  const t = h.apply;
  if (items.length === 0) return null;
  return (
    <Panel title={t.uploadsTitle}>
      <ul className="divide-y divide-line text-sm">
        {items.map((i) => (
          <li key={i.key} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span>{i.label}</span>
            <Badge tone={i.status === "in_dossier" ? "good" : "warn"} icon={i.status === "in_dossier" ? "check" : "alert"}>
              {t.uploadStatus[i.status] ?? i.status}
            </Badge>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function TodoPanel({ view, run, latest }: { view: ApplicationView; run: Run; latest: React.RefObject<ApplicationView | null> }) {
  const { h } = useHopeT();
  const t = h.apply;
  const atRisk = view.checklist.items.filter((i) => i.kind === "prep" && i.status === "at_risk");
  const owners = ["director", "finance", "program"] as const;
  const needs = view.checklist.inputs_needed;
  return (
    <Panel title={t.todoTitle} className="h-fit">
      {atRisk.length === 0 && needs.length === 0 && <p className="text-sm">{t.nothingTodo}</p>}
      {atRisk.length > 0 && (
        <section className="mb-3">
          <h3 className="text-sm font-semibold text-bad">
            {t.atRisk} ({atRisk.length})
          </h3>
          <ul className="mt-1 space-y-1 text-sm">
            {atRisk.map((i) => (
              <li key={i.key}>
                {i.label}
                {i.detail && ` · ${i.detail}`}
                {i.owner && ` · ${t.owner[i.owner]}`}
              </li>
            ))}
          </ul>
        </section>
      )}
      {owners.map((owner) => {
        const mine = needs.filter((x) => x.owner === owner);
        if (mine.length === 0) return null;
        return (
          <section key={owner} className="mb-3">
            <h3 className="text-sm font-semibold">
              {t.owner[owner]} ({mine.length})
            </h3>
            <ul className="mt-1 space-y-2">
              {mine.map((need, i) => (
                <NeedRow key={`${need.question_key ?? ""}:${need.text}:${i}`} need={need} view={view} run={run} latest={latest} />
              ))}
            </ul>
          </section>
        );
      })}
    </Panel>
  );
}

function NeedRow({ need, view, run, latest }: { need: InputNeeded; view: ApplicationView; run: Run; latest: React.RefObject<ApplicationView | null> }) {
  const { h } = useHopeT();
  const t = h.apply;
  const [value, setValue] = useState(need.answer ?? "");
  const [saved, setSaved] = useState(false);
  const upload = need.text.startsWith("Upload:") || !!need.rule;
  const fact = need.fact ? (view.facts ?? []).find((f) => f.need === need.fact) : undefined;
  const id = `need-${need.question_key ?? "x"}-${need.text.replace(/\W+/g, "-").slice(0, 40)}`;
  const redraft = (key: string) =>
    void run(
      () => api.draftOne(view.application_id, key),
      () => {
        if (window.confirm(t.confirmOverwrite)) void run(() => api.draftOne(view.application_id, key, true));
        return true;
      },
    );
  async function save() {
    if (await run(() => api.supplyFact(view.application_id, need.text, value, latest.current?.version ?? view.version))) setSaved(true);
  }
  return (
    <li className="rounded-xl border border-line p-2 text-sm" data-need={need.text}>
      <p>
        {need.answer ? "✓ " : "○ "}
        {need.text}
      </p>
      {fact && (
        <p className="text-xs text-muted" data-fact-source={fact.shared ? "shared" : "this_grant"}>
          {fact.shared ? t.reusedFact : t.thisGrantFact}
        </p>
      )}
      {!upload && (
        <div className="mt-1 space-y-1">
          <label htmlFor={id} className="sr-only">
            {t.answerLabel(need.text)}
          </label>
          <textarea id={id} rows={2} className={input} placeholder={t.answerOnce} value={value} onChange={(e) => setValue(e.target.value)} />
          <div className="flex flex-wrap items-center gap-2">
            <button className={btnSecondary} disabled={value === (need.answer ?? "")} onClick={() => void save()}>
              {t.save}
            </button>
            {(saved || need.answer) && need.question_key && (
              <button className={`text-xs font-semibold text-teal-ink underline ${focusRing}`} onClick={() => redraft(need.question_key!)}>
                {t.redraft}
              </button>
            )}
          </div>
          {saved && (
            <AutoDismiss onDismiss={() => setSaved(false)}>
              <p role="status" className="text-xs text-good">
                {t.factSaved}
              </p>
            </AutoDismiss>
          )}
        </div>
      )}
    </li>
  );
}

function ReadyPanel({ view }: { view: ApplicationView }) {
  const { h } = useHopeT();
  const t = h.apply;
  const [copied, setCopied] = useState(false);
  const qs = view.checklist.items.filter((i) => i.kind === "question");
  const done = qs.filter((i) => i.status === "drafted" || i.status === "edited").length;
  const over = qs.filter((i) => i.status === "over_limit").length;
  const confirm = qs.filter((i) => i.status === "to_confirm").length;
  async function download() {
    const md = await api.exportMarkdown(view.application_id);
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    Object.assign(document.createElement("a"), { href: url, download: `${view.grant_id}-application.md` }).click();
    URL.revokeObjectURL(url);
  }
  return (
    <Panel title={t.readyTitle}>
      <p className="text-sm">{t.readySummary(done, qs.length, over, confirm)}</p>
      <p className="mt-1 text-sm font-semibold">{view.checklist.complete ? t.complete : t.incomplete}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className={btnSecondary} onClick={() => void download().catch(() => undefined)}>
          {t.download}
        </button>
        <button
          className={btnSecondary}
          onClick={() =>
            void api
              .exportMarkdown(view.application_id)
              .then((md) => navigator.clipboard.writeText(md))
              .then(() => setCopied(true))
              .catch(() => undefined)
          }
        >
          {copied ? `✓ ${t.copied}` : t.copyAll}
        </button>
      </div>
      <p className="mt-2 text-xs text-navy/70">{t.neverSubmits}</p>
    </Panel>
  );
}
