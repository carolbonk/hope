import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { BidItem, BidView } from "./api";
import { BidWorkspace } from "./BidWorkspace";

const GRANT = "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10";
const ME = "11111111-2222-4333-8444-555555555555";
const ANA = "22222222-3333-4444-8555-666666666666";

const api = vi.hoisted(() => ({
  getBid: vi.fn(),
  listMembers: vi.fn(),
  updateItem: vi.fn(),
  reviewItem: vi.fn(),
  finalReview: vi.fn(),
  recordSubmission: vi.fn(),
}));
vi.mock("./api", () => api);
vi.mock("@/lib/api/session", () => ({ useSession: () => ({ status: "ready", me: { user_id: ME, display_name: "Bea" } }) }));

const item = (over: Partial<BidItem> = {}): BidItem => ({
  key: "need",
  kind: "question",
  label: "Describe the need.",
  checklist_status: "drafted",
  quote: "Describe the need.",
  url: "https://funder.example/apply",
  limit: null,
  owner: null,
  due: null,
  status: "missing",
  note: "",
  evidence_ref: "",
  review: null,
  ...over,
});

function bid(over: Partial<BidView> = {}): BidView {
  return {
    application_id: "a1",
    grant_id: GRANT,
    title: "Community Health Access Grant",
    funder: "Chelan County Community Foundation",
    url: "https://funder.example",
    deadline: "2026-12-07",
    phase: "preparing",
    ready: 0,
    total: 1,
    blockers: 2,
    updated_at: "2026-11-07T12:00:00Z",
    version: 4,
    items: [item()],
    blocker_list: [
      { code: "no_owner", key: "need" },
      { code: "not_ready", key: "need" },
    ],
    plan: [{ key: "owners", due: "2026-11-23", done: false }],
    final_review: null,
    submission: null,
    created_at: "2026-11-07T12:00:00Z",
    ...over,
  };
}

async function open(view: BidView) {
  api.getBid.mockResolvedValue(view);
  api.listMembers.mockResolvedValue([
    { user_id: ME, display_name: "Bea" },
    { user_id: ANA, display_name: "Ana" },
  ]);
  render(<BidWorkspace grantId={GRANT} />);
  await screen.findByRole("heading", { name: view.title });
}

beforeEach(() => vi.clearAllMocks());

it("assigns an owner with the bid's version and shows names, never emails", async () => {
  await open(bid());
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  const owner = screen.getByLabelText("Owner");
  expect(within(owner).getAllByRole("option").map((o) => o.textContent)).toEqual(["Unassigned", "You", "Ana"]);
  api.updateItem.mockResolvedValue(bid({ items: [item({ owner: ANA })], version: 5 }));
  fireEvent.change(owner, { target: { value: ANA } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Save" })));
  expect(api.updateItem).toHaveBeenCalledWith(GRANT, "need", { owner: ANA }, 4);
  expect(await screen.findByText(/^Ana · Internal due date/)).toBeInTheDocument();
});

it("asks for a comment before requesting changes", async () => {
  await open(bid({ items: [item({ status: "ready" })] }));
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  fireEvent.click(screen.getByRole("button", { name: "Request changes" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Write what should change.");
  expect(api.reviewItem).not.toHaveBeenCalled();
});

it("lists blockers and only offers the final review once they're clear", async () => {
  await open(bid());
  fireEvent.click(screen.getByRole("tab", { name: "Final review" }));
  expect(within(screen.getByTestId("blockers")).getAllByRole("listitem").map((l) => l.textContent)).toEqual([
    "Describe the need.: no ownerResolve",
    "Describe the need.: not readyResolve",
  ]);
  expect(screen.queryByRole("button", { name: "Complete the final review" })).toBeNull();
});

it("records the receipt after the final review and then is read-only", async () => {
  const reviewed = { by: ME, at: "2026-11-20T10:00:00Z", decision: "approved" as const, comment: "", stale: false };
  await open(bid({ phase: "final_reviewed", blocker_list: [], blockers: 0, final_review: { by: ME, at: "2026-11-20T10:00:00Z", comment: "" }, items: [item({ owner: ME, status: "ready", review: reviewed })] }));
  fireEvent.click(screen.getByRole("tab", { name: "Final review" }));
  expect(screen.getByTestId("final-done")).toHaveTextContent("Final review by You");
  api.recordSubmission.mockResolvedValue(
    bid({ phase: "submitted", blocker_list: [], blockers: 0, submission: { receipt: "CCF-42", portal: "CCF portal", submitted_at: "2026-11-21T12:00:00Z", recorded_by: ME, recorded_at: "2026-11-21T12:00:00Z", sent_by_hope: false } }),
  );
  fireEvent.change(screen.getByLabelText("Receipt or confirmation number"), { target: { value: "CCF-42" } });
  fireEvent.change(screen.getByLabelText("Portal"), { target: { value: "CCF portal" } });
  fireEvent.change(screen.getByLabelText("Submitted on"), { target: { value: "2026-11-21" } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Record the receipt" })));
  expect(api.recordSubmission).toHaveBeenCalledWith(GRANT, expect.objectContaining({ receipt: "CCF-42", portal: "CCF portal" }), 4);
  expect(await screen.findByTestId("receipt-done")).toHaveTextContent("not by Hope");
  expect(screen.getByText("This bid was submitted and is read-only.")).toBeInTheDocument();
});

it("says so when the bid doesn't exist", async () => {
  const { ProblemError } = await import("@/lib/api/http");
  api.getBid.mockRejectedValue(new ProblemError(404, "bid_not_found", "Bid not found"));
  api.listMembers.mockResolvedValue([]);
  render(<BidWorkspace grantId={GRANT} />);
  expect(await screen.findByText("This bid wasn't found.")).toBeInTheDocument();
});
