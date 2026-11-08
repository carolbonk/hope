"use client";

import Link from "next/link";
import { online } from "@/lib/api/http";
import { useEffect, useMemo, useState } from "react";
import { btnPrimary, btnSecondary, ClientOnly, focusRing, input, PageIntro, Panel } from "@/components/hope/ui";
import { demoOpportunities } from "@/lib/hope/demo";
import { applicability, factStatus, factValue, fieldsFor, GROUPS, isExpired, PROFILE_STEPS, pendingItems, record, reqStatus, reqValue, summary, type FieldKey, type Pending } from "@/lib/hope/dossier";
import { useHopeT } from "@/lib/hope/i18n";
import { DEMO_PROFILE, useHope } from "@/lib/hope/store";
import type { Country, Currency, FactStatus, Opportunity, OrgProfile, ReqId, RequirementRecord, ReqStatus, TriState } from "@/lib/hope/types";
import { AutoDismiss, NOTICE_MS } from "@/components/ui/AutoDismiss";

const FOCUS = ["mentoring", "youth", "family", "mental_health", "safety", "school_based", "capacity", "arts"];
const PURPOSES = ["general_operating", "program", "capacity", "capital"];
const CURRENCIES: Currency[] = ["USD", "EUR", "MXN", "COP"];
const COUNTRIES: Country[] = ["", "US", "MX", "CO", "other"];
const NUMS = ["annualBudget", "staffCount", "volunteerCount", "foundedYear"] as const;
type NumKey = (typeof NUMS)[number];
const INFO_FIELD: Record<string, FieldKey> = { need_country: "country", need_501c3: "has501c3", need_minors: "servesMinors", need_us_tax: "usTaxStatus", need_tax_status: "legalStatus", w9_fiscal_sponsor: "legalStatus" };
const today = () => new Date().toISOString().slice(0, 10);

export default function ProfilePage() {
  return (
    <ClientOnly>
      <ProfileWizard />
    </ClientOnly>
  );
}

const numText = (p: OrgProfile) => Object.fromEntries(NUMS.map((k) => [k, p[k]?.toString() ?? ""])) as Record<NumKey, string>;

/** Element id that "Resolve" focuses for a pending item. */
function targetOf(item: Pending, p: OrgProfile): { step: number; id: string } {
  if (item.kind === "field") return { step: item.step, id: `f-${item.key}` };
  if (item.problem === "needs_info") {
    const field = INFO_FIELD[applicability(item.id, p).reason];
    if (field) return { step: item.infoStep ?? 0, id: `f-${field}` };
  }
  return { step: 3, id: `req-${item.id}` };
}

