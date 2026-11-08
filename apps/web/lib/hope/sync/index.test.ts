import { act, render } from "@testing-library/react";
import { createElement } from "react";
import { w1 } from "@/api/session/testing";

const adapters = vi.hoisted(() => ({
  loadRemoteProfile: vi.fn(),
  flushDecisions: vi.fn(),
  loadRemoteDecisions: vi.fn(),
}));
vi.mock("./profile", () => ({ loadRemoteProfile: adapters.loadRemoteProfile, saveRemoteProfile: vi.fn() }));
vi.mock("./decisions", async (actual) => ({
  ...(await actual<typeof import("./decisions")>()),
  flushDecisions: adapters.flushDecisions,
  loadRemoteDecisions: adapters.loadRemoteDecisions,
  mirrorDecision: vi.fn(),
}));

async function mount(online: boolean) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_HOPE_API_URL", online ? "http://api.test" : "");
  const sync = await import("./index");
  const view = render(createElement(sync.HopeSync));
  await act(async () => {});
  return { sync, view };
}

beforeEach(() => {
  adapters.loadRemoteProfile.mockReset().mockResolvedValue(null);
  adapters.flushDecisions.mockReset().mockResolvedValue(undefined);
  adapters.loadRemoteDecisions.mockReset().mockResolvedValue(null);
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

it("never calls the adapters with sync off", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const { sync } = await mount(false);
  expect(sync.syncEnabled).toBe(false);
  expect(adapters.loadRemoteProfile).not.toHaveBeenCalled();
  expect(adapters.flushDecisions).not.toHaveBeenCalled();
  expect(adapters.loadRemoteDecisions).not.toHaveBeenCalled();
  expect(fetch).not.toHaveBeenCalled();
});

it("loads the profile and flushes decisions once after the session is ready", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(w1("me.get/onboarded"))));
  const { sync, view } = await mount(true);
  expect(sync.syncEnabled).toBe(true);
  expect(adapters.loadRemoteProfile).toHaveBeenCalledTimes(1);
  expect(adapters.flushDecisions).toHaveBeenCalledTimes(1);
  expect(adapters.loadRemoteDecisions).toHaveBeenCalledTimes(1);
  await act(async () => void window.dispatchEvent(new Event("focus")));
  view.rerender(createElement(sync.HopeSync));
  await act(async () => {});
  expect(adapters.loadRemoteProfile).toHaveBeenCalledTimes(1);
  expect(adapters.flushDecisions).toHaveBeenCalledTimes(1);
});

it("waits while signed out", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(w1("me.get/signed_out"))));
  await mount(true);
  expect(adapters.loadRemoteProfile).not.toHaveBeenCalled();
});

it("hydrates a remote profile into browser state", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(w1("me.get/onboarded"))));
  adapters.loadRemoteProfile.mockResolvedValue({ legalName: "Riverbend Community Health Alliance" });
  await mount(true);
  const stored = JSON.parse(window.localStorage.getItem("hope:state:v1") ?? "{}");
  expect(stored.profile.legalName).toBe("Riverbend Community Health Alliance");
});

it("survives adapters that throw or reject", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(w1("me.get/onboarded"))));
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  adapters.loadRemoteProfile.mockRejectedValue(new Error("down"));
  adapters.flushDecisions.mockImplementation(() => {
    throw new Error("boom");
  });
  await mount(true);
  expect(warn).toHaveBeenCalled();
  expect(window.localStorage.getItem("hope:state:v1")).toBeNull();
  warn.mockRestore();
});

it("hydrates server decisions after the profile, keeping both", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(w1("me.get/onboarded"))));
  const G1 = "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10";
  let profileDone: (p: unknown) => void = () => {};
  adapters.loadRemoteProfile.mockReturnValue(new Promise((resolve) => (profileDone = resolve)));
  adapters.loadRemoteDecisions.mockResolvedValue({ decisions: { [G1]: "saved" }, localIds: () => new Set() });
  await mount(true);
  expect(window.localStorage.getItem("hope:state:v1")).toBeNull();
  await act(async () => profileDone({ legalName: "Riverbend Community Health Alliance" }));
  const stored = JSON.parse(window.localStorage.getItem("hope:state:v1") ?? "{}");
  expect(stored.profile.legalName).toBe("Riverbend Community Health Alliance");
  expect(stored.decisions[G1].decision).toBe("saved");
});
