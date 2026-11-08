"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ProblemError } from "@/api/http";
import { useHopeT } from "@/lib/hope/i18n";
import * as api from "@/lib/hope/sync/applications";
import type { ApplicationView } from "@/lib/hope/sync/applications";

/** `handle` sees a problem first; returning true means it dealt with it. */
export type Run = (call: (version: number) => Promise<ApplicationView>, handle?: (err: ProblemError) => boolean) => Promise<boolean>;

export type ServerApplication = {
  view: ApplicationView | null | undefined;
  loadError: boolean;
  notice: string | null;
  clearNotice: () => void;
  pending: boolean;
  reload: () => Promise<void>;
  run: Run;
};

const POLL_MS = 2000;

/** One server application per page: loads it for `grantId`, polls running jobs, and runs writes with the
 * latest `version`. A 412 reloads; 409/422 show the server's message; nothing throws. */
export function useServerApplication(grantId: string): ServerApplication {
  const { h } = useHopeT();
  const t = h.apply;
  const [view, setView] = useState<ApplicationView | null | undefined>(undefined);
  const [loadError, setLoadError] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
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
    async (call, handle) => {
      const current = latest.current;
      if (!current) return false;
      setNotice(null);
      setPending(true);
      try {
        show(await call(current.version));
        return true;
      } catch (err) {
        const e = err instanceof ProblemError ? err : null;
        if (e && handle?.(e)) return false;
        if (e?.status === 412) {
          setNotice(t.stale);
          await reload();
        } else if (e?.code === "job_running") setNotice(t.busy);
        else if (e?.code === "profile_incomplete") setNotice(t.profileIncomplete);
        else if (e && (e.status === 409 || e.status === 422)) setNotice(api.problemMessage(e));
        else setNotice(t.failed);
        return false;
      } finally {
        setPending(false);
      }
    },
    [reload, show, t],
  );

  const clearNotice = useCallback(() => setNotice(null), []);
  return { view, loadError, notice, clearNotice, pending, reload, run };
}
