"use client";

import { useMemo } from "react";
import { useToday } from "@/components/useToday";
import { demoOpportunities } from "./demo";
import type { Opportunity } from "./types";

/** Opportunity catalog. Today only fictional demo data; a backend feed would replace this hook. */
export function useOpportunities(): Opportunity[] {
  const today = useToday();
  return useMemo(() => (today ? demoOpportunities(today) : []), [today]);
}
