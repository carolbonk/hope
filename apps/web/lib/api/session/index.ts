"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import { apiFetch, online, ProblemError, UNAUTHORIZED_EVENT } from "@/lib/api/http";

// Mirror contracts/mocks/w1/**.
export type User = { user_id: string; email: string; display_name: string };
export type Me = User & { agency_id: string; onboarding_complete: boolean };

export const me = () => apiFetch<Me>("/v1/me");
export const login = (body: { email: string; password: string }) =>
  apiFetch<{ user: User }>("/v1/auth/login", { method: "POST", body: JSON.stringify(body) }).then((r) => r.user);
export const signup = (body: { email: string; password: string; display_name: string; invite_code: string }) =>
  apiFetch<{ user: User }>("/v1/auth/signup", { method: "POST", body: JSON.stringify(body) }).then((r) => r.user);
export const logout = () => apiFetch<void>("/v1/auth/logout", { method: "POST" });

/** `next` only when it is a same-site path; anything else goes to Discover. */
export function safeNext(next: string | null | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/hope/discover";
}

export type SessionStatus = "offline" | "loading" | "signed_out" | "unreachable" | "ready";
/** `signedOut` = the user clicked Sign out (go to `/login`), not an expired session (keep `next`). */
type Snapshot = { status: SessionStatus; me?: Me; signedOut?: boolean };

// One cached `me()` shared by every component.
let snapshot: Snapshot = online ? { status: "loading" } : { status: "offline" };
let loaded = false;
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();

function set(next: Snapshot) {
  snapshot = next;
  listeners.forEach((l) => l());
}

function fetchMe(): Promise<void> {
  loaded = true;
  inflight ??= me()
    .then(
      (m) => set({ status: "ready", me: m }),
      (err) => set({ status: err instanceof ProblemError && err.status === 401 ? "signed_out" : "unreachable" }),
    )
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

const onFocus = () => void fetchMe();
const onUnauthorized = () => set({ status: "signed_out" });

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) {
    window.addEventListener("focus", onFocus);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      window.removeEventListener("focus", onFocus);
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    }
  };
}

/** Clears the cached session; the next `useSession()` refetches `/v1/me`. SC01 and SC11 call it. */
export function invalidateSession() {
  loaded = false;
  if (online) set({ status: "loading" });
}

/** Sign out: `POST /v1/auth/logout`, then drop the cached session without refetching it. */
export async function signOut(): Promise<void> {
  await logout();
  loaded = true;
  set({ status: "signed_out", signedOut: true });
}

export function useSession(): Snapshot & { retry: () => void } {
  const current = useSyncExternalStore(subscribe, () => snapshot, () => snapshot);
  useEffect(() => {
    if (online && !loaded) void fetchMe();
  }, [current.status]);
  const retry = useCallback(() => {
    if (!online) return;
    set({ status: "loading" });
    void fetchMe();
  }, []);
  return { ...current, retry };
}
