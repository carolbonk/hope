"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { errorMessage, PreconditionFailedError } from "@/api/errors";
import { sectionLabel } from "@/api/fixture";
import type { ProfilePatch, ProfilePatchResult } from "@/api/types";
import { Badge, Button, Card, ErrorNotice, SuccessNotice } from "@/components/ui";
import { isProtectedSection, type ProfileSection } from "@/lib/lifecycle";

interface Props {
  section: ProfileSection;
  title: string;
  description: string;
  dirty: boolean;
  /** Returns the patch for this section, or a validation message. */
  buildPatch: () => ProfilePatch | string;
  submit: (patch: ProfilePatch) => Promise<ProfilePatchResult>;
  onReset: () => void;
  onConflict: () => void;
  children: ReactNode;
}

export function SectionShell({ section, title, description, dirty, buildPatch, submit, onReset, onConflict, children }: Props) {
  const isProtected = isProtectedSection(section);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ProfilePatchResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const headingId = `section-${section}`;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setResult(null);
    setError(null);
    const patch = buildPatch();
    if (typeof patch === "string") return setError(new Error(patch));
    setBusy(true);
    try {
      setResult(await submit(patch));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card aria-labelledby={headingId}>
      <form onSubmit={onSubmit} noValidate>
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id={headingId} className="text-lg font-semibold text-ink">
              {title}
            </h2>
            <p className="mt-1 text-sm text-ink-muted">{description}</p>
          </div>
          {isProtected ? (
            <Badge tone="warn" icon="lock">
              Requires approval (HITL-0)
            </Badge>
          ) : (
            <Badge tone="neutral" icon="check">
              Saves immediately
            </Badge>
          )}
        </div>
        {children}
        {error != null && (
          <div className="mt-4">
            <ErrorNotice title={isProtected ? "Proposal not submitted" : "Changes not saved"} onRetry={error instanceof PreconditionFailedError ? onConflict : undefined}>
              {errorMessage(error)}
            </ErrorNotice>
          </div>
        )}
        {result && (
          <div className="mt-4">
            <SuccessNotice>
              {result.status === "pending_approval" ? (
                <>
                  Proposal <code>{result.proposal_id}</code> for {result.sections.map(sectionLabel).join(", ")} is waiting for HITL-0 approval. The
                  current profile stays in effect until it is approved.{" "}
                  <Link href="/approvals" className="neu-focus font-semibold text-accent-strong underline underline-offset-4">
                    View in Approval Inbox
                  </Link>
                </>
              ) : result.status === "accepted" ? (
                <>
                  Change <code>{result.proposal_id}</code> accepted. The profile steward applies it shortly; reload to see the new version.
                </>
              ) : (
                <>Saved. Profile is now version {result.profile.version}.</>
              )}
            </SuccessNotice>
          </div>
        )}
        <div className="mt-5 flex flex-wrap justify-end gap-3">
          <Button onClick={onReset} disabled={!dirty || busy}>
            Discard
          </Button>
          <Button type="submit" variant="primary" disabled={!dirty || busy}>
            {isProtected ? "Submit for approval" : "Save changes"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
