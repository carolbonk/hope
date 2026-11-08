"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { cx } from "@/lib/cx";

/** No notification, alert or validation message stays on screen longer than this. */
export const NOTICE_MS = 5000;
const FADE_MS = 300;

/**
 * Shows its children for at most `ms`, fading out over the last 300 ms, then unmounts them.
 * Give it a `key` tied to the message so a new message restarts the timer.
 */
export function AutoDismiss({ children, ms = NOTICE_MS, className, onDismiss }: { children: ReactNode; ms?: number; className?: string; onDismiss?: () => void }) {
  const [phase, setPhase] = useState<"shown" | "leaving" | "gone">("shown");
  const dismissed = useRef(onDismiss);
  useEffect(() => {
    dismissed.current = onDismiss;
  }, [onDismiss]);
  useEffect(() => {
    const fade = setTimeout(() => setPhase("leaving"), Math.max(0, ms - FADE_MS));
    const gone = setTimeout(() => {
      setPhase("gone");
      dismissed.current?.();
    }, ms);
    return () => {
      clearTimeout(fade);
      clearTimeout(gone);
    };
  }, [ms]);
  if (phase === "gone") return null;
  return <div className={cx("transition-opacity duration-300 ease-out", phase === "leaving" && "opacity-0", className)}>{children}</div>;
}
