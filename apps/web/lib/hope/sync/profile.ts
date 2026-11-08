import type { OrgProfile } from "../types";

// H1 replaces these bodies. Contract: never reject or throw; with sync off resolve/return at once.

/** `null` = nothing remote (or sync off). */
export function loadRemoteProfile(): Promise<OrgProfile | null> {
  return Promise.resolve(null);
}

/** Fire-and-forget, after the local write. */
export function saveRemoteProfile(profile: OrgProfile): void {
  void profile;
}
