"use client";

import { useEffect, useMemo, useState } from "react";
import { useToday } from "@/components/useToday";
import { demoOpportunities } from "./demo";
import { fetchOpportunities } from "./sync/opportunities";
import type { Opportunity } from "./types";

/** Opportunity catalog: the remote feed when the sync adapter has one, otherwise the fictional demo data. */
export function useOpportunities(): Opportunity[] {
  const today = useToday();
  const [remote, setRemote] = useState<Opportunity[] | null>(null);
  useEffect(() => {
    let live = true;
    const warn = (err: unknown) => console.warn("hope sync:", err);
    try {
      fetchOpportunities().then((r) => {
        if (live && r) setRemote(r);
      }, warn);
    } catch (err) {
      warn(err);
    }
    return () => {
      live = false;
    };
  }, []);
  return useMemo(() => remote ?? (today ? demoOpportunities(today) : []), [remote, today]);
}
