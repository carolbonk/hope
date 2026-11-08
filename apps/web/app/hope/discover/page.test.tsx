import { act, fireEvent, render, screen } from "@testing-library/react";
import type { Opportunity } from "@/lib/hope/types";
import DiscoverPage from "./page";

const fetchOpportunities = vi.fn<() => Promise<Opportunity[] | null>>();
vi.mock("@/lib/hope/sync/opportunities", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hope/sync/opportunities")>()),
  fetchOpportunities: () => fetchOpportunities(),
}));

const found = (id: string, name: string): Opportunity => ({
  id,
  funder: "Cascade Health Foundation",
  name,
  amountMin: 75000,
  amountMax: 75000,
  currency: "USD",
  geography: [],
  fundingType: "grant",
  focusAreas: [],
  purpose: "program",
  deadline: "2099-03-03",
  requirements: [{ id: "funder_eligibility", label: "Funder's eligibility rules (check the source page)" }],
  federal: false,
  source: { kind: "verified", url: `https://cascadehealth.example.org/${id}`, verifiedAt: "2026-11-07" },
  funderContext: null,
});

const check = (id: string, over: Partial<Opportunity> = {}): Opportunity => ({
  ...found(id, "Community Grants Supporting Charitable Causes in NCW"),
  funder: "Community Foundation of NCW",
  source: { kind: "verified", url: `https://cfncw.example.org/${id}`, verifiedAt: "2026-11-07" },
  summary: "Grants for charitable causes in north central Washington.",
  amountMin: null,
  amountMax: null,
  amountText: null,
  otherCurrency: null,
  deadline: null,
  deadlineText: "Rolling",
  ...over,
});

beforeEach(() => {
  window.localStorage.clear();
  fetchOpportunities.mockReset();
});

it("sync off renders deck and panel once without requests", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  fetchOpportunities.mockResolvedValue(null);
  render(<DiscoverPage />);
  await act(async () => {});
  expect(screen.getAllByRole("region", { name: "Find real grants" })).toHaveLength(1);
  expect(screen.getByText("Live search needs Hope's server. These are demo cards.")).toBeInTheDocument();
  expect(screen.getAllByText(/Fictional opportunity/).length).toBeGreaterThan(0);
  expect(screen.getByText("Demo data")).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
  vi.unstubAllGlobals();
});

it("verified cards show source and no demo chip; save pass undo work", async () => {
  fetchOpportunities.mockResolvedValue([found("g-1", "Rural Oral Health Access Grant 2027"), found("g-2", "CHW Training Grant")]);
  render(<DiscoverPage />);
  await act(async () => {});
  expect(screen.queryByText(/Fictional opportunity/)).not.toBeInTheDocument();
  expect(screen.queryByText("Demo data")).not.toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /cascadehealth\.example\.org\/g-/ }).length).toBeGreaterThan(0);
  const state = () => JSON.stringify(Object.fromEntries(Object.entries(window.localStorage)));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await act(async () => {});
  expect(state()).toMatch(/g-1|g-2/);
  fireEvent.click(screen.getByRole("button", { name: "Undo" }));
  fireEvent.keyDown(document.body, { key: "ArrowLeft" });
  await act(async () => {});
  expect(state()).toContain("passed");
});

it("grants missing amount or deadline join the deck as marked check cards, after complete ones", async () => {
  fetchOpportunities.mockResolvedValue([check("g-9", { amountText: "Grants are made possible through donors." }), found("g-1", "Rural Oral Health Access Grant 2027")]);
  render(<DiscoverPage />);
  await act(async () => {});
  expect(screen.queryByTestId("check-card")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Pass" }));
  await act(async () => {});
  const card = screen.getByTestId("check-card");
  expect(card).toHaveTextContent("Check amount and deadline");
  expect(card).toHaveTextContent("Amount not found");
  expect(card).toHaveTextContent('Page says: "Grants are made possible through donors."');
  expect(card).toHaveTextContent("Rolling, no fixed date");
  expect(card).not.toHaveTextContent("$");
  expect(screen.getByRole("link", { name: /Open funder page/ })).toHaveAttribute("href", "https://cfncw.example.org/g-9");
  expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  fireEvent.keyDown(document.body, { key: "ArrowLeft" });
  await act(async () => {});
  expect(screen.queryByTestId("check-card")).not.toBeInTheDocument();
});

it("a check card saves like any card: decision and application, unknowns kept null", async () => {
  fetchOpportunities.mockResolvedValue([check("g-9")]);
  render(<DiscoverPage />);
  await act(async () => {});
  expect(screen.getByTestId("check-card")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await act(async () => {});
  expect(screen.queryByTestId("check-card")).not.toBeInTheDocument();
  const stored = JSON.parse(Object.values(window.localStorage).find((v) => v.includes("g-9"))!);
  expect(stored.decisions["g-9"].decision).toBe("saved");
  expect(Object.values(stored.applications).map((a) => (a as { opportunityId: string }).opportunityId)).toContain("g-9");
  fireEvent.click(screen.getByRole("button", { name: /Undo/ }));
  await act(async () => {});
  expect(screen.getByTestId("check-card")).toBeInTheDocument();
});

it("filters hide check cards", async () => {
  fetchOpportunities.mockResolvedValue([check("g-9")]);
  render(<DiscoverPage />);
  await act(async () => {});
  expect(screen.getByTestId("check-card")).toBeInTheDocument();
  fireEvent.change(screen.getAllByLabelText("Funding type")[0]!, { target: { value: "grant" } });
  await act(async () => {});
  expect(screen.queryByTestId("check-card")).not.toBeInTheDocument();
});

it("check cards replace demo cards and show what is known", async () => {
  fetchOpportunities.mockResolvedValue([check("g-8", { amountMin: 5000, amountMax: 50000, amountText: "ranging from $5,000 to $50,000 per organization", deadlineText: "by 5 p.m. PDT on Sept. 18" })]);
  render(<DiscoverPage />);
  await act(async () => {});
  expect(screen.queryByText(/Fictional opportunity/)).not.toBeInTheDocument();
  const card = screen.getByTestId("check-card");
  expect(card).toHaveTextContent("Check deadline");
  expect(card).toHaveTextContent("$5,000–$50,000");
  expect(card).toHaveTextContent("Deadline not found");
  expect(card).toHaveTextContent('Page says: "by 5 p.m. PDT on Sept. 18"');
});
