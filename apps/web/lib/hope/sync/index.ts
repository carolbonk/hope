"use client";

import { useEffect, useRef } from "react";
import { online } from "@/api/http";
import { useSession } from "@/api/session";
import { useHope } from "../store";
import { flushDecisions } from "./decisions";
import { loadRemoteProfile } from "./profile";

export { online as syncEnabled } from "@/api/http";

const warn = (err: unknown) => console.warn("hope sync:", err);

/** Mounted once in `app/hope/layout.tsx`: loads the remote profile and flushes decisions once the session is ready. */
export function HopeSync(): null {
  const { status } = useSession();
  const { hydrateProfile } = useHope();
  const hydrate = useRef(hydrateProfile);
  const started = useRef(false);

  useEffect(() => {
    hydrate.current = hydrateProfile;
  }, [hydrateProfile]);

  useEffect(() => {
    if (!online || status !== "ready" || started.current) return;
    started.current = true;
    try {
      loadRemoteProfile()
        .then((p) => p && hydrate.current(p))
        .catch(warn);
      flushDecisions().catch(warn);
    } catch (err) {
      warn(err);
    }
  }, [status]);

  return null;
}