function ProfileWizard() {
  const { h } = useHopeT();
  const p = h.profile;
  const { state, saveProfile } = useHope();
  const [draft, setDraft] = useState<OrgProfile>(state.profile);
  const [nums, setNums] = useState(numText(state.profile));
  const [step, setStep] = useState(Math.min(state.profile.completedSteps, PROFILE_STEPS - 1));
  const [target, setTarget] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);
  useEffect(() => {
    if (!savedFlash) return;
    const t = setTimeout(() => setSavedFlash(false), NOTICE_MS);
    return () => clearTimeout(t);
  }, [savedFlash]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => {
    if (!target) return;
    const el = document.getElementById(target);
    if (!el) return;
    for (let d = el.closest("details"); d; d = d.parentElement?.closest("details") ?? null) d.open = true;
    el.querySelectorAll("details").forEach((d) => (d.open = true));
    const focusable = el.matches("input,select,textarea,button") ? el : el.querySelector<HTMLElement>("input,select,textarea,button");
    el.scrollIntoView({ block: "center" });
    focusable?.focus();
  }, [step, target]);

  const touched = () => {
    setDirty(true);
    setSavedFlash(false);
  };
  const set = <K extends keyof OrgProfile>(k: K, v: OrgProfile[K]) => {
    setDraft((d) => ({ ...d, [k]: v }));
    touched();
  };
  const toggle = (k: "focusAreas" | "intendedUse", v: string) => set(k, draft[k].includes(v) ? draft[k].filter((x) => x !== v) : [...draft[k], v]);
  const setNum = (k: NumKey, v: string) => {
    setNums((n) => ({ ...n, [k]: v }));
    touched();
  };

  function parseNums(): Partial<OrgProfile> | string {
    if (step !== 2) return {};
    const out: Partial<Record<NumKey, number | null>> = {};
    for (const k of NUMS) {
      const raw = nums[k].replace(/[,\s$]/g, "");
      if (raw === "") out[k] = null;
      else if (k === "annualBudget") {
        if (!/^\d+(\.\d+)?$/.test(raw) || Number(raw) <= 0) return p.errBudget;
        out[k] = Number(raw);
      } else if (k === "foundedYear") {
        const y = Number(raw);
        if (!/^\d{4}$/.test(raw) || y < 1800 || y > new Date().getFullYear()) return p.errYear;
        out[k] = y;
      } else {
        if (!/^\d+$/.test(raw)) return p.errNumber;
        out[k] = Number(raw);
      }
    }
    return out;
  }

  function persist(next: OrgProfile) {
    setDraft(next);
    saveProfile(next);
    setDirty(false);
    setSavedFlash(true);
  }

  function commit(nextStep: number) {
    setError(null);
    if (step === 0 && !draft.legalName.trim()) return setError(p.errName);
    if (step === 0 && draft.contactEmail.trim() && !/^\S+@\S+\.\S+$/.test(draft.contactEmail.trim())) return setError(p.errEmail);
    if (step === 1 && !draft.mission.trim()) return setError(p.errMission);
    const parsed = parseNums();
    if (typeof parsed === "string") return setError(parsed);
    const programs = draft.programs.filter((x) => x.name.trim() || x.description.trim() || x.outcomes.trim());
    persist({ ...draft, ...parsed, programs, completedSteps: Math.max(draft.completedSteps, nextStep >= PROFILE_STEPS - 1 && step === PROFILE_STEPS - 2 ? PROFILE_STEPS : step + 1) });
    setTarget(null);
    setStep(Math.min(nextStep, PROFILE_STEPS - 1));
  }

  function fillDemo() {
    setDraft({ ...DEMO_PROFILE, reviews: draft.reviews, reviewRequest: draft.reviewRequest, completedSteps: draft.completedSteps });
    setNums(numText(DEMO_PROFILE));
    touched();
  }

  function go(next: number, id: string | null = null) {
    setError(null);
    setTarget(id);
    setStep(next);
  }

  const done = state.profile.completedSteps;
  const last = PROFILE_STEPS - 1;

  return (
    <div className="space-y-5">
      <PageIntro kicker={h.look.profileEyebrow} title={h.look.profileHeading} sub={p.intro} />
      <h2 className="sr-only">{p.title}</h2>
      <p className="rounded-xl border border-gold/40 bg-gold/10 px-3 py-2 text-sm text-navy" data-testid="not-cert">
        {p.notCert} <span className="text-muted">{p.storage(online)}</span>
      </p>
      {done > 0 && done < PROFILE_STEPS && <p className="rounded-xl bg-sage px-3 py-2 text-sm text-navy">{p.resume(done, PROFILE_STEPS)}</p>}

      <ol className="grid grid-cols-5 gap-2" aria-label={p.step(step + 1, PROFILE_STEPS)}>
        {p.steps.map((label, i) => (
          <li key={label}>
            <button
              type="button"
              onClick={() => i <= done && go(i)}
              disabled={i > done}
              aria-current={i === step ? "step" : undefined}
              aria-label={`${i + 1}. ${label}`}
              className={`h-full w-full rounded-xl px-2 py-2 text-left text-xs ${focusRing} ${i === step ? "bg-navy text-cream" : i < done ? "bg-sage text-navy" : "glass-control text-navy/60"}`}
            >
              <span className="block font-semibold">{i + 1}</span>
              <span className="hidden md:block">{label}</span>
            </button>
          </li>
        ))}
      </ol>

      <Panel>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-semibold text-teal-ink">
            {p.step(step + 1, PROFILE_STEPS)} · {p.steps[step]}
          </p>
          {step < last && (
            <button type="button" onClick={fillDemo} className={`text-sm text-navy underline ${focusRing}`}>
              {p.useDemo} <span className="rounded bg-gold/25 px-1.5 text-xs">{h.demo}</span>
            </button>
          )}
        </div>

        <form
          className="space-y-4"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            commit(step + 1);
          }}
        >
          {step === 0 && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <Text k="legalName" label={p.legalName} draft={draft} set={set} />
                <Text k="publicName" label={p.publicName} draft={draft} set={set} />
                <Field id="f-country" label={p.country}>
                  <select id="f-country" className={input} value={draft.country} onChange={(e) => set("country", e.target.value as Country)}>
                    {COUNTRIES.map((c) => (
                      <option key={c} value={c}>
                        {p.countries[c]}
                      </option>
                    ))}
                  </select>
                </Field>
                <Text k="jurisdiction" label={p.jurisdiction} hint={p.jurisdictionHint} draft={draft} set={set} />
                <Text k="website" label={p.website} type="url" placeholder="https://" draft={draft} set={set} />
                <Text k="contactName" label={p.contactName} draft={draft} set={set} />
                <Text k="contactEmail" label={p.contactEmail} type="email" draft={draft} set={set} />
                <Text k="responsibleName" label={p.responsibleName} draft={draft} set={set} />
                <Text k="responsibleRole" label={p.responsibleRole} draft={draft} set={set} />
                <Field id="f-legalStatus" label={p.legalStatus}>
                  <select id="f-legalStatus" className={input} value={draft.legalStatus} onChange={(e) => set("legalStatus", e.target.value as OrgProfile["legalStatus"])}>
                    {Object.entries(h.legal).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              {draft.country === "US" && <Tri k="has501c3" legend={p.has501c3} value={draft.has501c3} onChange={(v) => set("has501c3", v)} />}
              {draft.country !== "US" && draft.country !== "" && <Tri k="usTaxStatus" legend={p.usTaxStatus} value={draft.usTaxStatus} onChange={(v) => set("usTaxStatus", v)} />}
            </>
          )}
          {step === 1 && (
            <>
              <Field id="f-mission" label={p.mission}>
                <textarea id="f-mission" rows={3} className={input} value={draft.mission} onChange={(e) => set("mission", e.target.value)} />
              </Field>
              <Field id="f-vision" label={p.vision}>
                <textarea id="f-vision" rows={2} className={input} value={draft.vision} onChange={(e) => set("vision", e.target.value)} />
              </Field>
              <div className="grid gap-3 sm:grid-cols-2">
                <Text k="targetPopulation" label={p.targetPopulation} draft={draft} set={set} />
                <Field id="f-serviceArea" label={p.serviceArea} hint={p.serviceAreaHint}>
                  <input id="f-serviceArea" list="areas" className={input} value={draft.serviceArea} onChange={(e) => set("serviceArea", e.target.value)} />
                  <datalist id="areas">
                    <option value="Miami-Dade" />
                    <option value="Broward" />
                  </datalist>
                </Field>
              </div>
              <Tri k="servesMinors" legend={p.servesMinors} value={draft.servesMinors} onChange={(v) => set("servesMinors", v)} />
              <Checks k="focusAreas" legend={p.focusAreas} options={FOCUS} labels={h.focus} value={draft.focusAreas} onToggle={(v) => toggle("focusAreas", v)} />
              <Programs draft={draft} set={set} />
            </>
          )}
          {step === 2 && (
            <>
              <div className="grid gap-3 sm:grid-cols-[1fr_8rem_1fr]">
                <Field id="f-annualBudget" label={p.annualBudget}>
                  <input id="f-annualBudget" inputMode="decimal" className={input} value={nums.annualBudget} placeholder={h.unknown} onChange={(e) => setNum("annualBudget", e.target.value)} />
                </Field>
                <Field id="f-currency" label={p.currency}>
                  <select id="f-currency" className={input} value={draft.currency} onChange={(e) => set("currency", e.target.value as Currency)}>
                    {CURRENCIES.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </Field>
                <Text k="fiscalYear" label={p.fiscalYear} hint={p.fiscalYearHint} draft={draft} set={set} />
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                {(["staffCount", "volunteerCount", "foundedYear"] as const).map((k) => (
                  <Field key={k} id={`f-${k}`} label={p[k]}>
                    <input id={`f-${k}`} inputMode="numeric" className={input} value={nums[k]} placeholder={h.unknown} onChange={(e) => setNum(k, e.target.value)} />
                  </Field>
                ))}
              </div>
              <Field id="f-experience" label={p.experience} hint={p.experienceHint}>
                <textarea id="f-experience" rows={2} className={input} value={draft.experience} onChange={(e) => set("experience", e.target.value)} />
              </Field>
              <Field id="f-fundingNeed" label={p.fundingNeed}>
                <textarea id="f-fundingNeed" rows={3} className={input} value={draft.fundingNeed} onChange={(e) => set("fundingNeed", e.target.value)} />
              </Field>
              <Checks k="intendedUse" legend={p.intendedUse} options={PURPOSES} labels={h.purpose} value={draft.intendedUse} onToggle={(v) => toggle("intendedUse", v)} />
            </>
          )}
          {step === 3 && <Dossier draft={draft} set={set} />}
          {step === 4 && <Review profile={state.profile} onResolve={(item) => { const t = targetOf(item, state.profile); go(t.step, t.id); }} onEdit={(s) => go(s)} onSave={persist} />}

          {error && (
            <AutoDismiss key={error}>
              <p role="alert" className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-800">
                {error}
              </p>
            </AutoDismiss>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <button type="button" className={btnSecondary} disabled={step === 0} onClick={() => go(step - 1)}>
              {p.back}
            </button>
            <span role="status" className="text-sm">
              {dirty ? <span className="font-semibold text-gold">● {p.unsaved}</span> : savedFlash ? <span className="text-teal-ink">✓ {p.saved}</span> : null}
            </span>
            {step < last ? (
              <button type="submit" className={btnPrimary}>
                {step === last - 1 ? p.finish : p.next}
              </button>
            ) : (
              <Link href="/hope/discover" className={btnPrimary}>
                {p.explore}
              </Link>
            )}
          </div>
        </form>
      </Panel>
    </div>
  );
}

type SetFn = <K extends keyof OrgProfile>(k: K, v: OrgProfile[K]) => void;
type StrKey = { [K in keyof OrgProfile]: OrgProfile[K] extends string ? K : never }[keyof OrgProfile];

function Text({ k, label, hint, type = "text", placeholder, draft, set }: { k: StrKey; label: string; hint?: string; type?: string; placeholder?: string; draft: OrgProfile; set: SetFn }) {
  return (
    <Field id={`f-${k}`} label={label} hint={hint}>
      <input id={`f-${k}`} type={type} className={input} value={draft[k] as string} placeholder={placeholder} onChange={(e) => set(k, e.target.value as never)} />
    </Field>
  );
}

function Programs({ draft, set }: { draft: OrgProfile; set: SetFn }) {
  const { h } = useHopeT();
  const p = h.profile;
  const up = (i: number, patch: Partial<OrgProfile["programs"][number]>) => set("programs", draft.programs.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  return (
    <fieldset className="space-y-3">
      <legend className="mb-1 text-sm font-semibold">{p.programs}</legend>
      {draft.programs.length === 0 && <p className="text-sm text-muted">{p.noPrograms}</p>}
      {draft.programs.map((pr, i) => (
        <div key={pr.id} className="grid gap-2 rounded-xl border border-line p-3 sm:grid-cols-2">
          <Field id={`pn-${pr.id}`} label={p.programName}>
            <input id={`pn-${pr.id}`} className={input} value={pr.name} onChange={(e) => up(i, { name: e.target.value })} />
          </Field>
          <Field id={`pd-${pr.id}`} label={p.programDesc}>
            <input id={`pd-${pr.id}`} className={input} value={pr.description} onChange={(e) => up(i, { description: e.target.value })} />
          </Field>
          <Field id={`po-${pr.id}`} label={p.programOutcomes}>
            <input id={`po-${pr.id}`} className={input} value={pr.outcomes} onChange={(e) => up(i, { outcomes: e.target.value })} />
          </Field>
          <div className="flex items-end gap-2">
            <Field id={`ps-${pr.id}`} label={p.programServed}>
              <input
                id={`ps-${pr.id}`}
                inputMode="numeric"
                className={input}
                value={pr.served ?? ""}
                placeholder={h.unknown}
                onChange={(e) => up(i, { served: /^\d+$/.test(e.target.value) ? Number(e.target.value) : null })}
              />
            </Field>
            <button type="button" className={btnSecondary} onClick={() => set("programs", draft.programs.filter((_, j) => j !== i))}>
              {p.removeProgram}
            </button>
          </div>
        </div>
      ))}
      <button id="f-programs" type="button" className={btnSecondary} onClick={() => set("programs", [...draft.programs, { id: `p-${Date.now()}`, name: "", description: "", outcomes: "", served: null }])}>
        + {p.addProgram}
      </button>
    </fieldset>
  );
}

function reqLabel(h: ReturnType<typeof useHopeT>["h"], id: ReqId, p: OrgProfile) {
  return p.country && p.country !== "US" && h.profile.reqLocal[id] ? h.profile.reqLocal[id] : h.profile.req[id];
}

function Dossier({ draft, set }: { draft: OrgProfile; set: SetFn }) {
  const { h } = useHopeT();
  const p = h.profile;
  const opps = useMemo(() => demoOpportunities(new Date()), []);
  const [oppId, setOppId] = useState("");
  const opp = opps.find((o) => o.id === oppId);
  const put = (id: ReqId, patch: Partial<RequirementRecord>) => set("dossier", { ...draft.dossier, [id]: { ...record(draft, id), ...patch } });
  return (
    <div className="space-y-4">
      <p className="rounded-xl bg-sage px-3 py-2 text-sm">{p.docsIntro}</p>
      <p className="rounded-xl bg-[#f1ead8] px-3 py-2 text-sm text-[#6b5520]">{p.docsNoUpload}</p>
      <Field id="preview-opp" label={p.previewFor}>
        <select id="preview-opp" className={input} value={oppId} onChange={(e) => setOppId(e.target.value)}>
          <option value="">{p.previewNone}</option>
          {opps.map((o) => (
            <option key={o.id} value={o.id}>
              {o.funder} · {o.name}
            </option>
          ))}
        </select>
      </Field>
      {GROUPS.map((g) => {
        const answered = g.reqs.filter((id) => record(draft, id).status !== "pending").length;
        return (
          <details key={g.id} open className="rounded-xl border border-line" data-group={g.id}>
            <summary className={`flex cursor-pointer items-center justify-between gap-2 px-3 py-3 font-display text-lg ${focusRing}`}>
              {p.groups[g.id]}
              <span className="font-sans text-xs text-muted">{p.groupCount(answered, g.reqs.length)}</span>
            </summary>
            <ul className="divide-y divide-line border-t border-line">
              {g.reqs.map((id) => (
                <ReqRow key={id} id={id} draft={draft} opp={opp} put={(patch) => put(id, patch)} />
              ))}
            </ul>
          </details>
        );
      })}
    </div>
  );
}

function ReqRow({ id, draft, opp, put }: { id: ReqId; draft: OrgProfile; opp?: Opportunity; put: (patch: Partial<RequirementRecord>) => void }) {
  const { h } = useHopeT();
  const p = h.profile;
  const r = record(draft, id);
  const a = applicability(id, draft, opp);
  const [comment, setComment] = useState("");
  const label = reqLabel(h, id, draft);
  const tone = { usual: "bg-teal-ink/10 text-teal-ink", when_asked: "bg-[#e3e6ee] text-navy", auto_na: "glass-control text-muted border border-line", needs_info: "bg-[#f1ead8] text-[#6b5520]" }[a.level];
  return (
    <li id={`req-${id}`} data-req={id} data-level={a.level} className="px-3 py-3">
      <details open={r.status !== "pending" || a.level === "usual" || a.level === "needs_info"}>
        <summary className={`flex cursor-pointer flex-wrap items-center justify-between gap-2 ${focusRing}`}>
          <span className="font-semibold">{label}</span>
          <span className="flex flex-wrap gap-1">
            <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${tone}`} data-testid="level">
              {p.level[a.level]}
            </span>
            <StatusBadge status={r.status === "not_applicable" ? "not_applicable" : reqStatus(draft, id)} />
          </span>
        </summary>
        <p className="mt-1 text-xs text-muted">{p.reason[a.reason]}</p>
        <fieldset className="mt-2">
          <legend className="sr-only">{label}</legend>
          <div className="flex flex-wrap gap-2">
            {(["pending", "declared", "not_applicable"] as ReqStatus[]).map((v) => (
              <label key={v} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-full border px-4 text-sm ${r.status === v ? "border-teal-ink bg-sage" : "border-navy/20 glass-control"}`}>
                <input type="radio" name={`req-${id}`} className={focusRing} checked={r.status === v} onChange={() => put({ status: v })} />
                {p.reqStatus[v]}
              </label>
            ))}
          </div>
        </fieldset>
        {r.status === "not_applicable" && (
          <div className="mt-2 space-y-1">
            <Field id={`na-${id}`} label={p.naReason}>
              <textarea id={`na-${id}`} rows={2} className={input} value={r.naReason} onChange={(e) => put({ naReason: e.target.value })} />
            </Field>
            {!r.naReason.trim() && (
              <AutoDismiss>
                <p className="text-xs text-red-800" role="alert">
                  {p.errNaReason(label ?? "")}{" "}
                  {a.level === "auto_na" && (
                    <button type="button" className={`underline ${focusRing}`} onClick={() => put({ naReason: p.reason[a.reason] })}>
                      {p.useSuggestion}
                    </button>
                  )}
                </p>
              </AutoDismiss>
            )}
          </div>
        )}
        {r.status === "declared" && (
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            <Field id={`ev-${id}`} label={p.evidenceRef} hint={p.evidenceHint}>
              <input id={`ev-${id}`} className={input} value={r.evidenceRef} onChange={(e) => put({ evidenceRef: e.target.value })} />
            </Field>
            <Field id={`pe-${id}`} label={p.period}>
              <input id={`pe-${id}`} className={input} value={r.period} onChange={(e) => put({ period: e.target.value })} />
            </Field>
            <Field id={`ex-${id}`} label={p.expires}>
              <input id={`ex-${id}`} type="date" className={input} value={r.expires} onChange={(e) => put({ expires: e.target.value })} />
            </Field>
            {isExpired(r) && <p className="text-xs text-red-800 sm:col-span-3">{p.expired}</p>}
          </div>
        )}
        <div className="mt-3 rounded-lg bg-cream p-2">
          <p className="text-xs font-semibold">{p.comments}</p>
          {r.comments.length === 0 ? (
            <p className="text-xs text-muted">{p.commentsNone}</p>
          ) : (
            <ul className="text-xs">
              {r.comments.map((c) => (
                <li key={c.id}>
                  <span className="font-semibold">{c.by}</span> · {c.at}: {c.text}
                </li>
              ))}
            </ul>
          )}
          <div className="mt-1 flex gap-2">
            <label htmlFor={`cm-${id}`} className="sr-only">
              {p.comments}
            </label>
            <input id={`cm-${id}`} className={`${input} py-1.5 text-sm`} value={comment} onChange={(e) => setComment(e.target.value)} />
            <button
              type="button"
              className={btnSecondary}
              disabled={!comment.trim()}
              onClick={() => {
                put({ comments: [...r.comments, { id: `c-${Date.now()}`, by: p.commentBy, at: today(), text: comment.trim() }] });
                setComment("");
              }}
            >
              {p.addComment}
            </button>
          </div>
        </div>
      </details>
    </li>
  );
}

