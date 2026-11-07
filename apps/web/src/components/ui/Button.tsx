import type { ButtonHTMLAttributes } from "react";
import { cx } from "@/lib/cx";

export type ButtonVariant = "primary" | "neutral" | "danger" | "ghost";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "!bg-accent/90 !border-accent-strong/40 text-white hover:!bg-accent-strong",
  neutral: "text-ink",
  danger: "text-bad",
  ghost: "text-ink-muted border border-transparent shadow-none bg-transparent hover:bg-white/40",
};

export function Button({
  variant = "neutral",
  pressed,
  className,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; pressed?: boolean }) {
  return (
    <button
      type={type}
      aria-pressed={pressed}
      className={cx(
        "glass-focus inline-flex min-h-10 items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold",
        "motion-safe:transition-[background-color,box-shadow] motion-safe:duration-150",
        "disabled:cursor-not-allowed disabled:opacity-60",
        pressed ? "glass-active" : variant === "ghost" ? "" : "glass-control active:glass-active",
        VARIANTS[variant],
        className,
      )}
      {...rest}
    />
  );
}
