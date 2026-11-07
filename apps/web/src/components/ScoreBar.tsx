import { cx } from "@/lib/cx";

/** Inset track with a raised fill; the number is always shown as text too. */
export function ScoreBar({ label, value, max = 100, compact }: { label: string; value: number; max?: number; compact?: boolean }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const shown = max === 1 ? `${Math.round(value * 100)}%` : String(Math.round(value));
  return (
    <div className={cx("flex items-center gap-2", compact ? "text-xs" : "text-sm")}>
      <span className={cx("shrink-0 text-ink-muted", compact ? "w-20" : "w-40")}>{label}</span>
      <div
        className="glass-inset h-2.5 flex-1 rounded-full"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-valuetext={shown}
      >
        <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-10 shrink-0 text-right font-semibold tabular-nums text-ink">{shown}</span>
    </div>
  );
}