function StatusBadge({ status }: { status: FactStatus | "not_applicable" }) {
  const { h } = useHopeT();
  const tone = { pending: "bg-[#f1ead8] text-[#6b5520]", declared: "bg-[#e3e6ee] text-navy", reviewed: "bg-sage text-sage-ink", not_applicable: "glass-control text-muted border border-line" }[status];
  const icon = { pending: "○", declared: "◐", reviewed: "◑", not_applicable: "–" }[status];
  return (
    <span data-status={status} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${tone}`} title={h.profile.statusHelp[status]}>
      <span aria-hidden>{icon}</span>
      {h.profile.status[status]}
    </span>
  );
}

function StateCard({ title, ok, lines, testid }: { title: string; ok: boolean | null; lines: string[]; testid: string }) {
  const { h } = useHopeT();
  return (
    <div className="rounded-xl glass-panel p-3" data-testid={testid}>
      <p className="text-xs font-bold uppercase tracking-wider text-teal-ink">{title}</p>
      {ok !== null && <p className={`font-display text-xl ${ok ? "text-teal-ink" : "text-[#6b5520]"}`}>{ok ? h.profile.yes : h.profile.notYet}</p>}
      {lines.map((l) => (
        <p key={l} className="text-xs text-muted">
          {l}
        </p>
      ))}
    </div>
  );
}

function Review({ profile, onResolve, onEdit, onSave }: { profile: OrgProfile; onResolve: (i: Pending) => void; onEdit: (step: number) => void; onSave: (p: OrgProfile) => void }) {
  const { h, locale } = useHopeT();
  const p = h.profile;
  const [open, setOpen] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [by, setBy] = useState("");
  const [err, setErr] = useState(false);
  const pend = pendingItems(profile);
  const s = summary(profile);

  const itemLabel = (i: Pending) => (i.kind === "field" ? p.pendingField(p.fact[i.key] ?? i.key) : p.pendingReq[i.problem](reqLabel(h, i.id, profile) ?? i.id));
  const valueOf = (key: string) => (key.startsWith("req:") ? reqValue(record(profile, key.slice(4) as ReqId)) : factValue(profile, key as FieldKey));

  function saveReview(key: string) {
    if (!note.trim()) return setErr(true);
    const rv = { by: by.trim() || p.reviewDefaultBy, at: today(), note: note.trim(), value: valueOf(key), simulated: true as const };
    onSave({ ...profile, reviews: { ...profile.reviews, [key]: rv } });
    setOpen(null);
  }
  function removeReview(key: string) {
    const reviews = { ...profile.reviews };
    delete reviews[key];
    onSave({ ...profile, reviews });
  }

  function Row({ k, label, status, step }: { k: string; label: string; status: FactStatus | "not_applicable"; step: number }) {
    const rv = profile.reviews[k];
    return (
      <li className="space-y-2 px-3 py-2" data-fact={k}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm">{label}</span>
          <span className="flex items-center gap-2">
            <StatusBadge status={status} />
            <button type="button" className={`text-xs text-teal-ink underline ${focusRing}`} onClick={() => onEdit(step)}>
              {p.edit}
            </button>
          </span>
        </div>
        {status === "reviewed" && rv && (
          <p className="text-xs text-muted">
            {p.reviewedBy(rv.by, rv.at, rv.note)} ·{" "}
            <button type="button" className={`underline ${focusRing}`} onClick={() => removeReview(k)}>
              {p.unreview}
            </button>
          </p>
        )}
        {(status === "declared" || status === "not_applicable") && rv && rv.value !== valueOf(k) && <p className="text-xs text-[#6b5520]">{p.changed}</p>}
        {(status === "declared" || (status === "not_applicable" && k.startsWith("req:"))) && open !== k && (
          <button
            type="button"
            className={`text-xs text-teal-ink underline ${focusRing}`}
            onClick={() => {
              setOpen(k);
              setNote("");
              setBy("");
              setErr(false);
            }}
          >
            {p.markReviewed}
          </button>
        )}
        {open === k && (
          <div className="grid gap-2 rounded-lg bg-cream p-3 sm:grid-cols-2">
            <Field id={`rn-${k}`} label={p.reviewNote}>
              <input id={`rn-${k}`} className={input} value={note} onChange={(e) => setNote(e.target.value)} />
            </Field>
            <Field id={`rb-${k}`} label={p.reviewerName}>
              <input id={`rb-${k}`} className={input} value={by} placeholder={p.reviewDefaultBy} onChange={(e) => setBy(e.target.value)} />
            </Field>
            {err && (
              <AutoDismiss className="sm:col-span-2">
                <p role="alert" className="text-sm text-red-800 sm:col-span-2">
                  {p.reviewNeedNote}
                </p>
              </AutoDismiss>
            )}
            <div className="flex gap-2 sm:col-span-2">
              <button type="button" className={btnPrimary} onClick={() => saveReview(k)}>
                {p.reviewSave}
              </button>
              <button type="button" className={btnSecondary} onClick={() => setOpen(null)}>
                {p.reviewCancel}
              </button>
            </div>
          </div>
        )}
      </li>
    );
  }

  return (
    <div className="space-y-5">
      <p className="text-sm">{p.reviewIntro}</p>

      <section aria-labelledby="pending-h" className="rounded-xl border-2 border-gold/50 glass-control p-3" data-testid="pending">
        <h3 id="pending-h" className="font-display text-xl">
          {p.pendingTitle} <span className="text-base text-muted">({pend.length})</span>
        </h3>
        {pend.length === 0 ? (
          <p className="mt-1 text-sm text-teal-ink">✓ {p.nonePending}</p>
        ) : (
          <ul className="mt-2 divide-y divide-line">
            {pend.map((i) => {
              const key = i.kind === "field" ? i.key : `req-${i.id}`;
              return (
                <li key={key} className="flex flex-wrap items-center justify-between gap-2 py-2" data-pending={key}>
                  <span className="text-sm">{itemLabel(i)}</span>
                  <button type="button" className={btnSecondary} onClick={() => onResolve(i)}>
                    {p.resolve}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <div className="mt-3 space-y-2 border-t border-line pt-3">
          <button
            type="button"
            className={btnPrimary}
            onClick={() => onSave({ ...profile, reviewRequest: { at: new Date().toISOString(), delivery: "local_only" } })}
          >
            {p.requestReview}
          </button>
          {profile.reviewRequest ? (
            <AutoDismiss key={profile.reviewRequest.at}>
              <p role="status" className="rounded-lg bg-[#f1ead8] px-3 py-2 text-sm text-[#6b5520]" data-testid="review-request">
                {p.requestRecorded(new Date(profile.reviewRequest.at).toLocaleString(locale))}
              </p>
            </AutoDismiss>
          ) : (
            <p className="text-xs text-muted">{p.requestHelp}</p>
          )}
          <p className="text-sm">
            <Link href="/hope/discover" className={`font-semibold text-teal-ink underline ${focusRing}`}>
              {p.explore} →
            </Link>{" "}
            <span className="text-muted">{p.exploreNote}</span>
          </p>
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-3">
        <StateCard testid="state-profile" title={p.stateProfile} ok={s.profile.complete} lines={[p.stateProfileVal(s.profile.filled, s.profile.total), p.stateDossierVal(s.dossier.answered, s.dossier.total)]} />
        <StateCard testid="state-docs" title={p.stateDocs} ok={false} lines={[p.stateDocsVal(s.review.reviewed, s.review.total), p.stateDocsNone]} />
        <StateCard testid="state-elig" title={p.stateElig} ok={null} lines={[p.stateEligVal]} />
      </div>
      <p className="rounded-xl bg-[#f1ead8] px-3 py-2 text-sm text-[#6b5520]">{h.app.simulated}</p>

      <section className="space-y-2">
        <h3 className="font-display text-xl">{p.detailTitle}</h3>
        {p.steps.slice(0, 3).map((stepLabel, si) => (
          <details key={stepLabel} className="rounded-xl border border-line">
            <summary className={`cursor-pointer px-3 py-2 font-display text-lg ${focusRing}`}>{stepLabel}</summary>
            <ul className="divide-y divide-line border-t border-line">
              {fieldsFor(profile)
                .filter((f) => f.step === si)
                .map((f) => (
                  <Row key={f.key} k={f.key} label={p.fact[f.key] ?? f.key} status={factStatus(profile, f.key)} step={si} />
                ))}
            </ul>
          </details>
        ))}
        {GROUPS.map((g) => (
          <details key={g.id} className="rounded-xl border border-line">
            <summary className={`cursor-pointer px-3 py-2 font-display text-lg ${focusRing}`}>
              {p.steps[3]} · {p.groups[g.id]}
            </summary>
            <ul className="divide-y divide-line border-t border-line">
              {g.reqs.map((id) => {
                const r = record(profile, id);
                const a = applicability(id, profile);
                const st = r.status === "not_applicable" ? "not_applicable" : a.level === "auto_na" && r.status === "pending" ? "not_applicable" : reqStatus(profile, id);
                return <Row key={id} k={`req:${id}`} label={`${reqLabel(h, id, profile)} — ${p.level[a.level]}`} status={st} step={3} />;
              })}
            </ul>
          </details>
        ))}
      </section>
    </div>
  );
}

function Tri({ k, legend, value, onChange }: { k: string; legend: string; value: TriState; onChange: (v: TriState) => void }) {
  const { h } = useHopeT();
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-semibold">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {(["yes", "no", "unknown"] as TriState[]).map((v, i) => (
          <label key={v} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-full border px-4 ${value === v ? "border-teal-ink bg-sage" : "border-navy/20 glass-control"}`}>
            <input id={i === 0 ? `f-${k}` : undefined} type="radio" name={k} className={focusRing} checked={value === v} onChange={() => onChange(v)} />
            {h[v]}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function Field({ id, label, hint, children }: { id: string; label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="w-full space-y-1">
      <label htmlFor={id} className="block text-sm font-semibold">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}

function Checks({ k, legend, options, labels, value, onToggle }: { k: string; legend: string; options: string[]; labels: Record<string, string>; value: string[]; onToggle: (v: string) => void }) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-semibold">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((o, i) => (
          <label key={o} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-full border px-4 text-sm ${value.includes(o) ? "border-teal-ink bg-sage" : "border-navy/20 glass-control"}`}>
            <input id={i === 0 ? `f-${k}` : undefined} type="checkbox" className={focusRing} checked={value.includes(o)} onChange={() => onToggle(o)} />
            {labels[o]}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
