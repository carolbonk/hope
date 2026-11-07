import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { FixtureApi } from "@/api/fixture";
import { ApiProvider } from "@/api/provider";
import { SessionProvider } from "@/api/session";

export const FIXED_NOW = new Date("2026-11-07T15:00:00Z");

export function renderWithApi(ui: ReactElement, api = new FixtureApi({ now: () => FIXED_NOW })) {
  return {
    api,
    ...render(
      <ApiProvider api={api}>
        <SessionProvider>{ui}</SessionProvider>
      </ApiProvider>,
    ),
  };
}
