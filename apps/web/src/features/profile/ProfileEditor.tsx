"use client";

import { useCallback, useState } from "react";
import { errorMessage } from "@/api/errors";
import { useApi } from "@/api/provider";
import { useSession } from "@/api/session";
import type { ProfilePatch } from "@/api/types";
import { ErrorNotice, Loading, PageHeader } from "@/components/ui";
import { useAsync } from "@/lib/hooks";
import { formatDateTime } from "@/lib/time";
import { ApprovalHierarchySection, CapacitySection, FinancialsSection, LegalSection, MissionSection } from "./sections";

export function ProfileEditor() {
  const api = useApi();
  const { agency_id } = useSession();
  const { data, error, reload } = useAsync(useCallback(() => api.getProfile(agency_id), [api, agency_id]));
  const [etag, setEtag] = useState<string>();

  if (error)
    return (
      <ErrorNotice title="Could not load the agency profile" onRetry={reload}>
        {errorMessage(error)}
      </ErrorNotice>
    );
  if (!data) return <Loading label="Loading agency profile…" />;

  const submit = async (patch: ProfilePatch) => {
    const result = await api.patchProfile(agency_id, patch, etag ?? data.etag);
    if (result.status === "applied") setEtag(result.etag);
    return result;
  };
  const props = { profile: data.profile, submit, onConflict: reload };
  return (
    <>
      <PageHeader
        title="Agency Profile"
        description={`${data.profile.legal.legal_name} · version ${data.profile.version}${data.profile.valid_from ? ` · effective ${formatDateTime(data.profile.valid_from)}` : ""}. Legal, financial and approval sections are protected and submit as proposals.`}
      />
      <div key={data.etag} className="grid gap-6 xl:grid-cols-2">
        <MissionSection {...props} />
        <CapacitySection {...props} />
        <LegalSection {...props} />
        <FinancialsSection {...props} />
        <div className="xl:col-span-2">
          <ApprovalHierarchySection {...props} />
        </div>
      </div>
    </>
  );
}
