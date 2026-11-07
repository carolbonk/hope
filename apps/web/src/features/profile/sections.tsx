"use client";

import type { AgencyProfile, ApprovalRule, Gate, Legal } from "@hope/schemas";
import { useState } from "react";
import type { ProfilePatch, ProfilePatchResult } from "@/api/types";
import { SelectField, TextArea, TextField } from "@/components/ui";
import { minorToMajorString, parseMajorToMinor } from "@/lib/money";
import { SectionShell } from "./SectionShell";

export interface SectionProps {
  profile: AgencyProfile;
  submit: (patch: ProfilePatch) => Promise<ProfilePatchResult>;
  onConflict: () => void;
}

/** Draft state seeded from the profile, with dirty tracking against the original. */
function useDraft<T>(initial: () => T) {
  const [original] = useState(initial);
  const [draft, setDraft] = useState(original);
  const set = <K extends keyof T>(key: K, value: T[K]) => setDraft((d) => ({ ...d, [key]: value }));
  return { draft, set, setDraft, dirty: JSON.stringify(draft) !== JSON.stringify(original), reset: () => setDraft(original) };
}

const list = (s: string) =>
  s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

const GRID = "grid gap-4 sm:grid-cols-2";

export function MissionSection({ profile, submit, onConflict }: SectionProps) {
  const m = profile.mission;
  const { draft, set, dirty, reset } = useDraft(() => ({
    mission: m.mission_statement,
    vision: m.vision_statement ?? "",
    focus: (m.focus_areas ?? []).join(", "),
  }));
  return (
    <SectionShell
      section="mission"
      title="Mission"
      description="Used by the Mission Alignment Evaluator to score every opportunity."
      dirty={dirty}
      onReset={reset}
      onConflict={onConflict}
      submit={submit}
      buildPatch={() =>
        draft.mission.trim()
          ? { mission: { ...m, mission_statement: draft.mission.trim(), vision_statement: draft.vision.trim() || null, focus_areas: list(draft.focus) } }
          : "Mission statement is required."
      }
    >
      <div className="flex flex-col gap-4">
        <TextArea label="Mission statement" value={draft.mission} maxLength={2000} onChange={(e) => set("mission", e.target.value)} />
        <TextArea label="Vision statement" value={draft.vision} maxLength={2000} rows={2} onChange={(e) => set("vision", e.target.value)} />
        <TextField label="Focus areas" hint="Comma-separated" value={draft.focus} onChange={(e) => set("focus", e.target.value)} />
      </div>
    </SectionShell>
  );
}

export function CapacitySection({ profile, submit, onConflict }: SectionProps) {
  const c = profile.capacity ?? {};
  const { draft, set, dirty, reset } = useDraft(() => ({
    fte: String(c.grant_writer_fte ?? ""),
    hours: String(c.monthly_hours_available ?? ""),
    concurrent: String(c.max_concurrent_applications ?? ""),
  }));
  const num = (s: string) => (s.trim() === "" ? null : Number(s));
  return (
    <SectionShell
      section="capacity"
      title="Capacity"
      description="Drives the capacity-fit column in the matrix."
      dirty={dirty}
      onReset={reset}
      onConflict={onConflict}
      submit={submit}
      buildPatch={() => {
        const values = [num(draft.fte), num(draft.hours), num(draft.concurrent)];
        if (values.some((v) => v !== null && (Number.isNaN(v) || v < 0))) return "Capacity values must be non-negative numbers.";
        const [fte, hours, concurrent] = values;
        return { capacity: { ...c, grant_writer_fte: fte, monthly_hours_available: hours, max_concurrent_applications: concurrent } };
      }}
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <TextField label="Grant writer FTE" inputMode="decimal" value={draft.fte} onChange={(e) => set("fte", e.target.value)} />
        <TextField label="Monthly hours available" inputMode="numeric" value={draft.hours} onChange={(e) => set("hours", e.target.value)} />
        <TextField label="Max concurrent applications" inputMode="numeric" value={draft.concurrent} onChange={(e) => set("concurrent", e.target.value)} />
      </div>
    </SectionShell>
  );
}

