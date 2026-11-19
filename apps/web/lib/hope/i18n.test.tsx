import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { I18nProvider } from "@/components/I18nProvider";
import { useHopeT } from "./i18n";

const health = (locale: "en" | "es") => {
  function Wrapper({ children }: { children: ReactNode }) {
    return <I18nProvider locale={locale}>{children}</I18nProvider>;
  }
  return renderHook(useHopeT, { wrapper: Wrapper }).result.current.h.focus.health;
};

it("labels the health focus in both languages", () => {
  expect(health("en")).toBe("Health");
  expect(health("es")).toBe("Salud");
});
