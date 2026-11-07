"use client";

import { useId, useRef, useState, type KeyboardEvent } from "react";
import type { BudgetBand } from "@/api/profile";
import { SelectField, TextField } from "@/components/ui";
import { cx } from "@/lib/cx";
import { bandFor, bandLabel, BUDGET_BANDS } from "../model";
import type { StepProps } from "./types";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = Array.from({ length: 31 }, (_, i) => String(i + 1).padStart(2, "0"));
const usd = new Intl.NumberFormat("en-US");

export function BudgetStep({ form, set, errors }: StepProps) {
  const bud = form.budget;
  const id = useId();
  const [warning, setWarning] = useState<string | null>(null);
  const [amountText, setAmountText] = useState(bud.annual_operating_budget_usd == null ? "" : usd.format(bud.annual_operating_budget_usd));
  const radios = useRef<(HTMLButtonElement | null)[]>([]);
  const patch = (p: Partial<typeof bud>) => set((f) => ({ ...f, budget: { ...f.budget, ...p } }));
  const [month, day] = bud.fiscal_year_end.split("-");

  const choose = (band: BudgetBand) => {
    setWarning(null);
    patch({ budget_band: band });
  };

  const onRadioKey = (e: KeyboardEvent, i: number) => {
    const dir = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    const next = (i + dir + BUDGET_BANDS.length) % BUDGET_BANDS.length;
    choose(BUDGET_BANDS[next]!.value);
    radios.current[next]?.focus();
  };

  const onAmountBlur = () => {
    const digits = amountText.replace(/[^\d]/g, "");
    if (!digits) {
      patch({ annual_operating_budget_usd: null });
      setWarning(null);
      return;
    }
    const value = Number(digits);
    setAmountText(usd.format(value));
    const band = bandFor(value);
    if (bud.budget_band && band !== bud.budget_band) setWarning(`This amount is in the ${bandLabel(band)} band.`);
    else setWarning(null);
    patch({ annual_operating_budget_usd: value, budget_band: band });
  };

  const checked = bud.budget_band;
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <p id={`${id}-label`} className="text-sm font-medium text-ink">
          Annual operating budget <span aria-hidden="true">*</span>
        </p>
        <div role="radiogroup" aria-labelledby={`${id}-label`} aria-required aria-invalid={!!errors["budget.budget_band"] || undefined} className="glass-inset flex flex-wrap gap-1 rounded-xl p-1">
          {BUDGET_BANDS.map((b, i) => {
            const on = checked === b.value;
            return (
              <button
                key={b.value}
                ref={(el) => {
                  radios.current[i] = el;
                }}
                type="button"
                role="radio"
                aria-checked={on}
                tabIndex={on || (!checked && i === 0) ? 0 : -1}
                onClick={() => choose(b.value)}
                onKeyDown={(e) => onRadioKey(e, i)}
                className={cx("glass-focus min-h-10 flex-1 rounded-lg border px-3 text-sm font-medium", on ? "glass-active text-accent-strong" : "border-transparent text-ink-muted hover:text-ink")}
              >
                {b.label}
              </button>
            );
          })}
        </div>
        {errors["budget.budget_band"] && (
          <p role="alert" className="text-xs font-semibold text-bad">
            {errors["budget.budget_band"]}
          </p>
        )}
      </div>
      <TextField
        label="Exact budget (optional)"
        inputMode="numeric"
        value={amountText}
        onChange={(e) => setAmountText(e.target.value)}
        onBlur={onAmountBlur}
        placeholder="$3,120,000"
        hint={warning ?? "Whole dollars. Leave blank to use the band."}
      />
      <div className="grid max-w-sm grid-cols-2 gap-3">
        <SelectField label="Fiscal year ends" value={month} onChange={(e) => patch({ fiscal_year_end: `${e.target.value}-${day}` })} options={MONTHS.map((m, i) => ({ value: String(i + 1).padStart(2, "0"), label: m }))} />
        <SelectField label="Day" value={day} onChange={(e) => patch({ fiscal_year_end: `${month}-${e.target.value}` })} options={DAYS.map((d) => ({ value: d, label: String(Number(d)) }))} />
      </div>
    </div>
  );
}
