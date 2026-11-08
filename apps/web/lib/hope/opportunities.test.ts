import { renderHook, waitFor } from "@testing-library/react";
import { demoOpportunities } from "./demo";
import { useOpportunities } from "./opportunities";
import { fetchOpportunities } from "./sync/opportunities";
import type { Opportunity } from "./types";

vi.mock("./sync/opportunities", () => ({ fetchOpportunities: vi.fn() }));

const today = new Date().toDateString();

beforeEach(() => {
  vi.mocked(fetchOpportunities).mockReset();
});

it("returns the demo catalog when the adapter has nothing", async () => {
  vi.mocked(fetchOpportunities).mockResolvedValue(null);
  const { result } = renderHook(() => useOpportunities());
  await waitFor(() => expect(fetchOpportunities).toHaveBeenCalledTimes(1));
  expect(result.current).toEqual(demoOpportunities(new Date(today)));
});

it("returns the remote catalog when there is one", async () => {
  const remote = [{ ...demoOpportunities(new Date(today))[0]!, id: "remote-1" }] as Opportunity[];
  vi.mocked(fetchOpportunities).mockResolvedValue(remote);
  const { result } = renderHook(() => useOpportunities());
  await waitFor(() => expect(result.current).toEqual(remote));
});

it("falls back to the demo catalog when the adapter rejects", async () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.mocked(fetchOpportunities).mockRejectedValue(new Error("down"));
  const { result } = renderHook(() => useOpportunities());
  await waitFor(() => expect(warn).toHaveBeenCalled());
  expect(result.current).toEqual(demoOpportunities(new Date(today)));
  warn.mockRestore();
});

it("falls back to the demo catalog when the adapter throws", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.mocked(fetchOpportunities).mockImplementation(() => {
    throw new Error("boom");
  });
  const { result } = renderHook(() => useOpportunities());
  expect(warn).toHaveBeenCalled();
  expect(result.current).toEqual(demoOpportunities(new Date(today)));
  warn.mockRestore();
});
