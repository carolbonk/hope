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
