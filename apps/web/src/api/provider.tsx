"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { FixtureApi } from "./fixture";
import { HttpApi } from "./http";
import type { HopeApi } from "./types";

interface ApiEnv {
  apiUrl?: string;
  tenantId?: string;
  agencyId?: string;
  userId?: string;
  roles?: string;
}

/** HTTP client when the API URL, tenant and agency are configured; otherwise the offline fixtures. */
export function createApi(env: ApiEnv = {}): HopeApi {
  const apiUrl = env.apiUrl ?? process.env.NEXT_PUBLIC_HOPE_API_URL;
  const tenantId = env.tenantId ?? process.env.NEXT_PUBLIC_HOPE_TENANT_ID;
  const agencyId = env.agencyId ?? process.env.NEXT_PUBLIC_HOPE_AGENCY_ID;
  if (!apiUrl || !tenantId || !agencyId) return new FixtureApi();
  const roles = (env.roles ?? process.env.NEXT_PUBLIC_HOPE_ROLES ?? "").split(",").map((r) => r.trim()).filter(Boolean);
  return new HttpApi({
    baseUrl: apiUrl,
    tenantId,
    agencyId,
    userId: env.userId ?? process.env.NEXT_PUBLIC_HOPE_USER_ID,
    roles,
    submissionChannel: process.env.NEXT_PUBLIC_HOPE_SUBMISSION_CHANNEL,
  });
}

const ApiContext = createContext<HopeApi | null>(null);

export function ApiProvider({ api, children }: { api?: HopeApi; children: ReactNode }) {
  const value = useMemo(() => api ?? createApi(), [api]);
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

export function useApi(): HopeApi {
  const api = useContext(ApiContext);
  if (!api) throw new Error("useApi must be used inside <ApiProvider>");
  return api;
}
