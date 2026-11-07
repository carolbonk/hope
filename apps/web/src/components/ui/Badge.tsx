import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { Icon, type IconName } from "./Icon";

export type Tone = "good" | "info" | "warn" | "bad" | "neutral";

const TONES: Record<Tone, string> = {
  good: "text-good border-good",
  info: "text-info border-info",
  warn: "text-warn border-warn",
  bad: "text-bad border-bad",
  neutral: "text-neutral border-neutral",
};

/** Status chip: colour is always paired with a border and an icon, never colour alone. */
export function Badge({ tone, icon, children, className }: { tone: Tone; icon: IconName; children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        "neu-raised-sm inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        TONES[tone],
        className,
      )}
    >
      <Icon name={icon} className="size-3.5" />
      {children}
    </span>
  );
}
