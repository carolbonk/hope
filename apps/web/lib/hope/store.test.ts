import { act, renderHook } from "@testing-library/react";
import { demoOpportunities } from "./demo";
import { DEMO_PROFILE, HOPE_KEY, useHope } from "./store";
import { mirrorDecision } from "./sync/decisions";
import { saveRemoteProfile } from "./sync/profile";

vi.mock("./sync/decisions", () => ({ mirrorDecision: vi.fn(), flushDecisions: vi.fn() }));
vi.mock("./sync/profile", () => ({ saveRemoteProfile: vi.fn(), loadRemoteProfile: vi.fn() }));

const opp = demoOpportunities(new Date("2026-11-07"))[0]!;
const stored = () => JSON.parse(window.localStorage.getItem(HOPE_KEY) ?? "null");

beforeEach(() => {
  vi.mocked(mirrorDecision).mockReset();
  vi.mocked(saveRemoteProfile).mockReset();
  window.localStorage.clear();
});

it("decide writes locally, then mirrors once", () => {
  const { result } = renderHook(() => useHope());
  act(() => result.current.decide(opp, "saved"));
  expect(result.current.state.decisions[opp.id]?.decision).toBe("saved");
  expect(mirrorDecision).toHaveBeenCalledTimes(1);
  expect(mirrorDecision).toHaveBeenCalledWith(opp.id, "saved");
});

it("undo mirrors the last decision as new, and nothing with an empty history", () => {
  const { result } = renderHook(() => useHope());
  act(() => result.current.undo());
  expect(mirrorDecision).not.toHaveBeenCalled();
  act(() => result.current.decide(opp, "passed"));
  vi.mocked(mirrorDecision).mockReset();
  act(() => result.current.undo());
  expect(mirrorDecision).toHaveBeenCalledTimes(1);
  expect(mirrorDecision).toHaveBeenCalledWith(opp.id, "new");
  expect(result.current.state.history).toEqual([]);
});

it("saveProfile saves remotely; hydrateProfile does not echo", () => {
  const { result } = renderHook(() => useHope());
  act(() => result.current.saveProfile(DEMO_PROFILE));
  expect(saveRemoteProfile).toHaveBeenCalledTimes(1);
  expect(vi.mocked(saveRemoteProfile).mock.calls[0]![0].legalName).toBe(DEMO_PROFILE.legalName);
  act(() => result.current.hydrateProfile({ ...DEMO_PROFILE, legalName: "From server" }));
  expect(saveRemoteProfile).toHaveBeenCalledTimes(1);
  expect(stored().profile.legalName).toBe("From server");
});

it("a throwing adapter never breaks the page or the browser state", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.mocked(mirrorDecision).mockImplementation(() => {
    throw new Error("boom");
  });
  vi.mocked(saveRemoteProfile).mockImplementation(() => {
    throw new Error("boom");
  });
  const { result } = renderHook(() => useHope());
  act(() => result.current.decide(opp, "saved"));
  act(() => result.current.saveProfile(DEMO_PROFILE));
  expect(stored().decisions[opp.id].decision).toBe("saved");
  expect(stored().profile.legalName).toBe(DEMO_PROFILE.legalName);
  warn.mockRestore();
});
