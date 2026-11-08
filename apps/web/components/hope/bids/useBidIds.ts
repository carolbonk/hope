"use client";

import { useEffect, useState } from "react";
import { online } from "@/lib/api/http";
import { listBids } from "./api";

/** Grant ids that already have a bid on the server; empty offline or when the list can't load. */
export function useBidIds(): Set<string> {
  const [ids, setIds] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!online) return;
    listBids().then(
      (bids) => setIds(new Set(bids.map((b) => b.grant_id))),
      () => undefined,
    );
  }, []);
  return ids;
}
