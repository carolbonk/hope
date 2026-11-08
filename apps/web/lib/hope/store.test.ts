import { act, renderHook } from "@testing-library/react";
import { demoOpportunities } from "./demo";
import { applicationId, DEMO_PROFILE, HOPE_KEY, ORG_ID, useHope } from "./store";
import { mirrorDecision } from "./sync/decisions";
import { saveRemoteProfile } from "./sync/profile";

vi.mock("./sync/decisions", async (actual) => ({ ...(await actual<typeof import("./sync/decisions")>()), mirrorDecision: vi.fn(), flushDecisions: vi.fn() }));
vi.mock("./sync/profile", () => ({
  saveRemoteProfile: vi.fn(),
  loadRemoteProfile: vi.fn(),
  profileSaveOutcome: vi.fn(async () => ({ ok: true, fields: [] })),
}));

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
  act(() => {
    void result.current.saveProfile(DEMO_PROFILE);
  });
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
  act(() => {
    void result.current.saveProfile(DEMO_PROFILE);
  });
  expect(stored().decisions[opp.id].decision).toBe("saved");
  expect(stored().profile.legalName).toBe(DEMO_PROFILE.legalName);
  warn.mockRestore();
});

describe("hydrateDecisions", () => {
  const G1 = "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10";
  const G2 = "5d1c7a90-2b3e-4f61-9c8d-0e1f2a3b4c5d";
  const G3 = "0b9f5c3e-1d2a-4c6b-9e8f-7a6b5c4d3e21";
  const G4 = "7c2a1b3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d";
  const grant = (id: string) => ({ ...opp, id });
  const remote = (decisions: Record<string, "saved" | "passed">, local: string[] = []) => ({ decisions, localIds: () => new Set(local) });

  it("loads server saved and passed grants into a clean browser, without mirroring them back", () => {
    const { result } = renderHook(() => useHope());
    act(() => result.current.hydrateDecisions(remote({ [G1]: "saved", [G2]: "passed" })));
    const s = result.current.state;
    expect(s.decisions[G1]?.decision).toBe("saved");
    expect(s.decisions[G2]?.decision).toBe("passed");
    expect(s.applications[applicationId(ORG_ID, G1)]?.stage).toBe("saved");
    expect(s.applications[applicationId(ORG_ID, G2)]).toBeUndefined();
    expect(s.history).toEqual([]);
    expect(mirrorDecision).not.toHaveBeenCalled();
  });

  it("follows the server for backend grants, keeps local ones, demo ids and worked-on applications", () => {
    const { result } = renderHook(() => useHope());
    act(() => result.current.decide(opp, "saved"));
    act(() => result.current.decide(grant(G1), "saved"));
    act(() => result.current.decide(grant(G2), "saved"));
    act(() => result.current.decide(grant(G3), "saved"));
    act(() => result.current.decide(grant(G4), "passed"));
    act(() => result.current.updateApplication(applicationId(ORG_ID, G3), (a) => ({ ...a, stage: "drafting" }), "stage"));
    // G1 saved on the server too; G2 and G3 reset elsewhere; G4 pending locally while the server still says saved.
    act(() => result.current.hydrateDecisions(remote({ [G1]: "saved", [G4]: "saved" }, [G4])));
    const s = result.current.state;
    expect(Object.keys(s.decisions).sort()).toEqual([G1, G4, opp.id].sort());
    expect(s.decisions[G4]?.decision).toBe("passed");
    expect(s.applications[applicationId(ORG_ID, G2)]).toBeUndefined();
    expect(s.applications[applicationId(ORG_ID, G3)]?.stage).toBe("drafting");
    expect(s.history).toEqual([opp.id, G1, G4]);
  });

  it("applies a server pass to a saved grant and keeps its application", () => {
    const { result } = renderHook(() => useHope());
    act(() => result.current.decide(grant(G1), "saved"));
    act(() => result.current.hydrateDecisions(remote({ [G1]: "passed" })));
    expect(result.current.state.decisions[G1]?.decision).toBe("passed");
    expect(result.current.state.applications[applicationId(ORG_ID, G1)]).toBeDefined();
  });

  it("writes onto the latest stored state, not the hook's render-time copy", () => {
    const { result } = renderHook(() => useHope());
    const hydrate = result.current.hydrateDecisions;
    act(() => result.current.hydrateProfile({ ...DEMO_PROFILE }));
    act(() => hydrate(remote({ [G1]: "saved" })));
    expect(stored().profile.legalName).toBe(DEMO_PROFILE.legalName);
    expect(stored().decisions[G1]?.decision).toBe("saved");
  });
});
