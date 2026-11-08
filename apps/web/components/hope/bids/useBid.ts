"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ProblemError } from "@/lib/api/http";
import { problemMessage } from "@/lib/hope/sync/applications";
import * as api from "./api";
import type { BidView, Member } from "./api";
import { useBidsCopy } from "./copy";

export type RunBid = (call: (version: number) => Promise<BidView>, done?: string) => Promise<boolean>;

/** One bid per page, with the team for the owner picker. Writes use the latest `version`: a 412 reloads,
 * 409/422 show the server's message; nothing throws. */
export function useBid(grantId: string) {
  const t = useBidsCopy().bid;
  const [view, setView] = useState<BidView | null | undefined>(undefined);
  const [members, setMembers] = useState<Member[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [notice, setNotice] = useState<{ text: string; ok: boolean } | null>(null);
  const [pending, setPending] = useState(false);
  const latest = useRef<BidView | null>(null);

  const show = useCallback((v: BidView | null) => {
    latest.current = v;
    setView(v);
  }, []);

  const reload = useCallback(
    () =>
      api.getBid(grantId).then(
        (v) => (show(v), setLoadError(false)),
        (err) => (err instanceof ProblemError && err.status === 404 ? show(null) : setLoadError(true)),
      ),
    [grantId, show],
  );

  useEffect(() => {
    void reload();
    api.listMembers().then(setMembers, () => setMembers([]));
  }, [reload]);

  const run: RunBid = useCallback(
    async (call, done) => {
      const current = latest.current;
      if (!current) return false;
      setNotice(null);
      setPending(true);
      try {
        show(await call(current.version));
        if (done) setNotice({ text: done, ok: true });
        return true;
      } catch (err) {
        const e = err instanceof ProblemError ? err : null;
        if (e?.status === 412) {
          setNotice({ text: t.stale, ok: false });
          await reload();
        } else if (e && (e.status === 409 || e.status === 422)) setNotice({ text: problemMessage(e), ok: false });
        else setNotice({ text: t.failed, ok: false });
        return false;
      } finally {
        setPending(false);
      }
    },
    [reload, show, t],
  );

  const clearNotice = useCallback(() => setNotice(null), []);
  return { view, members, loadError, notice, clearNotice, pending, reload, run };
}
