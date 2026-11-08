"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { NteeCode, NteeSuggestion, OnboardingApi } from "@/lib/api/onboarding";
import { ProblemError } from "@/lib/api/profile";
import { Badge, Button, Icon } from "@/components/ui";
import { cx } from "@/lib/cx";
import { AutoDismiss } from "@/components/ui/AutoDismiss";

const MAX = 3;

interface NteePickerProps {
  api: OnboardingApi;
  selected: string[];
  labels: Record<string, string>;
  onChange: (codes: string[], labels: Record<string, string>) => void;
  mission: string;
  programs: { name: string; description: string }[];
  error?: string;
}

/** ARIA 1.2 combobox over `GET /v1/profile/ntee-codes`, plus mission-based suggestions. */
export function NteePicker({ api, selected, labels, onChange, mission, programs, error }: NteePickerProps) {
  const id = useId();
  const listId = `${id}-list`;
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NteeCode[]>([]);
  const [active, setActive] = useState(0);
  const [limitMsg, setLimitMsg] = useState<string | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestions, setSuggestions] = useState<NteeSuggestion[] | null>(null);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const cache = useRef(new Map<string, NteeCode[]>());
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const key = q.trim().toLowerCase();
    const hit = cache.current.get(key);
    if (hit) {
      setItems(hit);
      setActive(0);
      return;
    }
    const t = setTimeout(() => {
      api.searchNtee(q, 20).then(
        (res) => {
          cache.current.set(key, res);
          setItems(res);
          setActive(0);
        },
        () => setItems([]),
      );
    }, 200);
    return () => clearTimeout(t);
  }, [q, open, api]);

  const add = (code: NteeCode | { code: string; label: string }) => {
    if (selected.includes(code.code)) return;
    if (selected.length >= MAX) return setLimitMsg("You can pick up to 3 codes.");
    setLimitMsg(null);
    onChange([...selected, code.code], { ...labels, [code.code]: code.label });
  };

  const pick = (item: NteeCode) => {
    const isGroup = item.code.length === 1;
    if (isGroup) {
      setQ(item.code);
      input.current?.focus();
      return;
    }
    add(item);
    setQ("");
    setOpen(false);
  };

  const remove = (code: string) => {
    setLimitMsg(null);
    onChange(
      selected.filter((c) => c !== code),
      labels,
    );
  };

  const move = (i: number, dir: -1 | 1) => {
    const next = [...selected];
    const a = next[i]!;
    next[i] = next[i + dir]!;
    next[i + dir] = a;
    onChange(next, labels);
  };

  const suggest = async () => {
    setSuggesting(true);
    setSuggestError(null);
    try {
      const res = await api.suggestNtee({ mission_statement: mission, programs: programs.filter((p) => p.name && p.description) });
      if (res.error) setSuggestError("Suggestions aren't available right now. Search instead.");
      else setSuggestions(res.suggestions);
    } catch (err) {
      setSuggestError(err instanceof ProblemError && err.code === "rate_limited" ? "Too many requests. Try again in a minute." : "Suggestions aren't available right now. Search instead.");
    } finally {
      setSuggesting(false);
    }
  };

  const message = limitMsg ?? error;
  const activeId = open && items[active] ? `${id}-opt-${items[active].code}` : undefined;

  return (
    <div className="flex flex-col gap-4">
      <div className="relative flex flex-col gap-1.5">
        <label htmlFor={id} className="text-sm font-medium text-ink">
          What kind of nonprofit are you? <span aria-hidden="true">*</span>
        </label>
        <p id={`${id}-hint`} className="text-xs text-ink-muted">
          Pick up to 3 NTEE codes. The first is your primary.
        </p>
        <div className="relative">
          <Icon name="eye" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" />
          <input
            ref={input}
            id={id}
            role="combobox"
            aria-expanded={open}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={activeId}
            aria-required
            aria-invalid={!!message || undefined}
            aria-describedby={`${id}-hint${message ? ` ${id}-err` : ""}`}
            value={q}
            placeholder='Search codes or words, e.g. "clinic" or E32'
            onChange={(e) => {
              setQ(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setOpen(true);
                setActive((a) => Math.min(a + 1, items.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((a) => Math.max(a - 1, 0));
              } else if (e.key === "Enter") {
                if (open && items[active]) {
                  e.preventDefault();
                  e.stopPropagation();
                  pick(items[active]);
                }
              } else if (e.key === "Escape") setOpen(false);
            }}
            className="glass-inset glass-focus w-full rounded-xl py-2 pl-9 pr-3 text-sm text-ink placeholder:text-ink-muted"
          />
        </div>
        {open && (
          <ul id={listId} role="listbox" aria-label="NTEE codes" className="glass-chrome absolute top-full z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-xl p-1">
            {items.length === 0 && q.trim() ? (
              <li className="px-3 py-2 text-sm text-ink-muted">No codes match &ldquo;{q}&rdquo;. Try a broader word like &ldquo;health&rdquo; or &ldquo;youth&rdquo;.</li>
            ) : (
              items.map((item, i) => (
                <li
                  key={item.code}
                  id={`${id}-opt-${item.code}`}
                  role="option"
                  aria-selected={i === active}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => pick(item)}
                  onMouseEnter={() => setActive(i)}
                  className={cx("flex cursor-pointer items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm", i === active && "glass-active")}
                >
                  <span>
                    <span className="font-semibold">{item.code}</span> {item.label}
                  </span>
                  <span className="text-xs text-ink-muted">{item.code.length === 1 ? "Group" : item.group_label}</span>
                </li>
              ))
            )}
          </ul>
        )}
        {message && (
          <AutoDismiss key={message}>
            <p id={`${id}-err`} role="alert" className="text-xs font-semibold text-bad">
              {message}
            </p>
          </AutoDismiss>
        )}
      </div>

      <div>
        <h3 className="text-sm font-medium text-ink">Selected</h3>
        {selected.length === 0 ? (
          <p className="mt-1 text-sm text-ink-muted">No codes yet.</p>
        ) : (
          <ol className="mt-2 flex flex-col gap-2" aria-label="Selected NTEE codes">
            {selected.map((code, i) => {
              const name = `${code} ${labels[code] ?? ""}`.trim();
              return (
                <li key={code} className="glass-control flex items-center gap-2 rounded-xl px-3 py-2 text-sm">
                  <span className="glass-inset flex size-6 items-center justify-center rounded-full text-xs font-bold">{i + 1}</span>
                  <span className="flex-1">
                    <span className="font-semibold">{code}</span> {labels[code]}
                    {i === 0 && <span className="ml-2 text-xs text-ink-muted">Primary</span>}
                  </span>
                  <button type="button" aria-label={`Move ${name} up`} disabled={i === 0} onClick={() => move(i, -1)} className="glass-focus rounded-lg p-1 text-ink-muted hover:text-ink disabled:opacity-30">
                    <Icon name="up" className="size-4" />
                  </button>
                  <button type="button" aria-label={`Move ${name} down`} disabled={i === selected.length - 1} onClick={() => move(i, 1)} className="glass-focus rotate-180 rounded-lg p-1 text-ink-muted hover:text-ink disabled:opacity-30">
                    <Icon name="up" className="size-4" />
                  </button>
                  <button type="button" aria-label={`Remove ${name}`} onClick={() => remove(code)} className="glass-focus rounded-lg p-1 text-ink-muted hover:text-ink">
                    <Icon name="x" className="size-4" />
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </div>

      <div className="glass-inset rounded-2xl p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm font-medium text-ink">Suggested from your mission</p>
          <Button onClick={suggest} disabled={suggesting || mission.trim().length < 20}>
            {suggesting ? "Suggesting…" : "Suggest codes"}
          </Button>
        </div>
        {suggestError && (
          <AutoDismiss key={suggestError}>
            <p role="alert" className="mt-2 text-sm text-warn">
              {suggestError}
            </p>
          </AutoDismiss>
        )}
        {suggestions && suggestions.length === 0 && <p className="mt-2 text-sm text-ink-muted">No suggestions for this mission. Search instead.</p>}
        {suggestions && suggestions.length > 0 && (
          <ul className="mt-3 flex flex-col gap-2" aria-label="Suggested NTEE codes">
            {suggestions.map((s) => {
              const added = selected.includes(s.code);
              return (
                <li key={s.code} className="glass-control flex flex-wrap items-center gap-2 rounded-xl px-3 py-2 text-sm">
                  <span className="flex-1">
                    <span className="font-semibold">{s.code}</span> {s.label} — {s.reason}
                    {s.citation && (
                      <span title={`From your ${s.citation.profile_path}`} className="ml-1 inline-flex items-center rounded-full border border-accent/40 px-1.5 text-xs text-accent-strong">
                        &ldquo;{s.citation.quote}&rdquo; [{s.citation.citation_id}]
                      </span>
                    )}
                    {!s.verified && (
                      <span title="Hope couldn't find this phrase in your text." className="ml-2">
                        <Badge tone="warn" icon="alert">
                          Unverified
                        </Badge>
                      </span>
                    )}
                  </span>
                  <Button disabled={added} onClick={() => add(s)} aria-label={added ? `${s.code} added` : `Add ${s.code} ${s.label}`}>
                    {added ? "Added" : "Add"}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
