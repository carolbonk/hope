import type { HopeDraftRequest } from "@/lib/hope/draft";

export const NOT_STATED = "amount not stated";

/** What the agent reads: an unknown amount (a saved check card) is spelled out, never null, 0 or NaN. */
export function agentInput({ profile, opportunity: o, ask }: HopeDraftRequest) {
  return {
    profile,
    opportunity: { ...o, amountMin: o.amountMin ?? NOT_STATED, amountMax: o.amountMax ?? NOT_STATED },
    ask: ask ?? NOT_STATED,
  };
}
