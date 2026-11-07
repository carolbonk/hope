"use client";

import type { ReactNode } from "react";
import { bandLabel, stateName, STEPS, TAX_STATUSES, type Errors, type StepId } from "../model";
import type { StepProps } from "./types";

function Section({ title, step, onEdit, disabled, children }: { title: string; step: StepId; onEdit: (s: StepId) => void; disabled: boolean; children: ReactNode }) {
  return (
    <section className="glass-inset rounded-2xl p-4" aria-labelledby={`review-${step}`}>
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 id={`review-${step}`} className="text-sm font-semibold text-ink">
          {title}
        </h2>
        <button type="button" disabled={disabled} onClick={() => onEdit(step)} className="glass-focus rounded-lg px-2 py-1 text-sm font-semibold text-accent-strong underline-offset-2 hover:underline disabled:opacity-50" aria-label={`Edit ${title}`}>
          Edit
        </button>
      </div>
      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">{children}</dl>
    </section>
  );
}

const Row = ({ k, v }: { k: string; v: ReactNode }) => (
  <>
    <dt className="text-ink-muted">{k}</dt>
    <dd className="text-ink">{v || <span className="text-ink-muted">—</span>}</dd>
  </>
);

export function ReviewStep({ form, errors, labels, onEdit, saving }: StepProps & { labels: Record<string, string>; onEdit: (s: StepId) => void; saving: boolean }) {
  const b = form.basics;
  const count = Object.keys(errors).length;
  const errorSteps = [...new Set(Object.keys(errors).map((f) => STEPS.find((s) => f.startsWith(s.id === "cause" ? "ntee_codes" : s.id))?.id))].filter(Boolean) as StepId[];
  return (
    <div className="flex flex-col gap-3">
      {count > 0 && <ErrorSummary count={count} steps={errorSteps} errors={errors} onEdit={onEdit} />}
      <Section title="Basics" step="basics" onEdit={onEdit} disabled={saving}>
        <Row k="Legal name" v={b.legal_name} />
        <Row k="EIN" v={b.ein} />
        <Row k="Tax status" v={TAX_STATUSES.find((t) => t.value === b.tax_status)?.label} />
        <Row k="Headquarters" v={b.hq_city && `${b.hq_city}, ${stateName(b.hq_state)}`} />
        <Row k="Service area" v={b.service_area.join(" · ")} />
        <Row k="Website" v={b.website} />
      </Section>
      <Section title="Mission and values" step="mission" onEdit={onEdit} disabled={saving}>
        <Row k="Mission" v={form.mission.mission_statement} />
        <Row k="Vision" v={form.mission.vision_statement} />
        <Row k="Values" v={form.mission.values.join(" · ")} />
      </Section>
      <Section title="Cause" step="cause" onEdit={onEdit} disabled={saving}>
        <Row k="NTEE codes" v={form.ntee_codes.map((c, i) => `${i + 1}. ${c} ${labels[c] ?? ""}`).join("  ")} />
      </Section>
      <Section title="Budget" step="budget" onEdit={onEdit} disabled={saving}>
        <Row k="Band" v={bandLabel(form.budget.budget_band)} />
        <Row k="Exact budget" v={form.budget.annual_operating_budget_usd != null && `$${form.budget.annual_operating_budget_usd.toLocaleString("en-US")}`} />
        <Row k="Fiscal year ends" v={form.budget.fiscal_year_end} />
      </Section>
      <Section title="Programs" step="programs" onEdit={onEdit} disabled={saving}>
        {form.programs.map((p, i) => (
          <Row key={i} k={p.name || `Program ${i + 1}`} v={`${p.people_served}${p.annual_served ? ` · ${p.annual_served.toLocaleString("en-US")} a year` : ""}`} />
        ))}
      </Section>
    </div>
  );
}

function ErrorSummary({ count, steps, errors, onEdit }: { count: number; steps: StepId[]; errors: Errors; onEdit: (s: StepId) => void }) {
  return (
    <div role="alert" className="glass-inset rounded-2xl border-l-4 border-bad p-4 text-sm">
      <p className="font-semibold text-bad">Fix {count} {count === 1 ? "item" : "items"} before finishing.</p>
      <ul className="mt-2 list-disc pl-5">
        {Object.entries(errors).map(([field, msg]) => (
          <li key={field}>{msg}</li>
        ))}
      </ul>
      <div className="mt-2 flex flex-wrap gap-2">
        {steps.map((s) => (
          <button key={s} type="button" onClick={() => onEdit(s)} className="glass-focus rounded-lg px-2 py-1 font-semibold text-accent-strong underline">
            Go to {STEPS.find((x) => x.id === s)?.title}
          </button>
        ))}
      </div>
    </div>
  );
}
