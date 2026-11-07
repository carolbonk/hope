"use client";

import { useMemo, useSyncExternalStore } from "react";

const noop = () => () => {};

/** Today's date, computed only in the browser so server and client HTML never disagree. */
export function useToday(): Date | null {
  const key = useSyncExternalStore(noop, () => new Date().toDateString(), () => null);
  return useMemo(() => (key ? new Date(key) : null), [key]);
}
