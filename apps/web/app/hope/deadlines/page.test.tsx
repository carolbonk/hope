import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import { I18nProvider } from "@/components/I18nProvider";
import { demoOpportunities } from "@/lib/hope/demo";
import { applicationId, emptyProfile, HOPE_KEY, ORG_ID } from "@/lib/hope/store";
import type { Application, HopeState, Opportunity, Stage } from "@/lib/hope/types";
import DeadlinesPage from "./page";

const catalog = vi.hoisted(() => ({ override: null as Opportunity[] | null }));
vi.mock("@/lib/hope/opportunities", async () => {
  const { demoOpportunities } = await import("@/lib/hope/demo");
  return { useOpportunities: () => catalog.override ?? demoOpportunities(new Date()) };
});

const TODAY = new Date("2026-11-07T12:00:00");
const demo = () => demoOpportunities(TODAY);
const byId = (id: string) => demo().find((o) => o.id === id)!;
const overdue: Opportunity = { ...byId("opp-harbor-capacity"), id: "opp-verified", name: "Verified Overdue Grant", deadline: "2026-11-04", source: { kind: "verified", url: "https://funder.example.org" } };

function app(oppId: string, stage: Stage = "saved"): Application {
  return { id: applicationId(ORG_ID, oppId), orgId: ORG_ID, opportunityId: oppId, stage } as Application;
}

function seedFixture() {
  const apps = [app("opp-tidal-sponsor"), app("opp-sunrise-ops", "approval"), app("opp-bayfront-youth", "drafting"), app("opp-coral-wellness", "ready"), app("opp-lumen-arts"), app("opp-gone"), app("opp-verified")];
  const decisions = { "opp-tidal-sponsor": "saved", "opp-sunrise-ops": "saved", "opp-bayfront-youth": "saved", "opp-coral-wellness": "saved", "opp-lumen-arts": "passed", "opp-verified": "saved" } as const;
  const state: HopeState = {
    version: 1,
    profile: emptyProfile(),
    decisions: Object.fromEntries(Object.entries(decisions).map(([id, decision]) => [id, { decision, at: TODAY.toISOString() }])),
    history: Object.keys(decisions),
    applications: Object.fromEntries(apps.map((a) => [a.id, a])),
  };
  window.localStorage.setItem(HOPE_KEY, JSON.stringify(state));
}

const hrefs = () => screen.getAllByRole("link").map((l) => l.getAttribute("href"));

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(TODAY);
  catalog.override = [...demo(), overdue];
  window.localStorage.clear();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("excludes ready and passed, sorts, labels urgency", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  seedFixture();
  render(<DeadlinesPage />);
  expect(hrefs()).toEqual(["/hope/applications/opp-verified", "/hope/applications/opp-tidal-sponsor", "/hope/applications/opp-sunrise-ops", "/hope/applications/opp-bayfront-youth"]);
  expect(screen.queryByText("Family Mental Wellness")).not.toBeInTheDocument();
  expect(screen.queryByText("Public Murals Fund")).not.toBeInTheDocument();
  expect(screen.getByText("Past due")).toHaveClass("bg-red-100/70");
  expect(screen.getByText("Due soon · 9d")).toHaveClass("bg-gold/70");
  expect(screen.getByText("Due soon · 12d")).toHaveClass("bg-gold/70");
  expect(screen.getByText("21d")).toHaveClass("bg-white/45");
  expect(screen.getByRole("tab", { name: "Table" })).toHaveAttribute("aria-selected", "true");
  expect(fetch).not.toHaveBeenCalled();
  expect(readFileSync(join(__dirname, "page.tsx"), "utf8")).not.toMatch(/@\/api\/|\bfetch\(/);
});

it("empty state", () => {
  render(<DeadlinesPage />);
  expect(screen.getByText("No saved opportunities yet, so no deadlines.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Discover" })).toHaveAttribute("href", "/hope/discover");
  expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
});

it("spanish copy", () => {
  seedFixture();
  render(
    <I18nProvider locale="es">
      <DeadlinesPage />
    </I18nProvider>,
  );
  expect(screen.getByText("Vencido")).toBeInTheDocument();
  expect(screen.getByText("Vence pronto · 9d")).toBeInTheDocument();
});

it("grants with no date go in a No date yet group after the dated ones, off the calendar", () => {
  const rolling: Opportunity = { ...byId("opp-sunrise-ops"), id: "g-rolling", name: "Rolling Funder Grant", amountMax: null, amountMin: null, deadline: null, deadlineText: "Rolling", source: { kind: "verified", url: "https://funder.example.org" } };
  const unknown: Opportunity = { ...rolling, id: "g-unknown", name: "Unread Funder Grant", deadlineText: null };
  catalog.override = [rolling, unknown, ...demo()];
  const apps = [app("g-rolling"), app("g-unknown"), app("opp-tidal-sponsor")];
  const state: HopeState = {
    version: 1,
    profile: emptyProfile(),
    decisions: Object.fromEntries(["g-rolling", "g-unknown", "opp-tidal-sponsor"].map((id) => [id, { decision: "saved" as const, at: TODAY.toISOString() }])),
    history: [],
    applications: Object.fromEntries(apps.map((a) => [a.id, a])),
  };
  window.localStorage.setItem(HOPE_KEY, JSON.stringify(state));
  render(<DeadlinesPage />);
  expect(hrefs()).toEqual(["/hope/applications/opp-tidal-sponsor", "/hope/applications/g-rolling", "/hope/applications/g-unknown"]);
  const group = screen.getByTestId("no-date");
  expect(screen.getByRole("heading", { name: "No date yet" })).toBeInTheDocument();
  expect(group).toHaveTextContent("Rolling Funder Grant");
  expect(group).toHaveTextContent("Rolling, no fixed date");
  expect(group).toHaveTextContent("Deadline not found");
  expect(document.body).not.toHaveTextContent(/Invalid Date|NaN/);
  fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));
  expect(screen.getAllByText("Rolling Funder Grant")).toHaveLength(1);
});
