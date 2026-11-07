"use client";

import { useId, useState, type KeyboardEvent } from "react";
import { Icon } from "@/components/ui";
import { cx } from "@/lib/cx";

interface TagInputProps {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  max: number;
  minLength?: number;
  maxLength: number;
  placeholder?: string;
  hint?: string;
  error?: string;
  required?: boolean;
  quickPicks?: string[];
}

/** Free-text tags: Enter or comma adds, Backspace on empty input removes the last one. */
export function TagInput({ label, values, onChange, max, minLength = 2, maxLength, placeholder, hint, error, required, quickPicks = [] }: TagInputProps) {
  const id = useId();
  const [draft, setDraft] = useState("");
  const [local, setLocal] = useState<string | null>(null);
  const message = local ?? error;
  const describedBy = [hint && `${id}-hint`, message && `${id}-err`].filter(Boolean).join(" ") || undefined;

  const add = (raw: string) => {
    const v = raw.trim().replace(/,$/, "");
    if (!v) return;
    if (values.length >= max) return setLocal(`You can add up to ${max}.`);
    if (v.length < minLength || v.length > maxLength) return setLocal(`Each entry needs ${minLength}-${maxLength} characters.`);
    if (values.some((x) => x.toLowerCase() === v.toLowerCase())) return setLocal(`"${v}" is already added.`);
    onChange([...values, v]);
    setDraft("");
    setLocal(null);
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      if (!draft.trim()) return;
      e.preventDefault();
      e.stopPropagation();
      add(draft);
    } else if (e.key === "Backspace" && !draft && values.length) onChange(values.slice(0, -1));
  };

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
        {required ? <span aria-hidden="true"> *</span> : <span className="font-normal text-ink-muted"> (optional)</span>}
      </label>
      <div className="glass-inset flex flex-wrap items-center gap-1.5 rounded-xl p-1.5">
        <ul className="contents" aria-label={`${label} added`}>
          {values.map((v) => (
            <li key={v} className="glass-control flex items-center gap-1 rounded-full py-1 pl-3 pr-1 text-sm">
              {v}
              <button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(values.filter((x) => x !== v))} className="glass-focus rounded-full p-1 text-ink-muted hover:text-ink">
                <Icon name="x" className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
        <input
          id={id}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setLocal(null);
          }}
          onKeyDown={onKey}
          onBlur={() => draft.trim() && add(draft)}
          placeholder={values.length ? "" : placeholder}
          aria-required={required || undefined}
          aria-invalid={!!message || undefined}
          aria-describedby={describedBy}
          className="glass-focus min-w-40 flex-1 rounded-lg bg-transparent px-2 py-1.5 text-sm text-ink placeholder:text-ink-muted"
        />
      </div>
      {quickPicks.filter((q) => !values.includes(q)).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {quickPicks
            .filter((q) => !values.includes(q))
            .map((q) => (
              <button key={q} type="button" onClick={() => add(q)} className={cx("glass-focus glass-control rounded-full px-3 py-1 text-xs font-medium text-accent-strong")}>
                + {q}
              </button>
            ))}
        </div>
      )}
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-ink-muted">
          {hint}
        </p>
      )}
      {message && (
        <p id={`${id}-err`} role="alert" className="text-xs font-semibold text-bad">
          {message}
        </p>
      )}
    </div>
  );
}
