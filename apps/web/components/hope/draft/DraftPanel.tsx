"use client";

import { useState } from "react";
import { Panel, btnPrimary, btnSecondary, input } from "@/components/hope/ui";
import type { HopeDraftResult } from "@/lib/hope/draft";
import { useHopeT } from "@/lib/hope/i18n";
import { SECTION_IDS, useHope } from "@/lib/hope/store";
import type { Application, Opportunity, SectionId } from "@/lib/hope/types";

export type Up = (fn: (x: Application) => Application, event: string) => void;

export function DraftPanel({ opp, app, up }: { opp: Opportunity; app: Application; up: Up }) {
  const { h, locale } = useHopeT();
  const a = h.app;
  const { state } = useHope();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const unlocked = app.stage === "drafting" || app.stage === "ready";

  async function generate(mode: "agent" | "template") {
    const edited = SECTION_IDS.some((s) => app.sections[s].origin === "human" && app.sections[s].text.trim());
    if (edited && !window.confirm(a.overwrite)) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/hope/draft", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ locale, mode, ask: opp.amountMax, profile: state.profile, opportunity: opp }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) return setError(data.error === "missing_openai_key" ? a.missingKey : a.agentFailed);
      const r = data as HopeDraftResult;
      const at = new Date().toISOString();
      up((x) => ({ ...x, sections: Object.fromEntries(SECTION_IDS.map((s) => [s, { text: r.sections[s] ?? "", origin: r.source, updatedAt: at }])) as Application["sections"] }), `draft:${r.source}`);
      setNotes(r.reviewerNotes);
    } catch {
      setError(a.network);
    } finally {
      setBusy(false);
    }
  }

  const exportText = () =>
    `# ${opp.name} — ${opp.funder}\n\n> ${a.humanSubmit}\n\n` + SECTION_IDS.map((s) => `## ${a.section[s]} (${a.origin[app.sections[s].origin]})\n\n${app.sections[s].text}`).join("\n\n");

  return (
    <Panel title={a.sectionsTitle}>
      {!unlocked ? (
        <p className="rounded-xl bg-cream px-3 py-2 text-sm">🔒 {a.locked}</p>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <button className={btnPrimary} disabled={busy} onClick={() => generate("agent")}>
              {busy ? a.drafting : a.draftAi}
            </button>
            {error && (
              <button className={btnSecondary} disabled={busy} onClick={() => generate("template")}>
                {a.useTemplate}
              </button>
            )}
          </div>
          {busy && (
            <p role="status" className="animate-pulse text-sm text-navy/70">
              {a.drafting}
            </p>
          )}
          {error && (
            <p role="alert" className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </p>
          )}
          {notes.length > 0 && (
            <ul className="list-inside list-disc rounded-xl bg-gold/15 p-3 text-sm">
              {notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
          {SECTION_IDS.map((s) => (
            <SectionEditor key={s} id={s} app={app} up={up} />
          ))}
          <div className="flex flex-wrap gap-2 border-t border-line pt-3">
            <button
              className={btnSecondary}
              onClick={async () => {
                await navigator.clipboard.writeText(exportText());
                setCopied(true);
              }}
            >
              {copied ? `✓ ${a.copied}` : a.copy}
            </button>
            <button
              className={btnSecondary}
              onClick={() => {
                const url = URL.createObjectURL(new Blob([exportText()], { type: "text/markdown" }));
                const link = Object.assign(document.createElement("a"), { href: url, download: `${opp.id}-draft.md` });
                link.click();
                URL.revokeObjectURL(url);
              }}
            >
              {a.download}
            </button>
          </div>
          <p className="text-xs text-navy/70">{a.humanSubmit}</p>
        </div>
      )}
    </Panel>
  );
}

function SectionEditor({ id, app, up }: { id: SectionId; app: Application; up: Up }) {
  const { h } = useHopeT();
  const sec = app.sections[id];
  const tone = { empty: "bg-line text-navy/70", ai: "bg-sage text-teal-ink", template: "bg-gold/25 text-navy", human: "bg-navy text-cream" }[sec.origin];
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <label htmlFor={`sec-${id}`} className="font-semibold">
          {h.app.section[id]}
        </label>
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${tone}`}>{h.app.origin[sec.origin]}</span>
      </div>
      <textarea
        id={`sec-${id}`}
        rows={id === "budget" || id === "logicModel" ? 6 : 5}
        className={input}
        value={sec.text}
        onChange={(e) => up((x) => ({ ...x, sections: { ...x.sections, [id]: { text: e.target.value, origin: "human", updatedAt: new Date().toISOString() } } }), `edit:${id}`)}
      />
    </div>
  );
}
