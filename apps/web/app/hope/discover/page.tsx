"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { ClientOnly, DemoTag, PageIntro, btnPrimary, btnSecondary, daysUntil, display, eyebrow, focusRing, input, money } from "@/components/hope/ui";
import { DiscoveryPanel } from "@/components/hope/discovery/DiscoveryPanel";
import { useToday } from "@/components/useToday";
import { useHopeT } from "@/lib/hope/i18n";
import { useOpportunities } from "@/lib/hope/opportunities";
import { pendingItems } from "@/lib/hope/dossier";
import { eligibility, matchReasons, PROFILE_STEPS, requirementStatus, useHope } from "@/lib/hope/store";
import type { Opportunity } from "@/lib/hope/types";
import { NOTICE_MS } from "@/components/ui/AutoDismiss";

type Filters = { geo: string; amount: string; type: string; focus: string; deadline: string; purpose: string };
const NO_FILTERS: Filters = { geo: "", amount: "", type: "", focus: "", deadline: "", purpose: "" };

export default function DiscoverPage() {
  return (
    <ClientOnly>
      <Deck />
    </ClientOnly>
  );
}

function Deck() {
  const { h } = useHopeT();
  const d = h.discover;
  const today = useToday()!;
  const all = useOpportunities();
  const { state, decide, undo } = useHope();
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [toast, setToast] = useState<{ text: string } | null>(null);
  const [details, setDetails] = useState<Opportunity | null>(null);
  const profile = state.profile;

  const matching = useMemo(
    () =>
      all
        .filter((o) => {
          const f = filters;
          if (f.geo && !o.geography.includes(f.geo)) return false;
          if (f.amount === "lt25" && o.amountMax >= 25000) return false;
          if (f.amount === "25to75" && (o.amountMax < 25000 || o.amountMin > 75000)) return false;
          if (f.amount === "gt75" && o.amountMax <= 75000) return false;
          if (f.type && o.fundingType !== f.type) return false;
          if (f.focus && !o.focusAreas.includes(f.focus)) return false;
          if (f.purpose && o.purpose !== f.purpose) return false;
          if (f.deadline && daysUntil(o.deadline, today) > Number(f.deadline.slice(1))) return false;
          return true;
        })
        .sort((a, b) => matchReasons(b, profile).score - matchReasons(a, profile).score || a.deadline.localeCompare(b.deadline)),
    [all, filters, profile, today],
  );
  const deck = matching.filter((o) => !state.decisions[o.id]);
  const top = deck[0];

  const act = (kind: "saved" | "passed") => {
    if (!top) return;
    decide(top, kind);
    setToast({ text: kind === "saved" ? d.savedToast : d.passedToast });
  };
  const doUndo = () => {
    if (!state.history.length) return;
    undo();
    setToast({ text: d.undone });
  };

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), NOTICE_MS);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (details || (e.target as HTMLElement).closest("input,select,textarea")) return;
      if (e.key === "ArrowLeft") act("passed");
      else if (e.key === "ArrowRight") act("saved");
      else if (e.key === "ArrowUp" && top) {
        e.preventDefault();
        setDetails(top);
      } else if (e.key.toLowerCase() === "u") doUndo();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const geos = [...new Set(all.flatMap((o) => o.geography))];
  const focuses = [...new Set(all.flatMap((o) => o.focusAreas))];
  const active = Object.values(filters).some(Boolean);
  const L = h.look;
  const filterFields = (prefix: string) => (
    <>
      <Select id={`${prefix}-geo`} label={d.geography} value={filters.geo} onChange={(v) => setFilters({ ...filters, geo: v })} any={d.any} options={geos.map((g) => [g, g])} />
      <Select id={`${prefix}-amt`} label={d.amount} value={filters.amount} onChange={(v) => setFilters({ ...filters, amount: v })} any={d.any} options={Object.entries(d.amounts)} />
      <Select id={`${prefix}-type`} label={d.fundingType} value={filters.type} onChange={(v) => setFilters({ ...filters, type: v })} any={d.any} options={Object.entries(h.type)} />
      <Select id={`${prefix}-focus`} label={d.focus} value={filters.focus} onChange={(v) => setFilters({ ...filters, focus: v })} any={d.any} options={focuses.map((f) => [f, h.focus[f] ?? f])} />
      <Select id={`${prefix}-dl`} label={d.deadline} value={filters.deadline} onChange={(v) => setFilters({ ...filters, deadline: v })} any={d.any} options={Object.entries(d.deadlines)} />
      <Select id={`${prefix}-purpose`} label={d.purposeL} value={filters.purpose} onChange={(v) => setFilters({ ...filters, purpose: v })} any={d.any} options={Object.entries(h.purpose)} />
      {active && (
        <button type="button" className={`text-left text-sm text-teal-ink underline ${focusRing}`} onClick={() => setFilters(NO_FILTERS)}>
          {d.clear}
        </button>
      )}
    </>
  );

  return (
    <div className="lg:grid lg:grid-cols-[13.5rem_1fr] lg:gap-10">
      <aside className="mb-6 space-y-6 lg:mb-0 lg:border-r lg:border-line lg:pr-7">
        <div className="hidden space-y-2 lg:block">
          <p className={eyebrow}>{L.yourOrg}</p>
          <p className={`${display} text-2xl leading-tight`}>{profile.legalName || (profile.mission ? (profile.mission.split(/[.(]/)[0] ?? "").trim() : L.orgName)}</p>
          <p className="text-xs leading-relaxed text-muted">
            {[profile.serviceArea, profile.focusAreas.slice(0, 3).map((f) => h.focus[f] ?? f).join(", ")].filter(Boolean).join(" · ") || L.noProfile}
          </p>
        </div>
        <Link href="/hope/profile" className={`${btnSecondary} w-full justify-between`}>
          {L.editProfile} <span aria-hidden>↗</span>
        </Link>
        <DiscoveryPanel />
        <div className="hidden space-y-4 lg:grid">{filterFields("fd")}</div>
        <details className="rounded-xl glass-panel p-4 lg:hidden">
          <summary className={`cursor-pointer font-semibold ${focusRing}`}>
            {d.filters} {active && <span className="ml-1 rounded-full bg-teal-ink px-2 text-xs text-white">●</span>}
          </summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">{filterFields("fm")}</div>
        </details>
      </aside>

      <div>
        <PageIntro kicker={L.eyebrow} title={L.heading} sub={L.sub} aside={<DemoTag />} />

        {profile.completedSteps < PROFILE_STEPS && (
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gold/50 bg-[#f1ead8] p-4">
            <p className="text-sm">{d.needProfile}</p>
            <Link href={profile.completedSteps === 0 ? "/onboarding" : "/hope/profile"} className={btnSecondary}>
              {d.goProfile}
            </Link>
          </div>
        )}
        {profile.completedSteps >= PROFILE_STEPS && pendingItems(profile).length > 0 && (
          <p className="mb-6 rounded-xl glass-panel p-3 text-sm" data-testid="pending-note">
            {d.pendingNote(pendingItems(profile).length)}{" "}
            <Link href="/hope/profile" className={`font-semibold text-teal-ink underline ${focusRing}`}>
              {d.goProfile}
            </Link>
          </p>
        )}

        <p role="status" aria-live="polite" className="mb-2 min-h-5 text-center text-sm font-medium text-teal-ink">
          {toast?.text}
        </p>

        {matching.length === 0 ? (
          <EmptyState title={d.empty} action={<button className={btnSecondary} onClick={() => setFilters(NO_FILTERS)}>{d.clear}</button>} />
        ) : !top ? (
          <EmptyState
            title={L.endTitle}
            hint={`${d.end} ${d.endHint}`}
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Link href="/hope/saved" className={btnPrimary}>
                  {d.seeSaved}
                </Link>
                <button className={btnSecondary} onClick={doUndo} disabled={!state.history.length}>
                  ↶ {d.undo}
                </button>
              </div>
            }
          />
        ) : (
          <div className="xl:grid xl:grid-cols-[minmax(0,34rem)_15rem] xl:items-center xl:justify-center xl:gap-9">
            <div className="mx-auto w-full max-w-[34rem]">
              <SwipeCard key={top.id} opp={top} onSwipe={act}>
                <CardBody opp={top} onDetails={() => setDetails(top)} />
              </SwipeCard>
              <div className="mt-6 flex items-end justify-center gap-5 sm:gap-6" role="group" aria-label={d.keys}>
                <RoundButton label={d.undo} onClick={doUndo} disabled={!state.history.length} size="sm">
                  ↶
                </RoundButton>
                <RoundButton label={d.pass} onClick={() => act("passed")}>
                  ✕
                </RoundButton>
                <RoundButton label={d.details} onClick={() => setDetails(top)}>
                  i
                </RoundButton>
                <RoundButton label={d.save} onClick={() => act("saved")} size="lg">
                  ♥
                </RoundButton>
              </div>
              <p className="mt-5 text-center text-xs text-muted">{L.left(deck.length)}</p>
              <p className="mt-1 hidden text-center text-xs text-muted sm:block">{d.keys}</p>
            </div>
            <section className="mt-10 hidden border-l border-line pl-6 xl:mt-0 xl:block">
              <p className={eyebrow}>{L.matchEyebrow}</p>
              <h2 className={`${display} mt-2 text-[1.7rem] leading-tight`}>{L.matchTitle}</h2>
              <p className="mt-3 text-sm leading-relaxed text-muted">{L.matchBody}</p>
              <ol className="mt-5 space-y-3 text-sm">
                {L.steps.map((step, i) => (
                  <li key={step} className="flex items-center gap-3">
                    <span className="grid h-6 w-6 place-items-center rounded-full border border-line text-xs text-teal-ink">{i + 1}</span>
                    {step}
                  </li>
                ))}
              </ol>
              <p className="mt-5 text-sm leading-relaxed text-muted">{L.notApproval}</p>
            </section>
          </div>
        )}
      </div>

      {details && <Details opp={details} onClose={() => setDetails(null)} />}
    </div>
  );
}

