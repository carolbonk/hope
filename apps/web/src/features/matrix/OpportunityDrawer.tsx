"use client";

import type { Evidence, GrantOpportunity } from "@hope/schemas";
import Link from "next/link";
import type { MatrixRow } from "@/api/types";
import { ScoreBar } from "@/components/ScoreBar";
import { Badge, Modal, Well } from "@/components/ui";
import { formatBps, formatMoney } from "@/lib/money";
import { countdown, formatDateTime } from "@/lib/time";
import { CapacityBadge, EligibilityBadge, RecommendationBadge, UrgencyBadge } from "../status";
import { DIMENSIONS, dueDate } from "./filter";

interface Props {
  row: MatrixRow | null;
  opportunity: GrantOpportunity | undefined;
  workflowId?: string;
  /** Hide dimension scores when the backend only returns ranking. */
  summaryOnly?: boolean;
  now: Date;
  onClose: () => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-muted">{title}</h3>
      {children}
    </section>
  );
}

function evidenceOf(opp: GrantOpportunity): { label: string; evidence: Evidence; status?: string }[] {
  const items = (opp.eligibility.clauses ?? []).flatMap((c) =>
    c.evidence.map((evidence) => ({ label: c.text, evidence, status: c.rule_status })),
  );
  const due = opp.deadlines.application_due;
  if (due) items.push(...due.evidence.map((evidence) => ({ label: "Application deadline", evidence, status: undefined })));
  return items;
}

export function OpportunityDrawer({ row, opportunity, workflowId, summaryOnly, now, onClose }: Props) {
  const due = dueDate(opportunity);
  return (
    <Modal
      open={!!row}
      variant="drawer"
      onClose={onClose}
      title={opportunity?.title ?? row?.opportunity_id ?? ""}
      description={opportunity ? `${opportunity.funder.name} · ${opportunity.source.source_id}` : undefined}
    >
      {row && (
        <>
          <div className="flex flex-wrap gap-2">
            <RecommendationBadge value={row.recommendation} />
            <EligibilityBadge value={row.eligibility} />
            <CapacityBadge value={row.capacity_fit} />
            {due && <UrgencyBadge {...countdown(due, now, { urgentMs: 7 * 864e5, soonMs: 21 * 864e5 })} />}
          </div>

          <Well className="mt-5 flex items-center justify-between">
            <span className="text-sm text-ink-muted">Composite score · rank {row.rank}</span>
            <span className="text-3xl font-bold tabular-nums text-accent-strong">{row.composite_score.toFixed(1)}</span>
          </Well>

          <Section title="Why this ranking">
            <p className="text-sm leading-relaxed text-ink">{row.explanation ?? "No explanation was generated for this row."}</p>
          </Section>

          {!summaryOnly && (
            <Section title="Dimension scores">
              <div className="flex flex-col gap-2">
                {DIMENSIONS.map((d) => (
                  <ScoreBar key={d.key} label={d.label} value={row.scores[d.key] ?? 0} max={d.max} />
                ))}
              </div>
            </Section>
          )}

          {opportunity && (
            <Section title="Funding">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <dt className="text-ink-muted">Award range</dt>
                <dd className="font-medium">
                  {opportunity.funding.award_floor ? `${formatMoney(opportunity.funding.award_floor, { compact: true })} – ` : "Up to "}
                  {formatMoney(opportunity.funding.award_ceiling, { compact: true })}
                </dd>
                <dt className="text-ink-muted">Expected value</dt>
                <dd className="font-medium">{formatMoney(row.estimates?.expected_value, { compact: true })}</dd>
                <dt className="text-ink-muted">Writing effort</dt>
                <dd className="font-medium">{row.estimates?.expected_hours ?? "—"} hours</dd>
                <dt className="text-ink-muted">Indirect cap</dt>
                <dd className="font-medium">{formatBps(opportunity.funding.indirect_cost_policy?.cap_bps)}</dd>
                {due && (
                  <>
                    <dt className="text-ink-muted">Application due</dt>
                    <dd className="font-medium">{formatDateTime(due)}</dd>
                  </>
                )}
              </dl>
            </Section>
          )}

          <Section title="Matched programs">
            {row.top_matched_programs?.length ? (
              <ul className="flex flex-wrap gap-2">
                {row.top_matched_programs.map((p) => (
                  <li key={p}>
                    <Badge tone="info" icon="check">
                      {p}
                    </Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-muted">No agency programs matched.</p>
            )}
          </Section>

          <Section title="Risks">
            {row.risks?.length ? (
              <ul className="flex flex-col gap-2 text-sm">
                {row.risks.map((r) => (
                  <li key={r} className="flex gap-2">
                    <span className="mt-0.5 text-warn" aria-hidden="true">
                      ▲
                    </span>
                    {r}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-muted">No risks flagged.</p>
            )}
          </Section>

          {opportunity && (
            <Section title="Evidence from the RFP">
              <ul className="flex flex-col gap-3">
                {evidenceOf(opportunity).map(({ label, evidence, status }, i) => (
                  <li key={i}>
                    <Well className="text-sm">
                      <p className="font-medium text-ink">{label}</p>
                      {evidence.quote && <blockquote className="mt-2 border-l-2 border-accent pl-3 italic text-ink">“{evidence.quote}”</blockquote>}
                      <p className="mt-2 text-xs text-ink-muted">
                        {evidence.artifact_id} · page {evidence.page}
                        {status && status !== "approved" ? ` · rule ${status.replace("_", " ")}` : ""}
                      </p>
                    </Well>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {workflowId && (
            <p className="mt-6">
              <Link href={`/workflows/${workflowId}`} className="glass-focus font-semibold text-accent-strong underline underline-offset-4">
                View workflow timeline
              </Link>
            </p>
          )}
        </>
      )}
    </Modal>
  );
}
