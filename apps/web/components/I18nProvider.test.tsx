import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { I18nProvider, useI18n } from "./I18nProvider";
import { LanguageToggle } from "./LanguageToggle";

function Show() {
  const { locale } = useI18n();
  return <p data-testid="locale">{locale}</p>;
}

afterEach(() => {
  document.cookie = "lang=; path=/; max-age=0";
  vi.restoreAllMocks();
});

it("uses the saved choice, then the browser language", () => {
  vi.spyOn(navigator, "language", "get").mockReturnValue("es-MX");
  const { unmount } = render(<I18nProvider><Show /></I18nProvider>);
  expect(screen.getByTestId("locale")).toHaveTextContent("es");
  expect(document.documentElement.lang).toBe("es");
  unmount();
  document.cookie = "lang=en; path=/";
  render(<I18nProvider><Show /></I18nProvider>);
  expect(screen.getByTestId("locale")).toHaveTextContent("en");
});

it("the toggle switches language in place and remembers it", () => {
  render(<I18nProvider><Show /><LanguageToggle /></I18nProvider>);
  expect(screen.getByTestId("locale")).toHaveTextContent("en");
  act(() => screen.getByRole("button", { name: "es" }).click());
  expect(screen.getByTestId("locale")).toHaveTextContent("es");
  expect(document.cookie).toContain("lang=es");
});
