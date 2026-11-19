import { act, renderHook } from "@testing-library/react";
import { demoOpportunities } from "./demo";
import {
  applicationId,
  DEMO_PROFILE,
  eligibility,
  emptyProfile,
  geographyFits,
  HOPE_KEY,
  ORG_ID,
  requirementStatus,
  STAGES,
  useHope,
} from "./store";
import type { Application, Opportunity } from "./types";

type Req = Opportunity["requirements"][number];
import { mirrorDecision } from "./sync/decisions";
import { saveRemoteProfile } from "./sync/profile";

vi.mock("./sync/decisions", async (actual) => ({
  ...(await actual<typeof import("./sync/decisions")>()),
  mirrorDecision: vi.fn(),
  flushDecisions: vi.fn(),
}));
vi.mock("./sync/profile", () => ({
  saveRemoteProfile: vi.fn(),
  loadRemoteProfile: vi.fn(),
}));

const opp = demoOpportunities(new Date("2026-11-07"))[0]!;
const stored = () =>
  JSON.parse(window.localStorage.getItem(HOPE_KEY) ?? "null");

beforeEach(() => {
  vi.mocked(mirrorDecision).mockReset();
  vi.mocked(saveRemoteProfile).mockReset();
  window.localStorage.clear();
});

it("geographyFits matches each area of a ';'-separated service area", () => {
  const opp = (geography: string[]) => ({
    ...demoOpportunities(new Date())[0]!,
    geography,
  });
  const profile = {
    ...DEMO_PROFILE,
    serviceArea: "Little Haiti; Miami-Dade ;",
  };
  expect(geographyFits(opp(["Little Haiti"]), profile)).toBe("yes");
  expect(geographyFits(opp(["South Florida"]), profile)).toBe("yes");
  expect(geographyFits(opp(["Orlando"]), profile)).toBe("no");
  expect(
    geographyFits(opp(["Orlando"]), { ...DEMO_PROFILE, serviceArea: " ; " }),
  ).toBe("unknown");
});

it("submitted is the last stage", () => {
  expect(STAGES.at(-1)).toBe("submitted");
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
  expect(vi.mocked(saveRemoteProfile).mock.calls[0]![0].legalName).toBe(
    DEMO_PROFILE.legalName,
  );
  act(() =>
    result.current.hydrateProfile({
      ...DEMO_PROFILE,
      legalName: "From server",
    }),
  );
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

describe("hydrateDecisions", () => {
  const G1 = "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10";
  const G2 = "5d1c7a90-2b3e-4f61-9c8d-0e1f2a3b4c5d";
  const G3 = "0b9f5c3e-1d2a-4c6b-9e8f-7a6b5c4d3e21";
  const G4 = "7c2a1b3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d";
  const grant = (id: string) => ({ ...opp, id });
  const remote = (
    decisions: Record<string, "saved" | "passed">,
    local: string[] = [],
  ) => ({ decisions, localIds: () => new Set(local) });

  it("loads server saved and passed grants into a clean browser, without mirroring them back", () => {
    const { result } = renderHook(() => useHope());
    act(() =>
      result.current.hydrateDecisions(
        remote({ [G1]: "saved", [G2]: "passed" }),
      ),
    );
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
    act(() =>
      result.current.updateApplication(
        applicationId(ORG_ID, G3),
        (a) => ({ ...a, stage: "drafting" }),
        "stage",
      ),
    );
    // G1 saved on the server too; G2 and G3 reset elsewhere; G4 pending locally while the server still says saved.
    act(() =>
      result.current.hydrateDecisions(
        remote({ [G1]: "saved", [G4]: "saved" }, [G4]),
      ),
    );
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
    expect(
      result.current.state.applications[applicationId(ORG_ID, G1)],
    ).toBeDefined();
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

describe("requirementStatus and eligibility", () => {
  const coral = demoOpportunities(new Date("2026-11-07")).find(
    (o) => o.id === "opp-coral-wellness",
  )!;
  const [c3, budget] = coral.requirements as [Req, Req];
  const withEvidence = (evidence: Application["evidence"]) =>
    ({ evidence }) as Application;
  const p = (
    has501c3: "yes" | "no" | "unknown",
    annualBudget: number | null,
  ) => ({ ...emptyProfile(), has501c3, annualBudget });

  it("recorded evidence beats the profile, and the profile beats unknown", () => {
    expect(requirementStatus(c3, p("unknown", null))).toBe("unknown");
    expect(requirementStatus(c3, p("yes", null))).toBe("yes");
    expect(
      requirementStatus(
        c3,
        p("yes", null),
        withEvidence({ c3: { status: "no", note: "lapsed" } }),
      ),
    ).toBe("no");
    expect(requirementStatus(budget, p("yes", 300_000))).toBe("yes");
    expect(requirementStatus(budget, p("yes", 100_000))).toBe("no");
    expect(requirementStatus(budget, p("yes", null))).toBe("unknown");
  });

  it.each([
    ["yes", 300_000, "meets"],
    ["yes", 100_000, "not_qualified"],
    ["no", null, "not_qualified"],
    ["yes", null, "needs_review"],
    ["unknown", 300_000, "needs_review"],
  ] as const)("501(c)(3) %s, budget %s -> %s", (c, b, want) => {
    expect(eligibility(coral, p(c, b))).toBe(want);
  });

  it("an opportunity with no requirements meets", () => {
    const open = demoOpportunities(new Date("2026-11-07")).find(
      (o) => o.id === "opp-lumen-arts",
    )!;
    expect(eligibility(open, emptyProfile())).toBe("meets");
  });
});
