import type { ReactNode } from "react";
import { Button } from "./Button";
import { Icon } from "./Icon";
import { AutoDismiss } from "./AutoDismiss";

export function Loading({ label }: { label: string }) {
  return (
    <p role="status" className="glass-inset rounded-2xl p-6 text-center text-sm text-ink-muted">
      {label}
    </p>
  );
}

export function ErrorNotice({ title, children, onRetry }: { title: string; children: ReactNode; onRetry?: () => void }) {
  return (
    <div role="alert" className="glass-inset flex flex-wrap items-start gap-3 rounded-2xl border-l-4 border-bad p-4 text-sm">
      <Icon name="alert" className="mt-0.5 size-5 shrink-0 text-bad" />
      <div className="flex-1">
        <p className="font-semibold text-bad">{title}</p>
        <div className="mt-1 text-ink">{children}</div>
      </div>
      {onRetry && (
        <Button onClick={onRetry} variant="neutral">
          Reload
        </Button>
      )}
    </div>
  );
}

export function SuccessNotice({ children }: { children: ReactNode }) {
  return (
    <AutoDismiss>
      <div role="status" className="glass-inset flex items-start gap-3 rounded-2xl border-l-4 border-good p-4 text-sm text-ink">
        <Icon name="check" className="mt-0.5 size-5 shrink-0 text-good" />
        <div>{children}</div>
      </div>
    </AutoDismiss>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="glass-inset rounded-2xl p-8 text-center text-sm text-ink-muted">{children}</p>;
}
