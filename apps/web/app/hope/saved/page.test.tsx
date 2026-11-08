import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { I18nProvider } from "@/components/I18nProvider";
import { demoOpportunities } from "@/lib/hope/demo";
import { applicationId, emptyProfile, HOPE_KEY, ORG_ID } from "@/lib/hope/store";
import type { Application, HopeState, Opportunity, Stage } from "@/lib/hope/types";
import SavedPage from "./page";

const catalog = vi.hoisted(() => ({ override: null as Opportunity[] | null }));
vi.mock("@/lib/hope/opportunities", async () => {
  const { demoOpportunities } = await import("@/lib/hope/demo");
  return { useOpportunities: () => catalog.override ?? demoOpportunities(new Date()) };
});

const bids = vi.hoisted(() => ({ ids: new Set<string>() }));
vi.mock("@/components/hope/bids/useBidIds", () => ({ useBidIds: () => bids.ids }));

const TODAY = new Date("2026-11-07T12:00:00");
const demo = () => demoOpportunities(TODAY);
const byId = (id: string) => demo().find((o) => o.id === id)!;

function app(oppId: string, stage: Stage = "saved"): Application {
  return { id: applicationId(ORG_ID, oppId), orgId: ORG_ID, opportunityId: oppId, stage } as Application;
}

function seed(apps: Application[], decisions: Record<string, "saved" | "passed">) {
  const state: HopeState = {
    version: 1,
    profile: emptyProfile(),
    decisions: Object.fromEntries(Object.entries(decisions).map(([id, decision]) => [id, { decision, at: TODAY.toISOString() }])),
    history: Object.keys(decisions),
    applications: Object.fromEntries(apps.map((a) => [a.id, a])),
  };
  window.localStorage.setItem(HOPE_KEY, JSON.stringify(state));
}

function seedFixture() {
  seed(
    [app("opp-tidal-sponsor"), app("opp-sunrise-ops", "approval"), app("opp-bayfront-youth", "drafting"), app("opp-coral-wellness", "ready"), app("opp-lumen-arts"), app("opp-gone")],
    { "opp-tidal-sponsor": "saved", "opp-sunrise-ops": "saved", "opp-bayfront-youth": "saved", "opp-coral-wellness": "saved", "opp-lumen-arts": "passed" },
  );
}

const hrefs = () => screen.getAllByRole("link").map((l) => l.getAttribute("href"));

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(TODAY);
  catalog.override = null;
  bids.ids = new Set();
  window.localStorage.clear();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("lists applications by deadline with stage and link", () => {
  seedFixture();
  render(<SavedPage />);
  expect(hrefs()).toEqual(["/hope/applications/opp-tidal-sponsor", "/hope/applications/opp-sunrise-ops", "/hope/applications/opp-bayfront-youth", "/hope/applications/opp-coral-wellness"]);
  const tidal = screen.getByRole("link", { name: /Back-to-School Event Sponsorship/ });
  expect(tidal).toHaveTextContent("Tidal Bank Giving (demo)");
  expect(tidal).toHaveTextContent(`$10,000 · Due ${byId("opp-tidal-sponsor").deadline} · 9 days`);
  expect(tidal).toHaveTextContent("Open workspace");
  expect(screen.getByRole("list", { name: "Internal approval" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 2, name: "Saved opportunities" })).toHaveClass("sr-only");
});

it("hides passed and missing opportunities", () => {
  seedFixture();
  render(<SavedPage />);
  expect(screen.queryByText("Public Murals Fund")).not.toBeInTheDocument();
  expect(hrefs()).not.toContain("/hope/applications/opp-gone");
  expect(screen.getAllByRole("link")).toHaveLength(4);
});

it("keeps a worked-on application whose decision was undone", () => {
  seed([app("opp-lumen-arts", "drafting")], {});
  render(<SavedPage />);
  expect(hrefs()).toEqual(["/hope/applications/opp-lumen-arts"]);
});

it("demo badge only for demo data", () => {
  const verified: Opportunity = { ...byId("opp-harbor-capacity"), id: "opp-verified", name: "Verified Overdue Grant", deadline: "2026-11-04", source: { kind: "verified", url: "https://funder.example.org" } };
  catalog.override = [verified, byId("opp-tidal-sponsor")];
  seed([app("opp-verified"), app("opp-tidal-sponsor")], { "opp-verified": "saved", "opp-tidal-sponsor": "saved" });
  render(<SavedPage />);
  expect(screen.getByRole("link", { name: /Verified Overdue Grant/ })).not.toHaveTextContent("Demo data");
  expect(screen.getByRole("link", { name: /Back-to-School/ })).toHaveTextContent("Demo data");
  expect(screen.getAllByText("Demo data")).toHaveLength(1);
});

it("links a card to its bid when it has one", () => {
  seedFixture();
  bids.ids = new Set(["opp-sunrise-ops"]);
  render(<SavedPage />);
  expect(screen.getByRole("link", { name: /Open bid/ })).toHaveAttribute("href", "/hope/bids/opp-sunrise-ops");
  expect(screen.getAllByRole("link", { name: /Open bid/ })).toHaveLength(1);
});

it("empty state", () => {
  render(<SavedPage />);
  expect(screen.getByText("Nothing saved yet. Save cards in Discover to start an application.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Discover" })).toHaveAttribute("href", "/hope/discover");
});

it("spanish copy", () => {
  render(
    <I18nProvider locale="es">
      <SavedPage />
    </I18nProvider>,
  );
  expect(screen.getByText(/^Aún no has guardado nada/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Descubrir" })).toHaveAttribute("href", "/hope/discover");
});

it("makes no network calls", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  seedFixture();
  render(<SavedPage />);
  expect(fetch).not.toHaveBeenCalled();
  const source = readFileSync(join(__dirname, "page.tsx"), "utf8");
  expect(source).not.toMatch(/@\/api\/|\bfetch\(/);
});

it("a saved grant with no amount or date shows both as not found and sorts last", () => {
  const unknown: Opportunity = { ...byId("opp-sunrise-ops"), id: "g-check", name: "Unread Funder Grant", amountMin: null, amountMax: null, deadline: null, source: { kind: "verified", url: "https://funder.example.org" } };
  catalog.override = [unknown, ...demo()];
  seed([app("g-check"), app("opp-tidal-sponsor")], { "g-check": "saved", "opp-tidal-sponsor": "saved" });
  render(<SavedPage />);
  expect(hrefs()).toEqual(["/hope/applications/opp-tidal-sponsor", "/hope/applications/g-check"]);
  const card = screen.getByRole("link", { name: /Unread Funder Grant/ });
  expect(card).toHaveTextContent("Amount not found · Deadline not found");
  expect(card).not.toHaveTextContent(/\$|Invalid|NaN/);
});
