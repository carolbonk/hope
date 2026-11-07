"use client";

import { createContext, useCallback, useContext, type ReactNode } from "react";
import { ErrorNotice, Loading } from "@/components/ui";
import { useAsync } from "@/lib/hooks";
import { errorMessage } from "./errors";
import { useApi } from "./provider";
import type { Session } from "./types";

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const api = useApi();
  const { data, error, reload } = useAsync(useCallback(() => api.getSession(), [api]));
  if (error)
    return (
      <ErrorNotice title="Could not load your session" onRetry={reload}>
        {errorMessage(error)}
      </ErrorNotice>
    );
  if (!data) return <Loading label="Signing you in…" />;
  return <SessionContext.Provider value={data}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside <SessionProvider>");
  return session;
}

export function useOptionalSession(): Session | null {
  return useContext(SessionContext);
}
