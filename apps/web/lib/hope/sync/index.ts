"use client";

import { useEffect, useRef } from "react";
import { online } from "@/api/http";
import { useSession } from "@/api/session";
import { useHope } from "../store";
import { flushDecisions, loadRemoteDecisions } from "./decisions";
import { loadRemoteProfile } from "./profile";

export { online as syncEnabled } from "@/api/http";

const warn = (err: unknown) => console.warn("hope sync:", err);

/**
 * Mounted once in `app/hope/layout.tsx`. Once the session is ready: loads the remote profile, flushes decisions,
 * and loads the server's saved/passed grants (applied after the profile, so neither write overwrites the other).
 */
export function HopeSync(): null {
  const { status } = useSession();
  const { hydrateProfile, hydrateDecisions } = useHope();
  const hydrate = useRef({ hydrateProfile, hydrateDecisions });
  const started = useRef(false);

  useEffect(() => {
    hydrate.current = { hydrateProfile, hydrateDecisions };
  }, [hydrateProfile, hydrateDecisions]);

  useEffect(() => {
    if (!online || status !== "ready" || started.current) return;
    started.current = true;
    try {
      const decisions = loadRemoteDecisions();
      const profile = loadRemoteProfile()
        .then((p) => p && hydrate.current.hydrateProfile(p))
        .catch(warn);
      flushDecisions().catch(warn);
      Promise.all([decisions, profile])
        .then(([d]) => d && hydrate.current.hydrateDecisions(d))
        .catch(warn);
    } catch (err) {
      warn(err);
    }
  }, [status]);

  return null;
}
