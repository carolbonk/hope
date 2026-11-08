"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { online } from "@/api/http";
import { invalidateSession, logout, useSession } from "@/api/session";
import { useToday } from "@/components/useToday";
import { useHopeT } from "@/lib/hope/i18n";
import { useOpportunities } from "@/lib/hope/opportunities";
import { STAGES, useHope } from "@/lib/hope/store";
import { LanguageToggle } from "@/components/LanguageToggle";

export const focusRing = "focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-gold";
export const btnPrimary = `inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-teal-ink px-5 py-2.5 font-semibold text-white hover:bg-navy disabled:cursor-not-allowed disabled:opacity-50 ${focusRing}`;
export const btnSecondary = `inline-flex min-h-11 items-center justify-center gap-2 rounded-lg glass-panel px-4 py-2 font-medium text-navy hover:border-teal-ink disabled:cursor-not-allowed disabled:opacity-50 ${focusRing}`;
export const input = `w-full rounded-lg glass-panel px-3 py-2.5 text-navy placeholder:text-muted ${focusRing}`;
export const eyebrow = "text-[11px] font-bold uppercase tracking-[0.18em] text-teal-ink";
export const display = "font-display tracking-tight text-navy";

const NAV = [
  { key: "discover", href: "/hope/discover" },
  { key: "saved", href: "/hope/saved" },
  { key: "deadlines", href: "/hope/deadlines" },
  { key: "profile", href: "/hope/profile" },
] as const;

export function Logo() {
  return (
    <Link href="/hope/discover" className={`font-display text-4xl leading-none tracking-[-0.06em] text-navy ${focusRing}`} aria-label="Hope">
      hope<span className="text-leaf" aria-hidden>✳</span>
    </Link>
  );
}

export function HopeNav() {
  const { h } = useHopeT();
  const path = usePathname();
  const { state } = useHope();
  const savedCount = Object.values(state.decisions).filter((d) => d.decision === "saved").length;
  return (
    <div className="no-print -mx-4 mb-8 glass-chrome rounded-2xl px-4">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 py-4">
        <Logo />
        <nav aria-label={h.brand} className="order-3 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto">
          {NAV.map((n) => {
            const active = path.startsWith(n.href) || (n.key === "saved" && path.startsWith("/hope/applications"));
            return (
              <Link
                key={n.key}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={`whitespace-nowrap rounded-full px-3 py-2.5 text-sm sm:px-4 ${focusRing} ${active ? "bg-navy text-white" : "text-muted hover:text-navy"}`}
              >
                {h.nav[n.key]}
                {n.key === "saved" && savedCount > 0 && <span className="ml-1 tabular-nums">({savedCount})</span>}
              </Link>
            );
          })}
        </nav>
        <LanguageToggle tone="light" />
        {online && <SessionControls />}
      </div>
      <DeadlineReminder />
    </div>
  );
}

/** Online only: the signed-in name and Sign out. Signing out never clears `hope:state:v1`. */
function SessionControls() {
  const { h } = useHopeT();
  const router = useRouter();
  const { status, me } = useSession();
  const [failed, setFailed] = useState(false);
  if (status !== "ready" || !me) return null;
  const name = me.display_name.length > 24 ? `${me.display_name.slice(0, 23)}…` : me.display_name;
  const signOut = () => {
    setFailed(false);
    logout().then(
      () => {
        invalidateSession();
        router.replace("/login");
      },
      () => setFailed(true),
    );
  };
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-3 text-sm">
        <span className="text-muted" title={me.display_name}>
          {name}
        </span>
        <button type="button" onClick={signOut} className={btnSecondary}>
          {h.session.signOut}
        </button>
      </div>
      {failed && (
        <p role="alert" className="text-xs text-bad">
          {h.session.signOutFailed}
        </p>
      )}
    </div>
  );
}

export function HopeFooter() {
  const { h } = useHopeT();
  return (
    <div className="mt-12 flex flex-wrap justify-between gap-3 border-t border-line pt-5 text-xs text-muted">
      <span>
        {h.demo} · {h.storageNote}
      </span>
      <span>{h.look.footerR}</span>
    </div>
  );
}

export function PageIntro({ kicker, title, sub, aside }: { kicker: string; title: string; sub?: string; aside?: React.ReactNode }) {
  return (
    <header className="mb-7 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <span className={eyebrow}>{kicker}</span>
        {aside}
      </div>
      <h1 className={`${display} text-[2.6rem] leading-[1.05] sm:text-5xl`}>{title}</h1>
      {sub && <p className="max-w-2xl leading-relaxed text-muted">{sub}</p>}
    </header>
  );
}

export function DemoTag() {
  const { h } = useHopeT();
  return <span className="rounded-md border border-[#d6c590] bg-[#f1ead8] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#6b5520]">{h.demo}</span>;
}

function DeadlineReminder() {
  const { h } = useHopeT();
  const today = useToday();
  const opps = useOpportunities();
  const { state } = useHope();
  if (!today) return null;
  const soon = Object.values(state.applications)
    .filter((a) => a.stage !== "ready")
    .map((a) => opps.find((o) => o.id === a.opportunityId))
    .filter((o) => o && daysUntil(o.deadline, today) <= 14);
  if (!soon.length) return null;
  return (
    <Link href="/hope/deadlines" className={`mb-3 block rounded-lg border border-gold/60 bg-[#f1ead8] px-3 py-2 text-sm text-navy ${focusRing}`}>
      <span aria-hidden className="mr-1 inline-block h-2 w-2 rounded-full bg-gold align-middle" /> {h.deadlines.soon}: {soon.map((o) => `${o!.name} (${daysUntil(o!.deadline, today)}d)`).join(" · ")}
    </Link>
  );
}

/** Renders children only in the browser, where localStorage is readable; shows a loading state otherwise. */
export function ClientOnly({ children }: { children: React.ReactNode }) {
  const today = useToday();
  const { h } = useHopeT();
  if (!today)
    return (
      <p role="status" className="animate-pulse rounded-2xl glass-panel p-6 text-muted">
        {h.loading}
      </p>
    );
  return <>{children}</>;
}

export function Panel({ title, children, className = "" }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl glass-panel p-5 sm:p-6 ${className}`}>
      {title && <h2 className="mb-3 font-display text-2xl text-navy">{title}</h2>}
      {children}
    </section>
  );
}

export function money(n: number, currency: string, locale: string) {
  return new Intl.NumberFormat(locale === "es" ? "es-US" : "en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(n);
}

export function daysUntil(iso: string, today: Date) {
  return Math.ceil((new Date(iso + "T00:00:00").getTime() - new Date(today.toDateString()).getTime()) / 86_400_000);
}

export function StageBar({ stage }: { stage: string }) {
  const { h } = useHopeT();
  const idx = STAGES.indexOf(stage as (typeof STAGES)[number]);
  return (
    <ol className="mt-3 grid grid-cols-5 gap-1" aria-label={h.stage[stage]}>
      {STAGES.map((s, i) => (
        <li key={s} aria-current={i === idx ? "step" : undefined} className="text-[10px] leading-tight sm:text-xs">
          <span className={`mb-1 block h-1.5 rounded-full ${i <= idx ? "bg-teal-ink" : "bg-line"}`} />
          <span className={i === idx ? "font-semibold text-navy" : "text-navy/60"}>{h.stage[s]}</span>
        </li>
      ))}
    </ol>
  );
}
