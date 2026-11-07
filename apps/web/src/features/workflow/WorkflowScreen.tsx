"use client";

import Link from "next/link";
import { useCallback } from "react";
import { errorMessage } from "@/api/errors";
import { useApi } from "@/api/provider";
import { Badge, Card, ErrorNotice, Loading, PageHeader, Table, Td, Th, Tr, Well } from "@/components/ui";
import { useAsync, useNow } from "@/lib/hooks";
import { humanizeState, nextStates, TERMINAL_STATES } from "@/lib/lifecycle";
import { countdown, formatDateTime } from "@/lib/time";
import { GateBadge, UrgencyBadge } from "../status";
import { Timeline } from "./Timeline";

export function WorkflowList() {
  const api = useApi();
  const now = useNow();
  const { data, error, reload } = useAsync(useCallback(() => api.listWorkflows(), [api]));
  return (
    <>
      <PageHeader title="Workflows" description="Every opportunity in flight and where it sits in the lifecycle." />
      {error ? (
        <ErrorNotice title="Could not load workflows" onRetry={reload}>
          {errorMessage(error)}
        </ErrorNotice>
      ) : !data ? (
        <Loading label="Loading workflows…" />
      ) : (
        <Table caption="Workflows" className="min-w-[40rem]">
          <thead>
            <tr>
              <Th>Opportunity</Th>
              <Th>State</Th>
              <Th>Internal deadline</Th>
            </tr>
          </thead>
          <tbody>
            {data.map((w) => (
              <Tr key={w.workflow_id}>
                <Td>
                  <Link href={`/workflows/${w.workflow_id}`} className="neu-focus font-semibold text-ink hover:underline">
                    {w.title}
                  </Link>
                </Td>
                <Td>{humanizeState(w.state)}</Td>
                <Td>
                  {w.internal_deadline && !TERMINAL_STATES.has(w.state) ? (
                    <UrgencyBadge {...countdown(w.internal_deadline, now, { urgentMs: 3 * 864e5, soonMs: 10 * 864e5 })} />
                  ) : (
                    <span className="text-ink-muted">—</span>
                  )}
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}

export function WorkflowDetail({ workflowId }: { workflowId: string }) {
  const api = useApi();
  const { data, error, reload } = useAsync(useCallback(() => api.getWorkflow(workflowId), [api, workflowId]));
  if (error)
    return (
      <ErrorNotice title="Could not load this workflow" onRetry={reload}>
        {errorMessage(error)}
      </ErrorNotice>
    );
  if (!data) return <Loading label="Loading workflow…" />;
  const next = nextStates(data.state);
  return (
    <>
      <PageHeader
        title={data.title}
        description={`Workflow ${data.workflow_id} · currently ${humanizeState(data.state)}`}
        actions={
          <Link href="/workflows" className="neu-focus neu-raised-sm rounded-xl px-4 py-2 text-sm font-semibold text-ink">
            All workflows
          </Link>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <h2 className="mb-4 text-lg font-semibold">Lifecycle</h2>
          <Timeline workflow={data} />
        </Card>
        <div className="flex flex-col gap-6">
          <Card>
            <h2 className="mb-3 text-lg font-semibold">Open gates</h2>
            {data.open_gates.length ? (
              <ul className="flex flex-col gap-3">
                {data.open_gates.map((g) => (
                  <li key={g.request_id}>
                    <Well>
                      <GateBadge gate={g.gate} />
                      <p className="mt-2 text-sm">{g.summary}</p>
                      <Link href="/approvals" className="neu-focus mt-2 inline-block text-sm font-semibold text-accent-strong underline underline-offset-4">
                        Open in Approval Inbox
                      </Link>
                    </Well>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-muted">No gates are open.</p>
            )}
          </Card>
          <Card>
            <h2 className="mb-3 text-lg font-semibold">Possible next states</h2>
            {next.length ? (
              <ul className="flex flex-wrap gap-2">
                {next.map((s) => (
                  <li key={s}>
                    <Badge tone={s === "Expired" ? "warn" : "neutral"} icon={s === "Expired" ? "clock" : "chevron"}>
                      {humanizeState(s)}
                    </Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-muted">This workflow has finished.</p>
            )}
          </Card>
          <Card>
            <h2 className="mb-3 text-lg font-semibold">History</h2>
            <ul className="flex flex-col gap-2 text-sm">
              {data.events?.toReversed().map((e, i) => (
                <li key={`e-${i}`} className="flex flex-col">
                  <span className="font-medium">{e.label}</span>
                  <span className="text-xs text-ink-muted">
                    {formatDateTime(e.at)}
                    {e.actor ? ` · ${e.actor}` : ""}
                  </span>
                </li>
              ))}
              {!data.events && data.history.toReversed().map((t, i) => (
                <li key={i} className="flex flex-col">
                  <span className="font-medium">
                    {t.from ? `${humanizeState(t.from)} → ` : ""}
                    {humanizeState(t.to)}
                  </span>
                  <span className="text-xs text-ink-muted">
                    {formatDateTime(t.at)} · {t.actor}
                    {t.note ? ` · ${t.note}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