const TAX_STATUS: { value: Legal["tax_status"]; label: string }[] = [
  { value: "501c3_public_charity", label: "501(c)(3) public charity" },
  { value: "501c3_private_foundation", label: "501(c)(3) private foundation" },
  { value: "501c4", label: "501(c)(4)" },
  { value: "501c6", label: "501(c)(6)" },
  { value: "fiscally_sponsored", label: "Fiscally sponsored" },
  { value: "government", label: "Government" },
  { value: "tribal", label: "Tribal" },
  { value: "other", label: "Other" },
];

export function LegalSection({ profile, submit, onConflict }: SectionProps) {
  const l = profile.legal;
  const { draft, set, dirty, reset } = useDraft(() => ({
    legal_name: l.legal_name,
    ein: l.ein,
    uei: l.uei ?? "",
    state: l.state_of_incorporation ?? "",
    tax_status: l.tax_status,
  }));
  const einError = /^\d{2}-\d{7}$/.test(draft.ein) ? undefined : "Use the format 12-3456789.";
  const ueiError = draft.uei === "" || /^[A-Z0-9]{12}$/.test(draft.uei) ? undefined : "UEI is 12 letters or digits.";
  return (
    <SectionShell
      section="legal"
      title="Legal identity"
      description="Legal name, EIN and registrations used on federal forms such as the SF-424."
      dirty={dirty}
      onReset={reset}
      onConflict={onConflict}
      submit={submit}
      buildPatch={() =>
        einError ?? ueiError ?? (draft.legal_name.trim()
          ? {
              legal: {
                ...l,
                legal_name: draft.legal_name.trim(),
                ein: draft.ein,
                uei: draft.uei || null,
                state_of_incorporation: draft.state || null,
                tax_status: draft.tax_status,
              },
            }
          : "Legal name is required.")
      }
    >
      <div className={GRID}>
        <TextField label="Legal name" value={draft.legal_name} onChange={(e) => set("legal_name", e.target.value)} />
        <SelectField
          label="Tax status"
          value={draft.tax_status}
          options={TAX_STATUS}
          onChange={(e) => set("tax_status", e.target.value as Legal["tax_status"])}
        />
        <TextField label="EIN" value={draft.ein} error={einError} onChange={(e) => set("ein", e.target.value)} />
        <TextField label="UEI" value={draft.uei} error={ueiError} onChange={(e) => set("uei", e.target.value.toUpperCase())} />
        <TextField label="State of incorporation" maxLength={2} value={draft.state} onChange={(e) => set("state", e.target.value.toUpperCase())} />
      </div>
    </SectionShell>
  );
}

const pct = (bps: number | null | undefined) => (bps == null ? "" : minorToMajorString(bps));

