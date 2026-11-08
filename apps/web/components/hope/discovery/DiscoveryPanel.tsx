"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ProblemError, online as syncOnline } from "@/api/http";
import { btnPrimary, btnSecondary, eyebrow, focusRing, input } from "@/components/hope/ui";
import { AutoDismiss } from "@/components/ui/AutoDismiss";
import { useHopeT, type HopeDict } from "@/lib/hope/i18n";
import { useHope } from "@/lib/hope/store";
import { needsCheck } from "@/lib/hope/sync/opportunities";
import { DiscoveryProblem, httpDiscoveryApi } from "./api";
import type { DiscoveryApi, DiscoveryJobView, DiscoveryRequest, DiscoveryRunSummary } from "./types";

type Phase = "idle" | "starting" | "running" | "done" | "failed" | "lost" | "gone";
type Copy = HopeDict["discovery"];

export const POLL_MS = 1500;
export const HIDDEN_POLL_MS = 5000;
const ANNOUNCE_MS = 5000;
const MAX_NETWORK_ERRORS = 3;

/** SC24 "Refine": trimmed, 2-40 chars, deduped case-insensitively, at most 5; empty location → null. */
export function parseRequest(keywords: string, location: string, d: Copy): { body: DiscoveryRequest } | { error: string } {
  const seen = new Set<string>();
  const kept: string[] = [];
  for (const raw of keywords.split(",")) {
    const k = raw.trim().replace(/\s+/g, " ");
    if (k.length < 2 || k.length > 40 || seen.has(k.toLowerCase())) continue;
    seen.add(k.toLowerCase());
    kept.push(k);
  }
  if (kept.length > 5) return { error: d.tooManyKeywords };
  const loc = location.trim().replace(/\s+/g, " ");
  if (loc && (loc.length < 2 || loc.length > 80)) return { error: d.badLocation };
  return { body: { focus_keywords: kept, location: loc || null } };
}

export function progressOf(v: DiscoveryJobView): number | null {
  if (v.job.status === "done") return 100;
  const p = v.job.progress;
  if (p.queries_total <= 0) return null;
  const pages = Math.min(v.counts.urls_found, v.limits.max_pages);
  const pct = 5 + (25 * p.queries_done) / p.queries_total + (pages ? 70 * Math.min(1, p.pages_read / pages) : 0);
  return Math.min(99, Math.floor(pct));
}

function relative(iso: string, locale: string, now: number): string {
  const secs = (Date.parse(iso) - now) / 1000;
  const fmt = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (Math.abs(secs) < 3600) return fmt.format(Math.round(secs / 60), "minute");
  if (Math.abs(secs) < 86_400) return fmt.format(Math.round(secs / 3600), "hour");
  return fmt.format(Math.round(secs / 86_400), "day");
}

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const ellipsis = (t: string, n = 60) => (t.length > n ? `${t.slice(0, n - 1)}…` : t);
const host = (url: string) => {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
};
const ICON: Record<string, string> = { skip: "⊘", warning: "⚠", error: "✕" };

const reloadPage = () => window.location.reload();

