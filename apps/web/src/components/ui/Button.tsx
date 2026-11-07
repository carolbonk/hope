import type { ButtonHTMLAttributes } from "react";
import { cx } from "@/lib/cx";

export type ButtonVariant = "primary" | "neutral" | "danger" | "ghost";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "text-accent-strong",
  neutral: "text-ink",
  danger: "text-bad",
  ghost: "text-ink-muted shadow-none bg-transparent",
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
        "neu-focus inline-flex min-h-10 items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold",
        "motion-safe:transition-shadow motion-safe:duration-150",
        "disabled:cursor-not-allowed disabled:opacity-60",
        pressed ? "neu-pressed" : variant === "ghost" ? "" : "neu-raised-sm active:neu-pressed",
        VARIANTS[variant],
        className,
      )}
      {...rest}
    />
  );
}