export function FinancialsSection({ profile, submit, onConflict }: SectionProps) {
  const f = profile.financials;
  const { draft, set, dirty, reset } = useDraft(() => ({
    budget: minorToMajorString(f.annual_operating_budget.amount_minor),
    fye: f.fiscal_year_end,
    fringe: pct(f.fringe_rate_bps),
    indirect: pct(f.indirect_rate?.rate_bps),
  }));
  return (
    <SectionShell
      section="financials"
      title="Financials"
      description="Feeds the Budget Engine. Amounts are stored as integer cents and rates as basis points."
      dirty={dirty}
      onReset={reset}
      onConflict={onConflict}
      submit={submit}
      buildPatch={() => {
        const budget = parseMajorToMinor(draft.budget);
        if (budget === null) return "Annual operating budget must be a dollar amount, e.g. 3,120,000.";
        if (!/^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/.test(draft.fye)) return "Fiscal year end must be MM-DD.";
        // Percent with up to 2 decimals maps exactly to basis points via the same integer parser.
        const fringe = draft.fringe ? parseMajorToMinor(draft.fringe) : null;
        const indirect = draft.indirect ? parseMajorToMinor(draft.indirect) : null;
        if ((draft.fringe && fringe === null) || (draft.indirect && indirect === null)) return "Rates must be percentages, e.g. 18.20.";
        return {
          financials: {
            ...f,
            annual_operating_budget: { ...f.annual_operating_budget, amount_minor: budget },
            fiscal_year_end: draft.fye,
            fringe_rate_bps: fringe,
            indirect_rate: f.indirect_rate ? { ...f.indirect_rate, rate_bps: indirect } : f.indirect_rate,
          },
        };
      }}
    >
      <div className={GRID}>
        <TextField label="Annual operating budget (USD)" inputMode="decimal" value={draft.budget} onChange={(e) => set("budget", e.target.value)} />
        <TextField label="Fiscal year end (MM-DD)" value={draft.fye} onChange={(e) => set("fye", e.target.value)} />
        <TextField label="Fringe rate (%)" inputMode="decimal" value={draft.fringe} onChange={(e) => set("fringe", e.target.value)} />
        <TextField
          label="Indirect rate (%)"
          inputMode="decimal"
          hint={f.indirect_rate ? `${f.indirect_rate.type.replace(/_/g, " ")}, base ${f.indirect_rate.base ?? "—"}` : undefined}
          value={draft.indirect}
          onChange={(e) => set("indirect", e.target.value)}
        />
      </div>
    </SectionShell>
  );
}

interface RuleDraft {
  gate: Gate;
  roles: string;
  sla: string;
  escalate: string;
}

export function ApprovalHierarchySection({ profile, submit, onConflict }: SectionProps) {
  const rules = profile.approval_hierarchy;
  const { draft, setDraft, dirty, reset } = useDraft<RuleDraft[]>(() =>
    rules.map((r) => ({ gate: r.gate, roles: r.approver_roles.join(", "), sla: String(r.sla_hours ?? ""), escalate: r.escalate_to_role ?? "" })),
  );
  const update = (i: number, patch: Partial<RuleDraft>) => setDraft((d) => d.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <SectionShell
      section="approval_hierarchy"
      title="Approval hierarchy"
      description="Who approves each gate, how long they have, and who it escalates to."
      dirty={dirty}
      onReset={reset}
      onConflict={onConflict}
      submit={submit}
      buildPatch={() => {
        const next = draft.map((d, i): ApprovalRule | string => {
          const roles = list(d.roles);
          const [first, ...rest] = roles;
          if (!first) return `${d.gate} needs at least one approver role.`;
          if (d.sla && !/^\d+$/.test(d.sla)) return `${d.gate} SLA must be whole hours.`;
          return { ...rules[i], gate: d.gate, approver_roles: [first, ...rest], sla_hours: d.sla ? Number(d.sla) : null, escalate_to_role: d.escalate || null };
        });
        const problem = next.find((r): r is string => typeof r === "string");
        if (problem) return problem;
        const [head, ...tail] = next as ApprovalRule[];
        return head ? { approval_hierarchy: [head, ...tail] } : "At least one rule is required.";
      }}
    >
      <div className="flex flex-col gap-3">
        {draft.map((r, i) => (
          <fieldset key={r.gate} className="neu-inset grid gap-3 rounded-2xl p-4 sm:grid-cols-[6rem_2fr_1fr_1.5fr] sm:items-end">
            <legend className="sr-only">{r.gate} rule</legend>
            <p className="text-sm font-bold text-accent-strong sm:pb-2.5">{r.gate}</p>
            <TextField label="Approver roles" value={r.roles} onChange={(e) => update(i, { roles: e.target.value })} />
            <TextField label="SLA (hours)" inputMode="numeric" value={r.sla} onChange={(e) => update(i, { sla: e.target.value })} />
            <TextField label="Escalate to" value={r.escalate} onChange={(e) => update(i, { escalate: e.target.value })} />
          </fieldset>
        ))}
      </div>
    </SectionShell>
  );
}
