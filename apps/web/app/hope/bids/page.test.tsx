import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { BidSummary } from "@/components/hope/bids/api";

const api = vi.hoisted(() => ({ listBids: vi.fn() }));
vi.mock("@/components/hope/bids/api", () => api);

const TODAY = new Date("2026-11-07T12:00:00");
const summary = (over: Partial<BidSummary>): BidSummary => ({
  application_id: "a1",
  grant_id: "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10",
  title: "Community Health Access Grant",
  funder: "Chelan County Community Foundation",
  deadline: "2026-12-07",
  phase: "preparing",
  ready: 1,
  total: 4,
  blockers: 3,
  updated_at: "2026-11-07T12:00:00Z",
  ...over,
});

async function renderPage(online: boolean) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_HOPE_API_URL", online ? "http://api.test" : "");
  const { default: BidsPage } = await import("./page");
  await act(async () => {
    render(<BidsPage />);
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(TODAY);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
});

it("counts bids by phase and links each card to its workspace", async () => {
  api.listBids.mockResolvedValue([
    summary({}),
    summary({ application_id: "a2", grant_id: "4a7c2d3f-0e1b-4f68-9b32-7d6e5c4b3a21", title: "Rural Clinics Fund", phase: "submitted", ready: 2, total: 2, blockers: 0 }),
  ]);
  await renderPage(true);
  const cards = screen.getAllByTestId("bid-card");
  expect(cards.map((c) => c.getAttribute("href"))).toEqual(["/hope/bids/3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10", "/hope/bids/4a7c2d3f-0e1b-4f68-9b32-7d6e5c4b3a21"]);
  expect(cards[0]).toHaveTextContent("Due 2026-12-07 · 30 days");
  expect(cards[0]).toHaveTextContent("1 of 4 requirements ready");
  expect(cards[0]).toHaveTextContent("Preparing · 3 things to resolve");
  expect(cards[1]).toHaveTextContent("Submitted");
  expect(cards[1]).not.toHaveTextContent("to resolve");
  const counts = [...document.querySelectorAll(".grid-cols-3 > div")].map((d) => d.textContent);
  expect(counts).toEqual(["1Preparing", "0Final review done", "1Submitted"]);
});

it("points an empty list at the matrix", async () => {
  api.listBids.mockResolvedValue([]);
  await renderPage(true);
  expect(screen.getByRole("link", { name: "Open the matrix" })).toHaveAttribute("href", "/hope/matrix");
});

it("offers a retry when the list can't load", async () => {
  api.listBids.mockRejectedValueOnce(new Error("down")).mockResolvedValue([]);
  await renderPage(true);
  expect(screen.getByText("Couldn't load your bids.")).toBeInTheDocument();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Reload" })));
  expect(api.listBids).toHaveBeenCalledTimes(2);
  expect(screen.getByText(/No bids yet/)).toBeInTheDocument();
});

it("says the server is needed when offline", async () => {
  await renderPage(false);
  expect(within(screen.getByTestId("bids-offline")).getByText("My bids needs the Hope server. Sign in to use it.")).toBeInTheDocument();
  expect(api.listBids).not.toHaveBeenCalled();
});
