import type { WorkflowView } from "@/api/types";
import { Icon } from "@/components/ui";
import { cx } from "@/lib/cx";
import { GATE_FOR_STATE, HAPPY_PATH, humanizeState, TERMINAL_STATES, type OpportunityState } from "@/lib/lifecycle";
import { formatDateTime } from "@/lib/time";

type StepStatus = "done" | "current" | "upcoming";

/** Visited states in order, then the remaining main-path states the workflow can still reach. */
export function timelineSteps(wf: WorkflowView): { state: OpportunityState; status: StepStatus; at?: string }[] {
  const visited = wf.history.map((t) => t.to);
  const seen = new Set<OpportunityState>();
  const steps: { state: OpportunityState; status: StepStatus; at?: string }[] = [];
  wf.history.forEach((t, i) => {
    if (i < wf.history.length - 1 && t.to === wf.state) return;
    seen.add(t.to);
    steps.push({ state: t.to, status: t.to === wf.state && i === visited.length - 1 ? "current" : "done", at: t.at });
  });
  if (!TERMINAL_STATES.has(wf.state)) {
    const from = HAPPY_PATH.indexOf(wf.state);
    for (const state of HAPPY_PATH.slice(from + 1)) if (!seen.has(state)) steps.push({ state, status: "upcoming" });
  }
  return steps;
}

export function Timeline({ workflow }: { workflow: WorkflowView }) {
  const steps = timelineSteps(workflow);
  return (
    <ol className="relative ml-3 border-l-2 border-base-dark" aria-label="Lifecycle timeline">
      {steps.map(({ state, status, at }, i) => {
        const gate = GATE_FOR_STATE[state];
        return (
          <li key={`${state}-${i}`} className="mb-5 ml-6 last:mb-0" aria-current={status === "current" ? "step" : undefined}>
            <span
              className={cx(
                "absolute -left-[0.95rem] flex size-7 items-center justify-center rounded-full border-2",
                status === "done" && "neu-raised-sm border-good text-good",
                status === "current" && "neu-pressed border-accent text-accent-strong",
                status === "upcoming" && "neu-inset border-base-dark text-ink-muted",
              )}
            >
              <Icon name={status === "done" ? "check" : status === "current" ? "dot" : "chevron"} className="size-3.5" />
            </span>
            <div
              className={cx(
                "rounded-xl px-4 py-2",
                status === "current" ? "neu-raised-sm" : "",
                status === "upcoming" ? "text-ink-muted" : "text-ink",
              )}
            >
              <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                {humanizeState(state)}
                {gate && <span className="text-xs font-medium text-ink-muted">({gate})</span>}
                <span className="sr-only">: {status}</span>
                {status === "current" && <span className="text-xs font-semibold uppercase tracking-wide text-accent-strong">Current</span>}
              </p>
              {at && <p className="text-xs text-ink-muted">{formatDateTime(at)}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
