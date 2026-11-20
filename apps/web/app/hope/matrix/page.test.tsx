import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { Opportunity } from "@/lib/hope/types";

const GRANT = "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10";
const OTHER = "4a7c2d3f-0e1b-4f68-9b32-7d6e5c4b3a21";

const api = vi.hoisted(() => ({ listBids: vi.fn(), startBid: vi.fn() }));
const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("@/components/hope/bids/api", () => api);
vi.mock("next/navigation", () => ({ useRouter: () => nav }));
vi.mock("@/lib/hope/opportunities", async () => {
  const { demoOpportunities } = await import("@/lib/hope/demo");
  // The page scores deadlines against the real today, so the demo deadlines must count from it too.
  const all = demoOpportunities(new Date());
  const ids: Record<string, string> = { "opp-sunrise-ops": GRANT, "opp-bayfront-youth": OTHER };
  return { useOpportunities: (): Opportunity[] => all.map((o) => (ids[o.id] ? { ...o, id: ids[o.id]! } : o)) };
});

async function renderPage(online: boolean) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_HOPE_API_URL", online ? "http://api.test" : "");
  const { default: MatrixPage } = await import("./page");
  await act(async () => {
    render(<MatrixPage />);
  });
}

const table = () => screen.getByTestId("matrix-table");
const row = (name: string) => within(table()).getByText(name).closest("tr") as HTMLElement;

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  api.listBids.mockResolvedValue([{ grant_id: OTHER }]);
});
afterEach(() => vi.unstubAllEnvs());

it("ranks every opportunity by the sample score and filters by recommendation", async () => {
  await renderPage(true);
  const rows = within(table()).getAllByTestId("matrix-row");
  const scores = rows.map((r) => Number(r.querySelectorAll("td")[2]!.textContent));
  expect(scores).toEqual([...scores].sort((a, b) => b - a));
  expect(screen.getByRole("status")).toHaveTextContent(`Showing ${rows.length} of ${rows.length} · Sample score`);
  const rec = rows[0]!.querySelectorAll("td")[6]!.textContent!;
  fireEvent.click(screen.getByRole("button", { name: rec }));
  const filtered = within(table()).getAllByTestId("matrix-row");
  for (const r of filtered) expect(r.querySelectorAll("td")[6]).toHaveTextContent(rec);
});

it("opens an existing bid and starts a new one for a server grant", async () => {
  await renderPage(true);
  expect(within(row("Youth Mentoring Grants")).getByRole("link", { name: "Open bid" })).toHaveAttribute("href", `/hope/bids/${OTHER}`);
  expect(within(row("Family Mental Wellness")).getByRole("button", { name: "Prepare bid" })).toBeDisabled();
  api.startBid.mockResolvedValue({ grant_id: GRANT });
  await act(async () => fireEvent.click(within(row("General Operating Support")).getByRole("button", { name: "Prepare bid" })));
  expect(api.startBid).toHaveBeenCalledWith(GRANT);
  expect(nav.push).toHaveBeenCalledWith(`/hope/bids/${GRANT}`);
});

it("stays usable offline but can't prepare bids", async () => {
  await renderPage(false);
  expect(screen.getByText("Sign in to prepare bids. They're kept on the Hope server.")).toBeInTheDocument();
  expect(api.listBids).not.toHaveBeenCalled();
  expect(within(table()).getAllByTestId("matrix-row").length).toBeGreaterThan(0);
  for (const b of within(table()).getAllByRole("button", { name: "Prepare bid" })) expect(b).toBeDisabled();
});
