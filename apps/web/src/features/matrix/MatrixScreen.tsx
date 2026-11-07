"use client";

import type { GrantOpportunity } from "@hope/schemas";
import { useCallback, useMemo, useState } from "react";
import { errorMessage } from "@/api/errors";
import { useApi } from "@/api/provider";
import { useSession } from "@/api/session";
import type { MatrixRow } from "@/api/types";
import { ScoreBar } from "@/components/ScoreBar";
import { Button, Card, EmptyState, ErrorNotice, Loading, PageHeader, Segmented, SelectField, Table, Td, Th, Tr } from "@/components/ui";
import { useAsync, useNow } from "@/lib/hooks";
import { countdown, formatDate, formatDateTime } from "@/lib/time";
import { CapacityBadge, ELIGIBILITY, EligibilityBadge, RECOMMENDATION, RecommendationBadge, UrgencyBadge } from "../status";
import { DEFAULT_FILTERS, DIMENSIONS, dueDate, filterRows, type DeadlineWindow, type MatrixFilters } from "./filter";
import { OpportunityDrawer } from "./OpportunityDrawer";

const DEADLINE_DAYS = { urgentMs: 7 * 864e5, soonMs: 21 * 864e5 };

const all = <T extends string>(labels: Record<T, { label: string }>) => [
  { value: "all" as const, label: "All" },
  ...(Object.entries(labels) as [T, { label: string }][]).map(([value, { label }]) => ({ value, label })),
];

export function MatrixScreen() {
  const api = useApi();
  const { agency_id } = useSession();
  const now = useNow();
  const load = useCallback(async () => {
    const [matrix, workflows] = await Promise.all([api.getMatrix(agency_id, { limit: 100 }), api.listWorkflows()]);
    const opps = await Promise.all(matrix.rows.map((r) => api.getOpportunity(r.opportunity_id)));
    return {
      matrix,
      opportunities: new Map<string, GrantOpportunity>(opps.map((o) => [o.opportunity_id, o])),
      workflowByOpp: new Map(workflows.map((w) => [w.opportunity_id, w.workflow_id])),
    };
  }, [api, agency_id]);
  const { data, error, loading, reload } = useAsync(load);
  const [filters, setFilters] = useState<MatrixFilters>(DEFAULT_FILTERS);
  const [selected, setSelected] = useState<MatrixRow | null>(null);

  const rows = useMemo(
    () => (data ? filterRows(data.matrix.rows, data.opportunities, filters, now) : []),
    [data, filters, now],
  );
  const set = <K extends keyof MatrixFilters>(key: K) => (value: MatrixFilters[K]) => setFilters((f) => ({ ...f, [key]: value }));

  return (
    <>
      <PageHeader
        title="Opportunity Matrix"
        description={
          data
            ? `Ranked by composite score · ${data.matrix.weights_profile ?? "default weights"} · generated ${formatDateTime(data.matrix.generated_at)}`
            : "Ranked grant opportunities for your agency."
        }
      />
      <Card className="mb-6">
        <div className="grid gap-5 lg:grid-cols-[auto_auto_14rem] lg:items-end">
          <Segmented label="Recommendation" value={filters.recommendation} options={all(RECOMMENDATION)} onChange={set("recommendation")} />
          <Segmented label="Eligibility" value={filters.eligibility} options={all(ELIGIBILITY)} onChange={set("eligibility")} />
          <SelectField
            label="Deadline window"
            value={filters.deadline}
            onChange={(e) => set("deadline")(e.target.value as DeadlineWindow)}
            options={[
              { value: "any", label: "Any deadline" },
              { value: "14", label: "Due within 14 days" },
              { value: "30", label: "Due within 30 days" },
              { value: "60", label: "Due within 60 days" },
            ]}
          />
        </div>
      </Card>

      {error ? (
        <ErrorNotice title="Could not load the matrix" onRetry={reload}>
          {errorMessage(error)}
        </ErrorNotice>
      ) : loading && !data ? (
        <Loading label="Loading opportunities…" />
      ) : (
        <>
          {data?.matrix.detail === "summary" && (
            <p className="mb-3 rounded-xl border border-warn bg-base px-4 py-3 text-sm text-ink" role="note">
              This backend returns ranking only. Dimension scores, eligibility and capacity fit appear once the matrix detail is available.
            </p>
          )}
          <p className="mb-3 text-sm text-ink-muted" aria-live="polite">
            Showing {rows.length} of {data?.matrix.rows.length ?? 0} opportunities
          </p>
          {rows.length === 0 ? (
            <EmptyState>No opportunities match these filters.</EmptyState>
          ) : (
            <Table caption="Ranked grant opportunities">
              <thead>
                <tr>
                  <Th className="w-12">Rank</Th>
                  <Th>Opportunity</Th>
                  <Th className="w-24 text-right">Score</Th>
                  <Th className="w-56">Dimensions</Th>
                  <Th>Eligibility</Th>
                  <Th>Deadline</Th>
                  <Th>Capacity</Th>
                  <Th>Recommendation</Th>
                  <Th className="sr-only">Details</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const opp = data?.opportunities.get(row.opportunity_id);
                  const due = dueDate(opp);
                  return (
                    <Tr key={row.opportunity_id}>
                      <Td className="text-center text-lg font-bold tabular-nums text-ink-muted">{row.rank}</Td>
                      <Td>
                        <p className="font-semibold text-ink">{opp?.title ?? row.opportunity_id}</p>
                        <p className="text-xs text-ink-muted">{opp?.funder.name}</p>
                      </Td>
                      <Td className="text-right text-xl font-bold tabular-nums text-accent-strong">{row.composite_score.toFixed(1)}</Td>
                      <Td>
                        <div className="flex flex-col gap-1">
                          {data?.matrix.detail === "summary" ? (
                            <span className="text-xs text-ink-muted">Not scored yet</span>
                          ) : (
                            DIMENSIONS.slice(0, 5).map((d) => (
                              <ScoreBar key={d.key} compact label={d.short} value={row.scores[d.key] ?? 0} max={d.max} />
                            ))
                          )}
                        </div>
                      </Td>
                      <Td>
                        <EligibilityBadge value={row.eligibility} />
                      </Td>
                      <Td>
                        {due ? (
                          <div className="flex flex-col items-start gap-1">
                            <UrgencyBadge {...countdown(due, now, DEADLINE_DAYS)} />
                            <span className="text-xs text-ink-muted">{formatDate(due)}</span>
                          </div>
                        ) : (
                          <span className="text-ink-muted">Rolling</span>
                        )}
                      </Td>
                      <Td>
                        <CapacityBadge value={row.capacity_fit} />
                      </Td>
                      <Td>
                        <RecommendationBadge value={row.recommendation} />
                      </Td>
                      <Td>
                        <Button onClick={() => setSelected(row)} aria-label={`Details for ${opp?.title ?? row.opportunity_id}`}>
                          Details
                        </Button>
                      </Td>
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </>
      )}

      <OpportunityDrawer
        row={selected}
        opportunity={selected ? data?.opportunities.get(selected.opportunity_id) : undefined}
        workflowId={selected ? data?.workflowByOpp.get(selected.opportunity_id) : undefined}
        summaryOnly={data?.matrix.detail === "summary"}
        now={now}
        onClose={() => setSelected(null)}
      />
    </>
  );
}