const ART: Record<string, { symbol: string; bg: string }> = {
  mental_health: { symbol: "≈", bg: "#d9e8e6" },
  health: { symbol: "≈", bg: "#d9e8e6" },
  education: { symbol: "⌁", bg: "#eee2c8" },
  school_based: { symbol: "⌁", bg: "#eee2c8" },
  arts: { symbol: "✺", bg: "#efe0d6" },
  capacity: { symbol: "◇", bg: "#e3e6ee" },
  data: { symbol: "◇", bg: "#e3e6ee" },
};

function CardBody({ opp, onDetails }: { opp: Opportunity; onDetails: () => void }) {
  const { h, locale } = useHopeT();
  const d = h.discover;
  const L = h.look;
  const today = useToday()!;
  const { state } = useHope();
  const profile = state.profile;
  const { reasons } = matchReasons(opp, profile);
  const elig = eligibility(opp, profile, state.applications[`app:${profile.id}:${opp.id}`]);
  const days = daysUntil(opp.deadline, today);
  const tone = elig === "meets" ? "bg-[#e8f1ea] text-sage-ink" : elig === "needs_review" ? "bg-[#f1ead8] text-[#6b5520]" : "bg-red-100 text-red-800";
  const art = ART[opp.focusAreas.find((f) => ART[f]) ?? ""] ?? { symbol: "✳", bg: "#dce6d8" };
  return (
    <>
      <div className="relative flex h-36 items-center justify-center overflow-hidden sm:h-44" style={{ background: art.bg }} aria-hidden>
        <span className="absolute left-[22%] top-6 h-64 w-64 rounded-full border border-[#94ad97]/45" />
        <span className="absolute left-[14%] -top-4 h-80 w-80 rounded-full border border-[#94ad97]/45" />
        <span className="absolute left-5 top-4 text-[10px] uppercase tracking-[0.2em] text-[#3f6450]">{h.purpose[opp.purpose]}</span>
        <span className="relative font-display text-7xl leading-none text-[#476f57] sm:text-8xl">{art.symbol}</span>
      </div>
      {opp.source.kind === "demo" && (
        <span className="absolute right-4 top-4 rounded-full glass-control/90 px-2.5 py-1.5 text-[11px] text-[#3f6450]">
          {L.fictional} · {h.demo}
        </span>
      )}
      <div className="space-y-4 p-6 sm:p-7">
        <div>
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted">{opp.funder}</p>
          <h2 className={`${display} mt-2 text-3xl leading-[1.12] sm:text-[2.1rem]`}>{opp.name}</h2>
        </div>
        <div className="flex justify-between gap-4 border-y border-line py-4">
          <div>
            <p className="text-lg font-medium">
              {money(opp.amountMin, opp.currency, locale)}–{money(opp.amountMax, opp.currency, locale)}
            </p>
            <p className="mt-1 text-[11px] text-muted">
              {opp.currency} · {L.range}
            </p>
          </div>
          <div className="text-right">
            <p className={`text-lg font-medium ${days <= 14 ? "text-[#8a5a00]" : ""}`}>{L.days(days)}</p>
            <p className="mt-1 text-[11px] text-muted">{d.due(opp.deadline, days)}</p>
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <Info label={d.geoL} value={opp.geography.join(", ")} />
          <Info label={d.fundingType} value={h.type[opp.fundingType] ?? opp.fundingType} />
          <Info label={d.focus} value={opp.focusAreas.map((f) => h.focus[f] ?? f).join(", ")} />
          <Info label={d.purposeL} value={h.purpose[opp.purpose] ?? opp.purpose} />
        </dl>
        <div className="rounded-lg bg-sage p-4 text-sm text-sage-ink">
          <p className="text-xs font-bold">↗ {L.whyFit}</p>
          <p className="sr-only">{d.why}</p>
          {reasons.length ? (
            <ul className="mt-1.5 list-inside list-disc space-y-0.5 leading-relaxed">
              {reasons.map((r) => (
                <li key={r.key}>{d.reason[r.key](r.key === "purpose" ? (h.purpose[r.detail] ?? r.detail) : r.key === "focus" ? r.detail.split(", ").map((f) => h.focus[f] ?? f).join(", ") : r.detail)}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-1">{d.noReasons}</p>
          )}
          <p className={`mt-3 inline-block rounded-full px-2.5 py-1 text-xs font-semibold ${tone}`}>{d.elig[elig]}</p>
        </div>
        <p className="text-xs text-muted">
          {d.source}: {opp.source.kind === "demo" ? d.demoSource : <a className="underline" href={opp.source.url}>{opp.source.url}</a>}
          {opp.source.verifiedAt && ` · ${d.verified(opp.source.verifiedAt)}`}
        </p>
        <button type="button" onClick={onDetails} className={`text-sm text-teal-ink underline-offset-2 hover:underline ${focusRing}`}>
          {L.detailsLink} ↗
        </button>
      </div>
    </>
  );
}

function RoundButton({ label, onClick, disabled, size = "md", children }: { label: string; onClick: () => void; disabled?: boolean; size?: "sm" | "md" | "lg"; children: React.ReactNode }) {
  const dims = size === "lg" ? "h-[4.25rem] w-[4.25rem] text-2xl bg-teal-ink text-white border-teal-ink shadow-[0_7px_16px_#087e7d40]" : size === "sm" ? "h-11 w-11 text-lg glass-control text-muted border-line" : "h-14 w-14 text-xl glass-control text-muted border-line";
  return (
    <div className="flex flex-col items-center gap-2">
      <button type="button" aria-label={label} onClick={onClick} disabled={disabled} className={`grid place-items-center rounded-full border ${dims} hover:border-navy disabled:cursor-not-allowed disabled:opacity-40 ${focusRing}`}>
        <span aria-hidden>{children}</span>
      </button>
      <span aria-hidden className="text-[11px] text-muted">
        {label}
      </span>
    </div>
  );
}

function Details({ opp, onClose }: { opp: Opportunity; onClose: () => void }) {
  const { h } = useHopeT();
  const d = h.discover;
  const { state } = useHope();
  const profile = state.profile;
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby="opp-title" className="m-auto w-[min(36rem,92vw)] rounded-2xl bg-cream p-0 backdrop:bg-navy/50">
      <div className="space-y-4 p-6 text-navy sm:p-8">
        <div className="flex items-start justify-between gap-2">
          <h2 id="opp-title" className="font-display text-3xl">
            {opp.name}
          </h2>
          <button className={btnSecondary} onClick={() => ref.current?.close()}>
            {d.close}
          </button>
        </div>
        <p className="text-sm text-navy/70">{opp.funder}</p>
        <section>
          <h3 className="font-semibold">{d.requirements}</h3>
          <ul className="mt-1 space-y-1 text-sm">
            {opp.requirements.length === 0 && <li>—</li>}
            {opp.requirements.map((r) => {
              const s = requirementStatus(r, profile);
              return (
                <li key={r.id} className="flex justify-between gap-2 border-b border-line py-1">
                  <span>{r.label}</span>
                  <span className="font-semibold">{h[s]}</span>
                </li>
              );
            })}
          </ul>
        </section>
        <section>
          <h3 className="font-semibold">{d.funderContext}</h3>
          {opp.funderContext && (opp.funderContext.previousGrantees.length || opp.funderContext.awardHistory.length) ? (
            <ul className="list-inside list-disc text-sm">
              {[...opp.funderContext.previousGrantees, ...opp.funderContext.awardHistory].map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-navy/70">{d.funderEmpty}</p>
          )}
        </section>
        <p className="text-xs text-navy/70">
          {d.source}: {opp.source.kind === "demo" ? d.demoSource : opp.source.url}
        </p>
      </div>
    </dialog>
  );
}

function SwipeCard({ onSwipe, children }: { opp: Opportunity; onSwipe: (k: "saved" | "passed") => void; children: React.ReactNode }) {
  const [dx, setDx] = useState(0);
  const [dragging, setDragging] = useState(false);
  const start = useRef<number | null>(null);
  const moved = useRef(0);
  return (
    <article
      className="relative touch-pan-y select-none overflow-hidden rounded-[1.25rem] border border-[#e2e4dc] glass-control text-navy shadow-[0_15px_45px_#0b22390d] transition-transform"
      style={{ transform: `translateX(${dx}px) rotate(${dx / 25}deg)`, transitionDuration: dragging ? "0ms" : "200ms" }}
      onPointerDown={(e) => {
        if ((e.target as HTMLElement).closest("a,button")) return;
        start.current = e.clientX;
        setDragging(true);
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (start.current === null) return;
        moved.current = e.clientX - start.current;
        setDx(moved.current);
      }}
      onPointerUp={() => {
        const distance = moved.current;
        start.current = null;
        moved.current = 0;
        setDragging(false);
        setDx(0);
        if (distance > 110) onSwipe("saved");
        else if (distance < -110) onSwipe("passed");
      }}
      onPointerCancel={() => {
        start.current = null;
        setDragging(false);
        setDx(0);
      }}
    >
      {dx !== 0 && (
        <p aria-hidden className={`absolute left-1/2 top-14 z-10 -translate-x-1/2 rounded-full glass-control px-4 py-1 text-lg font-bold shadow ${dx > 0 ? "text-teal-ink" : "text-red-700"}`}>
          {dx > 0 ? "♥" : "✕"}
        </p>
      )}
      {children}
    </article>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] text-muted">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}

function Select({ id, label, value, onChange, any, options }: { id: string; label: string; value: string; onChange: (v: string) => void; any: string; options: [string, string][] }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-xs font-semibold">
        {label}
      </label>
      <select id={id} className={input} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{any}</option>
        {options.map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </select>
    </div>
  );
}

function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="space-y-3 rounded-[1.1rem] border border-dashed border-[#bac7bb] px-6 py-14 text-center">
      <p aria-hidden className="text-4xl text-teal-ink">✳</p>
      <p className="font-display text-3xl">{title}</p>
      {hint && <p className="mx-auto max-w-md text-sm text-muted">{hint}</p>}
      {action}
    </div>
  );
}
