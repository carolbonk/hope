"use client";

import { SelectField, TextField } from "@/components/ui";
import { TagInput } from "../TagInput";
import { formatEin, stateName, TAX_STATUSES, US_STATES } from "../model";
import type { StepProps } from "./types";

export function BasicsStep({ form, set, errors }: StepProps) {
  const b = form.basics;
  const patch = (p: Partial<typeof b>) => set((f) => ({ ...f, basics: { ...f.basics, ...p } }));
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <TextField
        wrapperClassName="sm:col-span-2"
        label="Legal name *"
        aria-required
        autoComplete="organization"
        value={b.legal_name}
        onChange={(e) => patch({ legal_name: e.target.value })}
        error={errors["basics.legal_name"]}
        placeholder="Riverbend Community Health Alliance"
      />
      <TextField
        label="EIN *"
        aria-required
        inputMode="numeric"
        value={b.ein}
        onChange={(e) => patch({ ein: formatEin(e.target.value) })}
        error={errors["basics.ein"]}
        placeholder="12-3456789"
        hint="Your 9-digit IRS employer ID."
      />
      <SelectField
        label="Tax status"
        value={b.tax_status}
        onChange={(e) => patch({ tax_status: e.target.value as typeof b.tax_status })}
        options={TAX_STATUSES}
      />
      <TextField label="City *" aria-required value={b.hq_city} onChange={(e) => patch({ hq_city: e.target.value })} error={errors["basics.hq_city"]} placeholder="Wenatchee" />
      <SelectField
        label="State *"
        aria-required
        value={b.hq_state}
        onChange={(e) => patch({ hq_state: e.target.value })}
        error={errors["basics.hq_state"]}
        options={[{ value: "", label: "Choose a state" }, ...US_STATES.map(([value, name]) => ({ value, label: `${value} – ${name}` }))]}
      />
      <div className="sm:col-span-2">
        <TagInput
          label="Service area"
          required
          values={b.service_area}
          onChange={(service_area) => patch({ service_area })}
          max={20}
          maxLength={80}
          placeholder='Type a county, city or state and press Enter, e.g. "Chelan County, WA"'
          error={errors["basics.service_area"]}
          quickPicks={[...(b.hq_state ? [stateName(b.hq_state)] : []), "Nationwide"]}
        />
      </div>
      <TextField
        wrapperClassName="sm:col-span-2"
        label="Website (optional)"
        type="url"
        inputMode="url"
        value={b.website ?? ""}
        onChange={(e) => patch({ website: e.target.value || null })}
        onBlur={(e) => {
          const v = e.target.value.trim();
          if (v && !/^https?:\/\//i.test(v)) patch({ website: `https://${v}` });
        }}
        placeholder="https://yourorg.org"
      />
    </div>
  );
}
