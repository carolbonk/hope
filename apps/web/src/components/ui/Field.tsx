import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cx } from "@/lib/cx";

const CONTROL =
  "neu-inset neu-focus w-full rounded-xl px-3 py-2 text-sm text-ink placeholder:text-ink-muted disabled:opacity-70";

interface FieldShellProps {
  label: string;
  hint?: ReactNode;
  error?: string;
  className?: string;
  children: (id: string, describedBy: string | undefined) => ReactNode;
}

function FieldShell({ label, hint, error, className, children }: FieldShellProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      {children(id, describedBy)}
      {hint && (
        <p id={hintId} className="text-xs text-ink-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-xs font-semibold text-bad">
          {error}
        </p>
      )}
    </div>
  );
}

type Common = { label: string; hint?: ReactNode; error?: string; wrapperClassName?: string };

export function TextField({ label, hint, error, wrapperClassName, className, ...rest }: Common & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <FieldShell label={label} hint={hint} error={error} className={wrapperClassName}>
      {(id, describedBy) => (
        <input id={id} aria-describedby={describedBy} aria-invalid={!!error || undefined} className={cx(CONTROL, className)} {...rest} />
      )}
    </FieldShell>
  );
}

export function TextArea({ label, hint, error, wrapperClassName, className, ...rest }: Common & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <FieldShell label={label} hint={hint} error={error} className={wrapperClassName}>
      {(id, describedBy) => (
        <textarea id={id} aria-describedby={describedBy} aria-invalid={!!error || undefined} className={cx(CONTROL, "min-h-24", className)} {...rest} />
      )}
    </FieldShell>
  );
}

export function SelectField({
  label,
  hint,
  error,
  wrapperClassName,
  className,
  options,
  ...rest
}: Common & SelectHTMLAttributes<HTMLSelectElement> & { options: readonly { value: string; label: string }[] }) {
  return (
    <FieldShell label={label} hint={hint} error={error} className={wrapperClassName}>
      {(id, describedBy) => (
        <select id={id} aria-describedby={describedBy} className={cx(CONTROL, "appearance-none pr-8", className)} {...rest}>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </FieldShell>
  );
}

/** Segmented single-choice control: the selected segment is pressed (inset). */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1.5 text-sm font-medium text-ink">{label}</legend>
      <div className="neu-inset flex flex-wrap gap-1 rounded-xl p-1">
        {options.map((o) => {
          const active = o.value === value;
          return (
            <button
              key={o.value}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(o.value)}
              className={cx(
                "neu-focus min-h-9 rounded-lg px-3 text-sm font-medium motion-safe:transition-shadow",
                active ? "neu-raised-sm text-accent-strong" : "text-ink-muted hover:text-ink",
              )}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
