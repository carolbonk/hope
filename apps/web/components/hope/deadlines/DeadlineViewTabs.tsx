"use client";

import { useRef } from "react";
import { focusRing } from "@/components/hope/ui";

export type DeadlineView = "table" | "calendar";
export const DEADLINE_VIEWS: DeadlineView[] = ["table", "calendar"];

export const tabId = (v: DeadlineView) => `deadlines-tab-${v}`;
export const panelId = (v: DeadlineView) => `deadlines-panel-${v}`;

/** Segmented glass tab switch; the highlight slides between tabs. Arrow keys, Home and End move between tabs. */
export function DeadlineViewTabs({ value, onChange, labels, label }: { value: DeadlineView; onChange: (v: DeadlineView) => void; labels: Record<DeadlineView, string>; label: string }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const index = DEADLINE_VIEWS.indexOf(value);

  const select = (i: number) => {
    const next = DEADLINE_VIEWS[(i + DEADLINE_VIEWS.length) % DEADLINE_VIEWS.length]!;
    onChange(next);
    refs.current[DEADLINE_VIEWS.indexOf(next)]?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    const keys: Record<string, number> = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: DEADLINE_VIEWS.length - 1 };
    if (e.key in keys) {
      e.preventDefault();
      select(keys[e.key]!);
    }
  };

  return (
    <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className="relative inline-grid grid-cols-2 rounded-full glass-panel p-1">
      <span
        aria-hidden
        className="absolute inset-y-1 left-1 rounded-full bg-navy shadow-md transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]"
        style={{ width: `calc((100% - 0.5rem) / ${DEADLINE_VIEWS.length})`, transform: `translateX(${index * 100}%)` }}
      />
      {DEADLINE_VIEWS.map((v, i) => {
        const active = v === value;
        return (
          <button
            key={v}
            ref={(el) => {
              refs.current[i] = el;
            }}
            id={tabId(v)}
            type="button"
            role="tab"
            aria-selected={active}
            aria-controls={panelId(v)}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(v)}
            className={`relative z-10 min-h-10 rounded-full px-4 text-sm sm:px-5 font-semibold transition-colors duration-300 ${focusRing} ${active ? "text-white" : "text-muted hover:text-navy"}`}
          >
            {labels[v]}
          </button>
        );
      })}
    </div>
  );
}
