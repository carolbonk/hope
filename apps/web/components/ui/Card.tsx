import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "@/lib/cx";

export function Card({ className, ...rest }: HTMLAttributes<HTMLElement>) {
  return <section className={cx("glass-panel rounded-[var(--radius-glass)] p-5 sm:p-6", className)} {...rest} />;
}

export function Well({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("glass-inset rounded-2xl p-4", className)} {...rest} />;
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-ink-muted">{description}</p>}
      </div>
      {actions}
    </header>
  );
}
