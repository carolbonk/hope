"use client";

import { TextArea } from "@/components/ui";
import { TagInput } from "../TagInput";
import type { StepProps } from "./types";

export function MissionStep({ form, set, errors }: StepProps) {
  const m = form.mission;
  const patch = (p: Partial<typeof m>) => set((f) => ({ ...f, mission: { ...f.mission, ...p } }));
  return (
    <div className="flex flex-col gap-4">
      <TextArea
        label="Mission statement *"
        aria-required
        value={m.mission_statement}
        maxLength={2000}
        rows={4}
        onChange={(e) => patch({ mission_statement: e.target.value })}
        error={errors["mission.mission_statement"]}
        hint={`${m.mission_statement.length} / 2000`}
        placeholder="What does your organization do, for whom, and why?"
      />
      <TextArea
        label="Vision (optional)"
        value={m.vision_statement ?? ""}
        maxLength={2000}
        rows={2}
        onChange={(e) => patch({ vision_statement: e.target.value || null })}
        error={errors["mission.vision_statement"]}
      />
      <TagInput
        label="Values"
        values={m.values}
        onChange={(values) => patch({ values })}
        max={10}
        maxLength={60}
        placeholder="e.g. Community-led — press Enter to add"
        hint="Up to 10."
      />
    </div>
  );
}
