// Mirrors Discover decisions to `/v1/grants` through a localStorage outbox. Never throws or rejects;
// with sync off it does nothing. The browser state (`hope:state:v1`) is never read or changed here.
import { apiFetch, online, ProblemError } from "@/api/http";

export type DecisionStatus = "saved" | "passed" | "new";

export const OUTBOX_KEY = "hope:sync:decisions:v1";
const GRANT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const BACKOFF_MS = [2_000, 8_000, 30_000, 60_000];
const MAX_ATTEMPTS = 5;
const REQUESTS: Record<DecisionStatus, { action: string; body?: string }> = {
  saved: { action: "save" },
  passed: { action: "pass", body: "{}" },
  new: { action: "reset" },
};

type Entry = { status: DecisionStatus; attempts: number; at: string };
type Outbox = { version: 1; pending: Record<string, Entry> };

const warn = (err: unknown) => console.warn("decision sync:", err);

function readOutbox(): Outbox {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(OUTBOX_KEY) ?? "null") as Outbox | null;
    if (parsed?.version === 1 && parsed.pending && typeof parsed.pending === "object") return parsed;
  } catch (err) {
    warn(err);
  }
  return { version: 1, pending: {} };
}

/** Applies `change` to the stored outbox (read, change, write in one step). */
function updateOutbox(change: (pending: Record<string, Entry>) => void) {
  const box = readOutbox();
  change(box.pending);
  window.localStorage.setItem(OUTBOX_KEY, JSON.stringify(box));
}

/** Changes an entry only if it is still the one that was sent (a newer intent wins). */
function settle(grantId: string, sent: Entry, change: (entry: Entry) => Entry | null) {
  updateOutbox((pending) => {
    const current = pending[grantId];
    if (!current || current.at !== sent.at || current.status !== sent.status) return;
    const next = change(current);
    if (next) pending[grantId] = next;
    else delete pending[grantId];
  });
}

function resetAttempts() {
  updateOutbox((pending) => {
    for (const entry of Object.values(pending)) entry.attempts = 0;
  });
}

let running: Promise<void> | null = null;
let again = false;
let retryTimer: ReturnType<typeof setTimeout> | undefined;
let loaded = false;
let scheduled = false;

async function flush(): Promise<void> {
  clearTimeout(retryTimer);
  retryTimer = undefined;
  for (;;) {
    const next = Object.entries(readOutbox().pending)
      .filter(([, e]) => e.attempts < MAX_ATTEMPTS)
      .sort(([, a], [, b]) => a.at.localeCompare(b.at))[0];
    if (!next) return;
    const [grantId, entry] = next;
    const { action, body } = REQUESTS[entry.status];
    try {
      await apiFetch(`/v1/grants/${grantId}/${action}`, { method: "POST", body });
      settle(grantId, entry, () => null);
    } catch (err) {
      const status = err instanceof ProblemError ? err.status : 0;
      const code = err instanceof ProblemError ? err.code : "unknown";
      if (status === 401) {
        again = false;
        return;
      }
      if (status === 422 || (status === 404 && code === "grant_not_found")) {
        console.warn("decision sync dropped", { grantId, code });
        settle(grantId, entry, () => null);
        continue;
      }
      const attempts = entry.attempts + 1;
      settle(grantId, entry, (e) => ({ ...e, attempts }));
      const delay = BACKOFF_MS[attempts - 1];
      if (delay !== undefined) retryTimer = setTimeout(flushDecisions, delay);
      return;
    }
  }
}

/** Sends any decisions not yet mirrored. */
export function flushDecisions(): Promise<void> {
  if (!online) return Promise.resolve();
  try {
    if (!loaded) {
      loaded = true;
      resetAttempts();
    }
    if (running) {
      again = true;
      return running;
    }
    running = flush()
      .catch(warn)
      .finally(() => {
        running = null;
        if (again) {
          again = false;
          void flushDecisions();
        }
      });
    return running;
  } catch (err) {
    warn(err);
    return Promise.resolve();
  }
}

/** Fire-and-forget mirror of a swipe (or "new" on undo), after the local write. */
export function mirrorDecision(oppId: string, decision: DecisionStatus): void {
  if (!online || !GRANT_ID.test(oppId)) return;
  try {
    updateOutbox((pending) => {
      pending[oppId] = { status: decision, attempts: 0, at: new Date().toISOString() };
    });
    // On the next microtask, so a burst (save, undo, pass) coalesces into one request. During a
    // backoff the entry waits for the retry timer, so new swipes don't use up earlier entries' attempts.
    if (scheduled) return;
    scheduled = true;
    void Promise.resolve().then(() => {
      scheduled = false;
      return retryTimer === undefined ? flushDecisions() : undefined;
    });
  } catch (err) {
    warn(err);
  }
}

if (online && typeof window !== "undefined") {
  window.addEventListener("online", () => {
    try {
      resetAttempts();
      void flushDecisions();
    } catch (err) {
      warn(err);
    }
  });
}
