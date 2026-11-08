// H3 replaces these bodies. Contract: never throw or reject; with sync off do nothing.

export type DecisionStatus = "saved" | "passed" | "new";

/** Fire-and-forget mirror of a swipe (or "new" on undo), after the local write. */
export function mirrorDecision(oppId: string, decision: DecisionStatus): void {
  void oppId;
  void decision;
}

/** Sends any decisions not yet mirrored. */
export function flushDecisions(): Promise<void> {
  return Promise.resolve();
}