export function DiscoveryPanel({
  api = httpDiscoveryApi,
  online = syncOnline,
  reload = reloadPage,
}: {
  api?: DiscoveryApi;
  online?: boolean;
  reload?: () => void;
}) {
  const { h, locale } = useHopeT();
  const d = h.discovery;
  const { state } = useHope();
  const [phase, setPhase] = useState<Phase>("idle");
  const [view, setView] = useState<DiscoveryJobView | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [last, setLast] = useState<DiscoveryRunSummary | null>(null);
  const [listed, setListed] = useState(false);
  const [keywords, setKeywords] = useState("");
  const [location, setLocation] = useState(() => state.profile.serviceArea ?? "");
  const [refineOpen, setRefineOpen] = useState(false);
  const [fieldError, setFieldError] = useState<{ id: number; text: string } | null>(null);
  const [notice, setNotice] = useState<{ id: number; text: string; profile?: boolean } | null>(null);
  const [pct, setPct] = useState<number | null>(null);
  const [announce, setAnnounce] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [receivedAt, setReceivedAt] = useState(0);

  const viewRef = useRef<DiscoveryJobView | null>(null);
  const pollNow = useRef(false);
  const errors = useRef(0);
  const announcedAt = useRef(0);
  const focusInside = useRef(false);
  const panel = useRef<HTMLElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  const refreshLast = useCallback(() => {
    api
      .listJobs(1)
      .then((list) => {
        setLast(list.items[0] ?? null);
        setListed(true);
        return list;
      })
      .catch((err: unknown) => console.warn("hope discovery:", err));
  }, [api]);

  const apply = useCallback(
    (v: DiscoveryJobView) => {
      const prev = viewRef.current && viewRef.current.job.job_id === v.job.job_id ? viewRef.current : null;
      const merged = prev ? { ...v, steps: [...prev.steps, ...v.steps.filter((s) => s.seq > prev.last_seq)] } : v;
      viewRef.current = merged;
      setView(merged);
      setReceivedAt(Date.now());
      setNow(Date.now());
      const p = progressOf(merged);
      if (p !== null) setPct((old) => Math.max(old ?? 0, p));
      const terminal = v.job.status === "done" || v.job.status === "failed";
      const milestone =
        terminal ||
        ((prev?.job.progress.queries_total ?? 0) === 0 && v.job.progress.queries_total > 0) ||
        v.steps.some((s) => s.kind === "candidate" && s.seq > (prev?.last_seq ?? 0));
      const at = Date.now();
      if (milestone || at - announcedAt.current >= ANNOUNCE_MS) {
        announcedAt.current = at;
        setAnnounce(v.job.status === "failed" ? (v.job.error ?? d.failedTitle) : v.job.status === "done" ? d.doneTitle : v.job.progress.current_step);
      }
    },
    [d],
  );

  const resume = useCallback((id: string) => {
    errors.current = 0;
    pollNow.current = true;
    setJobId(id);
    setPhase("running");
  }, []);

  useEffect(() => {
    if (!online) return;
    let live = true;
    api
      .listJobs(1)
      .then((list) => {
        if (!live) return;
        setLast(list.items[0] ?? null);
        setListed(true);
        if (list.running_job_id) resume(list.running_job_id);
      })
      .catch((err: unknown) => console.warn("hope discovery:", err));
    return () => {
      live = false;
    };
  }, [api, online, resume]);

  useEffect(() => {
    if (phase !== "running" || !jobId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      timer = setTimeout(tick, typeof document !== "undefined" && document.hidden ? HIDDEN_POLL_MS : POLL_MS);
    };
    async function tick() {
      try {
        const v = await api.getJob(jobId!, viewRef.current?.job.job_id === jobId ? viewRef.current.last_seq : 0);
        if (stopped) return;
        errors.current = 0;
        apply(v);
        if (v.job.status === "done" || v.job.status === "failed") {
          focusInside.current = !!panel.current?.contains(document.activeElement);
          setPhase(v.job.status);
          refreshLast();
          return;
        }
      } catch (err) {
        if (stopped) return;
        if (err instanceof ProblemError && err.status === 404) {
          setPhase("gone");
          return;
        }
        errors.current += 1;
        if (errors.current >= MAX_NETWORK_ERRORS) {
          setPhase("lost");
          return;
        }
      }
      schedule();
    }
    if (pollNow.current) {
      pollNow.current = false;
      void tick();
    } else schedule();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [phase, jobId, api, apply, refreshLast]);

  useEffect(() => {
    if (phase !== "running") return;
    const slow = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const t = setInterval(() => setNow(Date.now()), slow ? 5000 : 1000);
    return () => clearInterval(t);
  }, [phase]);

  useEffect(() => {
    if ((phase === "done" || phase === "failed") && focusInside.current) {
      focusInside.current = false;
      heading.current?.focus();
    }
  }, [phase]);

  const start = async () => {
    const parsed = parseRequest(keywords, location, d);
    if ("error" in parsed) {
      setFieldError({ id: Date.now(), text: parsed.error });
      setRefineOpen(true);
      return;
    }
    setFieldError(null);
    setNotice(null);
    setPhase("starting");
    try {
      const v = await api.startJob(parsed.body);
      viewRef.current = null;
      setPct(null);
      apply(v);
      errors.current = 0;
      pollNow.current = false;
      setJobId(v.job.job_id);
      setPhase("running");
    } catch (err) {
      const code = err instanceof ProblemError ? err.code : "network_error";
      const extra = err instanceof DiscoveryProblem ? err.extra : {};
      const id = Date.now();
      setPhase("idle");
      if (code === "job_running") {
        setNotice({ id, text: d.alreadyRunning });
        const running = extra.job_id ?? (await api.listJobs(1).catch(() => null))?.running_job_id;
        if (running) {
          viewRef.current = null;
          setPct(null);
          resume(running);
        }
      } else if (code === "profile_incomplete") setNotice({ id, text: d.profileIncomplete, profile: true });
      else if (code === "validation_error") {
        setFieldError({ id, text: (err instanceof ProblemError && err.errors[0]?.message) || d.badRequest });
        setRefineOpen(true);
      } else if (code === "daily_limit") {
        setNotice({ id, text: d.dailyLimit(extra.limit ?? 0, extra.resets_at ? relative(extra.resets_at, locale, Date.now()) : "") });
      } else if (!(err instanceof ProblemError && err.status === 401)) setNotice({ id, text: d.startFailed });
    }
  };

  const searchAgain = () => {
    setPhase("idle");
    setView(null);
    viewRef.current = null;
    setPct(null);
  };

  const title = { idle: d.title, starting: d.title, running: d.runningTitle, lost: d.runningTitle, done: d.doneTitle, failed: d.failedTitle, gone: d.title }[phase];
  const box = "space-y-3 rounded-xl glass-panel p-4 text-sm";
  const headingEl = (
    <h2 ref={heading} tabIndex={-1} className={`${eyebrow} ${focusRing}`}>
      {title}
    </h2>
  );

  if (!online) {
    return (
      <section aria-label={d.title} className={box}>
        {headingEl}
        <p className="text-muted">{d.offline}</p>
      </section>
    );
  }

  const live = (
    <p aria-live="polite" className="sr-only">
      {announce}
    </p>
  );
  const notices = (
    <>
      {notice && (
        <AutoDismiss key={notice.id}>
          <p role="status" className="text-navy">
            {notice.text}{" "}
            {notice.profile && (
              <Link href="/hope/profile" className={`font-semibold text-teal-ink underline ${focusRing}`}>
                {d.completeProfile}
              </Link>
            )}
          </p>
        </AutoDismiss>
      )}
    </>
  );

  if (phase === "idle" || phase === "starting" || phase === "gone") {
    const starting = phase === "starting";
    return (
      <section ref={panel} aria-label={d.title} className={box}>
        {headingEl}
        {live}
        {phase === "gone" && <p className="text-navy">{d.gone}</p>}
        <p className="hidden text-muted lg:block">{d.intro}</p>
        {listed && !last && <p className="hidden text-muted lg:block">{d.firstRun}</p>}
        <details open={refineOpen} onToggle={(e) => setRefineOpen(e.currentTarget.open)} className="hidden lg:block">
          <summary className={`cursor-pointer font-semibold ${focusRing}`}>{d.refine}</summary>
          <div className="mt-2 space-y-2">
            <label className="block">
              <span className="text-xs font-semibold text-navy">{d.keywords}</span>
              <input className={input} value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder={d.keywordsHint} />
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-navy">{d.location}</span>
              <input className={input} value={location} onChange={(e) => setLocation(e.target.value)} placeholder={d.locationPlaceholder} />
            </label>
            {fieldError && (
              <AutoDismiss key={fieldError.id}>
                <p role="alert" className="text-xs text-navy">
                  {fieldError.text}
                </p>
              </AutoDismiss>
            )}
          </div>
        </details>
        {starting && (
          <>
            <p>{d.startingLine}</p>
            <Bar pct={null} grants={0} d={d} />
          </>
        )}
        <button type="button" className={`${btnPrimary} w-full`} disabled={starting} onClick={() => void start()}>
          {starting ? d.starting : d.find}
        </button>
        {notices}
        {last && (
          <p className="text-xs text-muted">
            {last.status === "failed"
              ? d.lastFailed
              : d.lastSearch(relative(last.finished_at ?? last.started_at, locale, now), last.candidates_found, last.candidates_new)}
          </p>
        )}
      </section>
    );
  }

  const v = view;
  const progress = v?.job.progress;
  const grants = progress?.candidates_found ?? 0;
  const pages = v ? Math.min(v.counts.urls_found, v.limits.max_pages) : 0;
  const steps = v?.steps ?? [];

  if (phase === "running" || phase === "lost") {
    const elapsed = (v?.elapsed_s ?? 0) + (receivedAt ? Math.max(0, (now - receivedAt) / 1000) : 0);
    return (
      <section ref={panel} aria-label={d.runningTitle} className={box}>
        <div className="flex items-center justify-between gap-2">
          {headingEl}
          <span className="text-xs text-muted">{v?.job.status === "running" ? d.statusRunning(clock(elapsed)) : d.statusStarting}</span>
        </div>
        {live}
        {notices}
        {phase === "lost" ? (
          <>
            <p className="text-navy">{d.lost}</p>
            <button type="button" className={`${btnSecondary} w-full`} onClick={() => jobId && resume(jobId)}>
              {d.reconnect}
            </button>
          </>
        ) : (
          <>
            <div className="flex items-center justify-between gap-2 lg:hidden">
              <span>{d.mobileRunning(pct ?? 0)}</span>
              <button type="button" aria-expanded={expanded} className={`text-teal-ink underline ${focusRing}`} onClick={() => setExpanded(!expanded)}>
                {d.details}
              </button>
            </div>
            <p className="truncate text-navy" title={progress?.current_step}>
              {ellipsis(progress?.current_step ?? d.statusStarting)}
            </p>
            <Bar pct={pct} grants={grants} d={d} />
            <p className="text-xs text-muted">{d.counters(progress?.queries_done ?? 0, progress?.queries_total ?? 0, progress?.pages_read ?? 0, pages, grants)}</p>
          </>
        )}
        <div className={`${expanded ? "" : "hidden "}space-y-2 lg:block`}>
          {v && v.job.queries.length > 0 && (
            <details>
              <summary className={`cursor-pointer font-semibold ${focusRing}`}>{d.queriesTitle(v.job.queries.length)}</summary>
              <ul className="mt-1 space-y-1 text-xs">
                {v.job.queries.map((q) => {
                  const failed = steps.some((s) => s.kind === "warning" && s.text.includes(q));
                  const n = steps.find((s) => s.kind === "query" && s.query === q)?.result_count;
                  return <li key={q}>{failed ? `⚠ ${q} ${d.queryFailed}` : n !== undefined ? `✓ ${q} (${n})` : q}</li>;
                })}
              </ul>
            </details>
          )}
          {steps.length > 0 && <Activity steps={steps} d={d} locale={locale} />}
        </div>
      </section>
    );
  }

  if (phase === "failed") {
    return (
      <section ref={panel} aria-label={d.failedTitle} className={box}>
        {headingEl}
        {live}
        <p className="text-navy">
          {d.failedTitle}. {v?.job.error}
        </p>
        <button type="button" className={`${btnPrimary} w-full`} onClick={() => void start()}>
          {d.tryAgain}
        </button>
      </section>
    );
  }

  const counts = v!.counts;
  const found = grants;
  const fresh = counts.candidates_new;
  const stopped = steps.some((s) => s.kind === "warning" && s.text.startsWith("Stopped early"));
  const checks = v!.candidates.filter((c) => needsCheck(c));
  const secs = v!.elapsed_s;
  const summary =
    found === 0
      ? d.noneFound
      : fresh === 0
        ? d.allKnown(found)
        : [
            d.summary.found(found),
            d.summary.fresh(fresh),
            counts.skipped_expired ? d.summary.expired(counts.skipped_expired) : "",
            counts.skipped_poor_fit ? d.summary.poorFit(counts.skipped_poor_fit) : "",
            secs ? d.summary.took(d.duration(Math.floor(secs / 60), secs % 60)) : "",
          ]
            .filter(Boolean)
            .join(" · ");
  return (
    <section ref={panel} aria-label={d.doneTitle} className={box}>
      {headingEl}
      {live}
      {stopped && <p className="rounded-lg glass-control p-2 text-navy">{d.stoppedEarly(counts.pages_read, counts.urls_found)}</p>}
      <p className="text-navy">{summary}</p>
      <div className="flex flex-wrap gap-2">
        {fresh > 0 && (
          <button type="button" className={btnPrimary} onClick={reload}>
            {d.showNew}
          </button>
        )}
        <button type="button" className={btnSecondary} onClick={searchAgain}>
          {d.searchAgain}
        </button>
      </div>
      {checks.length > 0 && (
        <div className="text-xs text-muted">
          <p>{d.needsCheck(checks.length)}</p>
          <ul className="mt-1 space-y-1">
            {checks.map((c) => (
              <li key={c.grant_id}>
                <a href={c.url} target="_blank" rel="noopener noreferrer" className={`text-teal-ink underline ${focusRing}`}>
                  {c.title} <span aria-hidden>↗</span>
                  <span className="sr-only"> {d.opens(host(c.url))}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function Bar({ pct, grants, d }: { pct: number | null; grants: number; d: Copy }) {
  const aria = pct === null ? {} : { "aria-valuenow": pct, "aria-valuetext": d.progressText(pct, grants) };
  return (
    <div role="progressbar" aria-label={d.progressLabel} aria-valuemin={0} aria-valuemax={100} {...aria} className="h-2 overflow-hidden rounded-full glass-control">
      <div
        className={`h-full rounded-full bg-teal-ink ${pct === null ? "w-1/3 motion-safe:animate-pulse" : "motion-safe:transition-[width] motion-safe:duration-500"}`}
        style={pct === null ? undefined : { width: `${pct}%` }}
      />
    </div>
  );
}

function Activity({ steps, d, locale }: { steps: DiscoveryJobView["steps"]; d: Copy; locale: string }) {
  return (
    <details>
      <summary className={`cursor-pointer font-semibold ${focusRing}`}>{d.activity(steps.length)}</summary>
      <ol className="mt-1 space-y-1 text-xs">
        {steps.map((s) => {
          const time = new Date(s.at).toLocaleTimeString(locale, { hour12: false });
          const text = `${ICON[s.kind] ? `${ICON[s.kind]} ` : ""}${s.text}`;
          return (
            <li key={s.seq} className={s.kind === "skip" ? "text-muted" : "text-navy"}>
              {time} ·{" "}
              {s.url ? (
                <a href={s.url} target="_blank" rel="noopener noreferrer" className={`underline ${focusRing}`}>
                  {text}
                  <span className="sr-only"> {d.opens(host(s.url))}</span>
                </a>
              ) : (
                text
              )}
            </li>
          );
        })}
      </ol>
    </details>
  );
}
