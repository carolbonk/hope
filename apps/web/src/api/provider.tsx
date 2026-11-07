"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { FixtureApi } from "./fixture";
import { HttpApi } from "./http";
import type { HopeApi } from "./types";

export function createApi(env: { apiUrl?: string; tenantId?: string } = {}): HopeApi {
  const apiUrl = env.apiUrl ?? process.env.NEXT_PUBLIC_HOPE_API_URL;
  const tenantId = env.tenantId ?? process.env.NEXT_PUBLIC_HOPE_TENANT_ID;
  if (apiUrl && tenantId) return new HttpApi({ baseUrl: apiUrl, tenantId });
  return new FixtureApi();
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
