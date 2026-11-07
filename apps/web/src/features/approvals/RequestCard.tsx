"use client";

import type { HitlRequest } from "@hope/schemas";
import Link from "next/link";
import { useState } from "react";
import { errorMessage, StaleArtifactError } from "@/api/errors";
import { useApi } from "@/api/provider";
import { Button, Card, ErrorNotice, TextArea } from "@/components/ui";
import { GATES, type DecisionOption } from "@/lib/gates";
import { STEP_UP_MFA_GATES } from "@/lib/lifecycle";
import { countdown, formatDateTime } from "@/lib/time";
import { GateBadge, roleLabel, UrgencyBadge } from "../status";
import { StepUpDialog } from "./StepUpDialog";

interface Props {
  request: HitlRequest;
  workflowTitle?: string;
  hasWorkflow: boolean;
  now: Date;
  onDecided: (message: string) => void;
  onStale: () => void;
}

const shortHash = (hash: string) => `${hash.slice(0, 15)}…${hash.slice(-6)}`;

export function RequestCard({ request, workflowTitle, hasWorkflow, now, onDecided, onStale }: Props) {
  const api = useApi();
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState<DecisionOption | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [commentError, setCommentError] = useState<string>();
  const needsStepUp = STEP_UP_MFA_GATES.has(request.gate);
  const sla = request.due_at ? countdown(request.due_at, now) : null;

  async function submit(option: DecisionOption, stepUpToken?: string) {
    setPending(null);
    setBusy(true);
    setError(null);
    try {
      await api.submitSignal(
        request.workflow_id,
        request.gate,
        { decision: option.decision, artifact_hash: request.artifact_hash, comment: comment.trim() || null },
        { stepUpToken },
      );
      onDecided(`${option.label} recorded for ${request.gate} · ${workflowTitle ?? request.workflow_id}.`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function choose(option: DecisionOption) {
    if (option.requiresComment && !comment.trim()) {
      setCommentError(`Add a comment to ${option.label.toLowerCase()}.`);
      return;
    }
    setCommentError(undefined);
    if (needsStepUp) setPending(option);
    else void submit(option);
  }

  const titleId = `req-${request.request_id}`;
  return (
    <Card aria-labelledby={titleId}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <GateBadge gate={request.gate} />
          {sla && <UrgencyBadge urgency={sla.urgency} label={`SLA ${sla.label}`} />}
        </div>
        {request.due_at && <span className="text-xs text-ink-muted">Due {formatDateTime(request.due_at)}</span>}
      </div>
      <h2 id={titleId} className="mt-3 text-lg font-semibold text-ink">
        {hasWorkflow ? (
          <Link href={`/workflows/${request.workflow_id}`} className="neu-focus hover:underline">
            {workflowTitle ?? request.workflow_id}
          </Link>
        ) : (
          (workflowTitle ?? "Agency profile change")
        )}
      </h2>
      <p className="mt-1 text-sm text-ink">{request.summary}</p>
      <dl className="mt-3 grid gap-x-4 gap-y-1 text-xs text-ink-muted sm:grid-cols-[auto_1fr]">
        <dt>Approver roles</dt>
        <dd className="text-ink">{request.approver_roles.map(roleLabel).join(", ")}</dd>
        <dt>Artifact hash</dt>
        <dd>
          <code className="text-ink" title={request.artifact_hash}>
            {shortHash(request.artifact_hash)}
          </code>
        </dd>
      </dl>

      {error != null && (
        <div className="mt-4">
          {error instanceof StaleArtifactError ? (
            <ErrorNotice title="Stale artifact (409): this version changed after the request was opened" onRetry={onStale}>
              Your decision was not recorded. The artifact you reviewed (<code>{shortHash(request.artifact_hash)}</code>) is no longer current
              {error.currentHash ? (
                <>
                  ; the latest is <code>{shortHash(error.currentHash)}</code>
                </>
              ) : null}
              . Reload to review the latest version before deciding.
            </ErrorNotice>
          ) : (
            <ErrorNotice title="Decision not recorded">{errorMessage(error)}</ErrorNotice>
          )}
        </div>
      )}

      <TextArea
        wrapperClassName="mt-4"
        label="Comment"
        hint="Required to reject, request changes, NO-GO or hold."
        error={commentError}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        rows={2}
      />
      <div className="mt-4 flex flex-wrap items-center gap-3">
        {GATES[request.gate].options.map((o) => (
          <Button key={o.decision} variant={o.tone} disabled={busy} onClick={() => choose(o)}>
            {o.label}
          </Button>
        ))}
        {needsStepUp && <span className="text-xs text-ink-muted">Step-up MFA required</span>}
      </div>
      <StepUpDialog
        open={!!pending}
        actionLabel={pending?.label ?? ""}
        onCancel={() => setPending(null)}
        onVerified={(token) => pending && void submit(pending, token)}
      />
    </Card>
  );
}
