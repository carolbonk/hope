"use client";

import { useEffect, useRef, useState } from "react";
import type { ProgramForm } from "@/api/profile";
import { Button, TextArea, TextField } from "@/components/ui";
import { emptyProgram } from "../model";
import type { StepProps } from "./types";

const MAX = 10;

export function ProgramsStep({ form, set, errors }: StepProps) {
  const [confirming, setConfirming] = useState<number | null>(null);
  const focusIndex = useRef<number | null>(null);
  const list = useRef<HTMLOListElement>(null);

  useEffect(() => {
    if (focusIndex.current == null) return;
    list.current?.querySelectorAll<HTMLInputElement>("input[data-program-name]")[focusIndex.current]?.focus();
    focusIndex.current = null;
  });

  const patch = (i: number, p: Partial<ProgramForm>) => set((f) => ({ ...f, programs: f.programs.map((x, j) => (j === i ? { ...x, ...p } : x)) }));
  const remove = (i: number) => {
    set((f) => ({ ...f, programs: f.programs.filter((_, j) => j !== i) }));
    setConfirming(null);
  };
  const add = () => {
    set((f) => ({ ...f, programs: [...f.programs, emptyProgram()] }));
    focusIndex.current = form.programs.length;
  };

  return (
    <div className="flex flex-col gap-4">
      <ol ref={list} className="flex flex-col gap-4" aria-label="Programs">
        {form.programs.map((p, i) => (
          <li key={i} className="glass-inset rounded-2xl p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-ink">Program {i + 1}</h3>
              {form.programs.length > 1 &&
                (confirming === i ? (
                  <div className="flex items-center gap-2 text-sm" role="group" aria-label="Confirm removal">
                    <span>Remove {p.name || `program ${i + 1}`}?</span>
                    <Button variant="danger" onClick={() => remove(i)}>
                      Remove
                    </Button>
                    <Button variant="ghost" onClick={() => setConfirming(null)}>
                      Keep
                    </Button>
                  </div>
                ) : (
                  <Button variant="ghost" onClick={() => setConfirming(i)} aria-label={`Remove ${p.name || `program ${i + 1}`}`}>
                    Remove
                  </Button>
                ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField wrapperClassName="sm:col-span-2" data-program-name label="Program name *" aria-required value={p.name} onChange={(e) => patch(i, { name: e.target.value })} error={errors[`programs.${i}.name`]} placeholder="Mobile Dental Clinic" />
              <TextArea wrapperClassName="sm:col-span-2" label="Description *" aria-required rows={3} value={p.description} onChange={(e) => patch(i, { description: e.target.value })} error={errors[`programs.${i}.description`]} placeholder="What the program does and how." />
              <TextField wrapperClassName="sm:col-span-2" label="People served *" aria-required value={p.people_served} onChange={(e) => patch(i, { people_served: e.target.value })} error={errors[`programs.${i}.people_served`]} placeholder="Children and adults on Medicaid" />
              <TextField
                label="Served per year (optional)"
                inputMode="numeric"
                value={p.annual_served == null ? "" : String(p.annual_served)}
                onChange={(e) => {
                  const d = e.target.value.replace(/\D/g, "");
                  patch(i, { annual_served: d ? Number(d) : null });
                }}
                placeholder="3200"
              />
              <TextField label="Age range (optional)" maxLength={40} value={p.age_range ?? ""} onChange={(e) => patch(i, { age_range: e.target.value || null })} placeholder="11-18" />
            </div>
          </li>
        ))}
      </ol>
      {form.programs.length < MAX && (
        <Button onClick={add} className="self-start">
          + Add another program
        </Button>
      )}
    </div>
  );
}
