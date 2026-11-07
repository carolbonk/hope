"use client";

import type { OnboardingApi } from "@/api/onboarding";
import { NteePicker } from "../NteePicker";
import type { StepProps } from "./types";

export function CauseStep({ form, set, errors, api, labels, setLabels }: StepProps & { api: OnboardingApi; labels: Record<string, string>; setLabels: (l: Record<string, string>) => void }) {
  return (
    <NteePicker
      api={api}
      selected={form.ntee_codes}
      labels={labels}
      onChange={(codes, next) => {
        setLabels(next);
        set((f) => ({ ...f, ntee_codes: codes }));
      }}
      mission={form.mission.mission_statement}
      programs={form.programs.map((p) => ({ name: p.name, description: p.description }))}
      error={errors.ntee_codes}
    />
  );
}
