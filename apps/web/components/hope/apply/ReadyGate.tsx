"use client";

import { useState } from "react";
import { btnPrimary, btnSecondary, input } from "@/components/hope/ui";
import { AutoDismiss } from "@/components/ui/AutoDismiss";
import { Modal } from "@/components/ui/Modal";
import { readyGaps, type ApplicationView } from "@/lib/hope/sync/applications";
import { useServerCopy } from "./copy";

export const MIN_REASON = 10;

/** The server refused `ready`: list the checklist gaps and ask for a written override reason. */
export function ReadyGate({ view, reason, onCancel, onConfirm }: { view: ApplicationView; reason: string; onCancel: () => void; onConfirm: (why: string) => void }) {
  const c = useServerCopy();
  const [why, setWhy] = useState("");
  const [error, setError] = useState(false);
  const gaps = readyGaps(view);
  return (
    <Modal
      open
      title={c.gateTitle}
      description={c.gateIntro}
      onClose={onCancel}
      footer={
        <div className="flex justify-end gap-2">
          <button className={btnSecondary} onClick={onCancel}>
            {c.cancel}
          </button>
          <button className={btnPrimary} onClick={() => (why.trim().length < MIN_REASON ? setError(true) : onConfirm(why.trim()))}>
            {c.gateConfirm}
          </button>
        </div>
      }
    >
      {gaps.length > 0 ? (
        <ul className="mb-3 list-inside list-disc text-sm" data-testid="ready-gaps">
          {gaps.map((g) => (
            <li key={`${g.kind}:${g.key}`}>
              {g.label} · <span className="font-semibold">{c.gap[g.status] ?? g.status}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mb-3 text-sm" data-testid="ready-gaps">
          {reason}
        </p>
      )}
      <label htmlFor="override-reason" className="block text-sm font-semibold">
        {c.gateReason}
      </label>
      <textarea id="override-reason" rows={3} maxLength={500} className={input} value={why} onChange={(e) => setWhy(e.target.value)} aria-invalid={error} />
      {error && (
        <AutoDismiss key={why} onDismiss={() => setError(false)}>
          <p role="alert" className="mt-1 text-sm text-red-800">
            {c.gateShort}
          </p>
        </AutoDismiss>
      )}
    </Modal>
  );
}
