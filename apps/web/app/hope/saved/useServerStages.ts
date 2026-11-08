"use client";

import { useEffect, useState } from "react";
import { apiFetch, online } from "@/lib/api/http";
import type { Stage } from "@/lib/hope/types";

/** Each grant's application stage on the server; empty offline or when the list can't load. */
export function useServerStages(): Map<string, Stage> {
  const [stages, setStages] = useState<Map<string, Stage>>(new Map());
  useEffect(() => {
    if (!online) return;
    apiFetch<{ items: { grant_id: string; stage: Stage }[] }>("/v1/applications").then(
      (list) => setStages(new Map(list.items.map((a) => [a.grant_id, a.stage]))),
      () => undefined,
    );
  }, []);
  return stages;
}
