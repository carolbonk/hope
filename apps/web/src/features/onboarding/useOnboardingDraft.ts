"use client";

import type { ProfileForm } from "@/api/profile";

export const DRAFT_KEY = "hope.onboarding.v1";

export function loadDraft(): ProfileForm | null {
  try {
    const raw = window.localStorage.getItem(DRAFT_KEY);
    return raw ? (JSON.parse(raw) as ProfileForm) : null;
  } catch {
    return null;
  }
}

export function saveDraft(form: ProfileForm): void {
  try {
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify(form));
  } catch {
    // Storage full or disabled: the wizard still works in memory.
  }
}

export function clearDraft(): void {
  try {
    window.localStorage.removeItem(DRAFT_KEY);
  } catch {
    // ignore
  }
}
