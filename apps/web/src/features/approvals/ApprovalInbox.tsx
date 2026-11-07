"use client";

import { useCallback, useState } from "react";
import { errorMessage } from "@/api/errors";
import { useApi } from "@/api/provider";
import { useSession } from "@/api/session";
import { EmptyState, ErrorNotice, Loading, PageHeader, SuccessNotice } from "@/components/ui";
import { cx } from "@/lib/cx";
import { useAsync, useNow } from "@/lib/hooks";
import { roleLabel } from "../status";
import { RequestCard } from "./RequestCard";

export function ApprovalInbox() {
  const api = useApi();
  const session = useSession();
  const now = useNow(30_000);
  const [roles, setRoles] = useState<string[]>(session.roles);
  const [notice, setNotice] = useState<string | null>(null);
  const load = useCallback(async () => {
    const [requests, workflows] = await Promise.all([api.listHitlRequests(roles), api.listWorkflows()]);
    const byDue = (d?: string | null) => (d ? new Date(d).getTime() : Number.POSITIVE_INFINITY);
    return {
      requests: requests.toSorted((a, b) => byDue(a.due_at) - byDue(b.due_at)),
      titles: new Map(workflows.map((w) => [w.workflow_id, w.title])),
    };
  }, [api, roles]);
  const { data, error, loading, reload } = useAsync(load);

  const toggle = (role: string) => setRoles((r) => (r.includes(role) ? r.filter((x) => x !== role) : [...r, role]));

  return (
    <>
      <PageHeader
        title="Approval Inbox"
        description="Human-in-the-loop gates waiting on your roles, soonest SLA first. Each decision is bound to the artifact hash you reviewed."
      />
      <fieldset className="mb-6">
        <legend className="mb-2 text-sm font-medium text-ink">Show requests for</legend>
        <div className="flex flex-wrap gap-2">
          {session.roles.map((role) => {
            const on = roles.includes(role);
            return (
              <button
                key={role}
                type="button"
                aria-pressed={on}
                onClick={() => toggle(role)}
                className={cx(
                  "neu-focus min-h-9 rounded-full border px-3 text-sm font-medium motion-safe:transition-shadow",
                  on ? "neu-pressed border-accent text-accent-strong" : "neu-raised-sm border-transparent text-ink-muted",
                )}
              >
                {on ? "✓ " : ""}
                {roleLabel(role)}
              </button>
            );
          })}
        </div>
      </fieldset>

      {notice && (
        <div className="mb-4">
          <SuccessNotice>{notice}</SuccessNotice>
        </div>
      )}
      {error ? (
        <ErrorNotice title="Could not load approvals" onRetry={reload}>
          {errorMessage(error)}
        </ErrorNotice>
      ) : loading && !data ? (
        <Loading label="Loading approvals…" />
      ) : data?.requests.length ? (
        <div className="grid gap-6 xl:grid-cols-2">
          {data.requests.map((r) => (
            <RequestCard
              key={`${r.request_id}:${r.artifact_hash}`}
              request={r}
              now={now}
              workflowTitle={data.titles.get(r.workflow_id)}
              hasWorkflow={data.titles.has(r.workflow_id)}
              onStale={() => {
                setNotice(null);
                reload();
              }}
              onDecided={(msg) => {
                setNotice(msg);
                reload();
              }}
            />
          ))}
        </div>
      ) : (
        <EmptyState>Nothing is waiting on you. New requests appear here as gates open.</EmptyState>
      )}
    </>
  );
}
