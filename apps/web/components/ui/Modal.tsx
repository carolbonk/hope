"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { cx } from "@/lib/cx";
import { Button } from "./Button";
import { Icon } from "./Icon";

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])';

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  variant?: "dialog" | "drawer";
  description?: string;
}

/** Accessible modal shell used by both the centred dialog and the side drawer. */
export function Modal({ open, title, onClose, children, footer, variant = "dialog", description }: ModalProps) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descId = useId();
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  }, [onClose]);

  // Depends on `open` only: an inline `onClose` must not re-run this on every parent render,
  // or focus jumps back to the first control while the user types.
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
      if (e.key !== "Tab" || !panel.current) return;
      const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
      const first = items[0];
      const last = items[items.length - 1];
      const target = e.shiftKey ? (document.activeElement === first ? last : null) : document.activeElement === last ? first : null;
      if (target) {
        e.preventDefault();
        target.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [open]);

  if (!open || typeof document === "undefined") return null;
  const drawer = variant === "drawer";
  // Portalled to <body>: a backdrop-filter ancestor (any glass panel) would otherwise become the
  // containing block for `fixed` and clip the dialog.
  return createPortal(
    <div className={cx("fixed inset-0 z-50 flex", drawer ? "justify-end" : "items-center justify-center p-4")}>
      <div className="absolute inset-0 glass-overlay" aria-hidden="true" onClick={onClose} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        className={cx(
          "glass-panel relative flex max-h-full flex-col",
          drawer ? "h-full w-full max-w-xl rounded-l-[var(--radius-glass)]" : "w-full max-w-md rounded-[var(--radius-glass)]",
        )}
      >
        <div className="flex items-start justify-between gap-4 p-5 pb-3">
          <div>
            <h2 id={titleId} className="text-lg font-semibold text-ink">
              {title}
            </h2>
            {description && (
              <p id={descId} className="mt-1 text-sm text-ink-muted">
                {description}
              </p>
            )}
          </div>
          <Button variant="ghost" aria-label="Close" onClick={onClose} className="!min-h-9 !px-2">
            <Icon name="close" className="size-5" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 pb-5">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-3 border-t border-base-dark/60 p-5">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
