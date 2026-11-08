import { online, ProblemError } from "@/api/http";
import { profileApi, type ProfileForm, type ProfileSections, type ProfileView } from "@/api/profile";
import { validateStep, type StepId } from "@/features/onboarding/model";
import { formFromProfile, profileFromOnboarding } from "../fromOnboarding";
import { HOPE_KEY, normalizeProfile } from "../store";
import type { HopeState, OrgProfile } from "../types";

// H1: keeps the browser profile (`useHope()`) and `/v1/profile` in step. Never rejects or throws.

export const SYNC_KEY = "hope:sync:profile:v1";
const SECTIONS = ["basics", "mission", "ntee_codes", "budget", "programs"] as const;
type Section = (typeof SECTIONS)[number];
const STEP_OF: Record<Section, StepId> = { basics: "basics", mission: "mission", ntee_codes: "cause", budget: "budget", programs: "programs" };

type SyncState = { etag: string | null; form: ProfileForm | null; pending: boolean; skipped: string[] };

let state: SyncState | null = null;
let queued: OrgProfile | null = null;
let worker: Promise<void> | null = null;

function current(): SyncState {
  if (state) return state;
  state = { etag: null, form: null, pending: false, skipped: [] };
  try {
    const raw = window.localStorage.getItem(SYNC_KEY);
    if (raw) state = { ...state, ...(JSON.parse(raw) as Partial<SyncState>) };
  } catch {
    // unreadable storage: start from no base
  }
  return state;
}

function update(patch: Partial<SyncState>) {
  state = { ...current(), ...patch };
  try {
    window.localStorage.setItem(SYNC_KEY, JSON.stringify(state));
  } catch {
    // storage full or blocked: keep the in-memory state
  }
}

const setBase = (view: ProfileView, extra: Partial<SyncState> = {}) => update({ etag: view.etag, form: view.form, ...extra });

function warn(err: unknown) {
  console.warn("[hope-sync] profile", err instanceof ProblemError ? err.code : "network_error");
}

function readLocal(): OrgProfile {
  let saved: Partial<HopeState> = {};
  try {
    saved = JSON.parse(window.localStorage.getItem(HOPE_KEY) ?? "{}") as Partial<HopeState>;
  } catch {
    saved = {};
  }
  return normalizeProfile(saved.profile);
}

async function fetchBase(): Promise<ProfileView | null> {
  const view = await profileApi().getProfile();
  if (view) setBase(view);
  return view;
}

const stable = (v: unknown): string =>
  JSON.stringify(v, (_k, x: unknown) =>
    x && typeof x === "object" && !Array.isArray(x) ? Object.fromEntries(Object.entries(x).sort(([a], [b]) => a.localeCompare(b))) : x,
  );

function build(profile: OrgProfile, base: ProfileForm): { sections: ProfileSections; skipped: string[] } {
  const form = formFromProfile(profile, base);
  const skipped: string[] = profile.currency !== "USD" && profile.annualBudget !== null ? ["non_usd_budget"] : [];
  const sections: Record<string, unknown> = {};
  for (const name of SECTIONS) {
    if (stable(form[name]) === stable(base[name])) continue;
    if (Object.keys(validateStep(STEP_OF[name], form)).length) skipped.push(name);
    else sections[name] = form[name];
  }
  return { sections: sections as ProfileSections, skipped };
}

async function push(profile: OrgProfile, retried = false): Promise<void> {
  const base = current();
  if (!base.form || !base.etag) return;
  const { sections, skipped } = build(profile, base.form);
  update({ skipped });
  if (!Object.keys(sections).length) return update({ pending: false });
  try {
    setBase(await profileApi().patchProfile(sections, base.etag), { pending: false });
  } catch (err) {
    warn(err);
    if (err instanceof ProblemError && (err.status === 409 || err.status === 428)) {
      if (retried || !(await fetchBase())) return update({ pending: true });
      return push(profile, true);
    }
    if (err instanceof ProblemError && err.status === 422) {
      const bad = err.errors.map((e) => e.field.split(".")[0] ?? e.field);
      return update({ skipped: [...new Set([...skipped, ...bad])] });
    }
    update({ pending: true });
  }
}

async function drain(): Promise<void> {
  while (queued) {
    const next = queued;
    queued = null;
    try {
      if (!current().form && !(await fetchBase())) {
        update({ skipped: ["needs_onboarding"] });
        continue;
      }
      await push(next);
    } catch (err) {
      warn(err);
      update({ pending: true });
    }
  }
  worker = null;
}

/** `null` = nothing remote (or sync off). */
export function loadRemoteProfile(): Promise<OrgProfile | null> {
  if (!online) return Promise.resolve(null);
  return (async () => {
    try {
      const local = readLocal();
      const view = await fetchBase();
      if (!view) return null;
      if (!local.updatedAt || Date.parse(local.updatedAt) < Date.parse(view.updated_at))
        return { ...profileFromOnboarding(view.form, local), updatedAt: view.updated_at };
      if (current().pending) saveRemoteProfile(local);
      return null;
    } catch (err) {
      warn(err);
      return null;
    }
  })();
}

/** Fire-and-forget, after the local write. */
export function saveRemoteProfile(profile: OrgProfile): void {
  if (!online) return;
  try {
    queued = profile;
    worker ??= drain();
  } catch (err) {
    warn(err);
  }
}

/** Not part of the seam: sync state for tests and devtools. `idle` settles when the queue is empty. */
export function profileSyncStatus(): SyncState & { idle: Promise<void> } {
  return { ...current(), idle: worker ?? Promise.resolve() };
}
