import { ProblemError } from "@/lib/api/http";
import { DEMO_FORM } from "@/lib/api/profile/fixture";
import type { ProfileApi, ProfileView } from "@/lib/api/profile";
import { HOPE_KEY } from "../store";
import type { OrgProfile } from "../types";

const h = vi.hoisted(() => ({ online: true, api: null as unknown as ProfileApi }));

vi.mock("@/lib/api/http", async (orig) => {
  const real = await orig<typeof import("@/lib/api/http")>();
  return {
    ...real,
    get online() {
      return h.online;
    },
  };
});
vi.mock("@/lib/api/profile", async (orig) => ({ ...(await orig<typeof import("@/lib/api/profile")>()), profileApi: () => h.api }));

const view = (version: number, form = DEMO_FORM, updated_at = "2026-11-07T21:40:12Z"): ProfileView => ({
  version,
  updated_at,
  updated_by: "demo@hope.org",
  onboarding_complete: true,
  form: structuredClone(form),
  ntee_labels: {},
  etag: `"${version}"`,
});

function fakeApi(get: ProfileView | null | Error = view(3)) {
  return {
    getProfile: vi.fn(async () => {
      if (get instanceof Error) throw get;
      return get;
    }),
    saveProfile: vi.fn(),
    patchProfile: vi.fn(async (sections: Partial<typeof DEMO_FORM>, etag: string) => view(Number(etag.replaceAll('"', "")) + 1, { ...DEMO_FORM, ...sections })),
  };
}

async function load() {
  vi.resetModules();
  const sync = await import("./profile");
  const { profileFromOnboarding } = await import("../fromOnboarding");
  const { emptyProfile } = await import("../store");
  return { ...sync, local: (updatedAt = "2026-11-08T00:00:00Z"): OrgProfile => ({ ...profileFromOnboarding(DEMO_FORM, emptyProfile()), updatedAt }) };
}

const storeLocal = (p: OrgProfile) => window.localStorage.setItem(HOPE_KEY, JSON.stringify({ version: 1, profile: p }));
const settle = async (status: () => { idle: Promise<void> }) => {
  for (let i = 0; i < 5; i++) await status().idle;
};

beforeEach(() => {
  window.localStorage.clear();
  h.online = true;
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

describe("sync/profile", () => {
  it("off without api url", async () => {
    h.online = false;
    const api = fakeApi();
    h.api = api;
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const sync = await load();
    await expect(sync.loadRemoteProfile()).resolves.toBeNull();
    expect(sync.saveRemoteProfile(sync.local())).toBeUndefined();
    expect(api.getProfile).not.toHaveBeenCalled();
    expect(api.patchProfile).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("load returns newer server profile only", async () => {
    const api = fakeApi(view(3, { ...DEMO_FORM, basics: { ...DEMO_FORM.basics, legal_name: "Server Name" } }));
    h.api = api;
    const sync = await load();
    const older = { ...sync.local("2026-11-01T00:00:00Z"), outcomes: undefined, publicName: "Keep me" };
    storeLocal(older);
    const got = await sync.loadRemoteProfile();
    expect(got).toMatchObject({ legalName: "Server Name", publicName: "Keep me", updatedAt: "2026-11-07T21:40:12Z" });
    expect(sync.profileSyncStatus()).toMatchObject({ etag: '"3"', pending: false });
    expect(JSON.parse(window.localStorage.getItem(sync.SYNC_KEY)!)).toMatchObject({ etag: '"3"' });

    storeLocal({ ...sync.local("2026-11-08T00:00:00Z"), completedSteps: 5 });
    await expect(sync.loadRemoteProfile()).resolves.toBeNull();
    storeLocal({ ...sync.local(), updatedAt: "" });
    await expect(sync.loadRemoteProfile()).resolves.toMatchObject({ legalName: "Server Name" });
  });

  it("server onboarding_complete marks the profile complete", async () => {
    h.api = fakeApi(view(3));
    const sync = await load();
    storeLocal(sync.local("2026-11-01T00:00:00Z"));
    await expect(sync.loadRemoteProfile()).resolves.toMatchObject({ completedSteps: 5 });

    storeLocal(sync.local("2026-11-08T00:00:00Z"));
    await expect(sync.loadRemoteProfile()).resolves.toMatchObject({ completedSteps: 5, updatedAt: "2026-11-08T00:00:00Z" });

    h.api = fakeApi({ ...view(3), onboarding_complete: false });
    const again = await load();
    storeLocal(again.local("2026-11-01T00:00:00Z"));
    await expect(again.loadRemoteProfile()).resolves.toMatchObject({ completedSteps: 3 });
  });

  it("load never rejects", async () => {
    for (const get of [null, new ProblemError(401, "not_signed_in", "x"), new ProblemError(0, "network_error", "x"), new ProblemError(503, "http_503", "x"), new TypeError("boom")]) {
      h.api = fakeApi(get);
      const sync = await load();
      await expect(sync.loadRemoteProfile()).resolves.toBeNull();
    }
  });

  it("save patches changed valid sections", async () => {
    const api = fakeApi();
    h.api = api;
    const sync = await load();
    const p = { ...sync.local(), mission: "We bring dental care and counseling to every rural school we can reach." };
    expect(sync.saveRemoteProfile(p)).toBeUndefined();
    await settle(sync.profileSyncStatus);
    expect(api.getProfile).toHaveBeenCalledOnce();
    expect(api.patchProfile).toHaveBeenCalledOnce();
    expect(api.patchProfile).toHaveBeenCalledWith({ mission: { ...DEMO_FORM.mission, mission_statement: p.mission } }, '"3"');
    expect(sync.profileSyncStatus()).toMatchObject({ etag: '"4"', pending: false, skipped: [] });

    sync.saveRemoteProfile({ ...p, legalName: "", mission: "Short" });
    await settle(sync.profileSyncStatus);
    expect(api.patchProfile).toHaveBeenCalledTimes(1);
    expect(sync.profileSyncStatus().skipped).toEqual(["basics", "mission"]);

    sync.saveRemoteProfile({ ...p, currency: "EUR", annualBudget: 5 });
    await settle(sync.profileSyncStatus);
    expect(sync.profileSyncStatus().skipped).toEqual(["non_usd_budget"]);
  });

  it("skips until onboarding", async () => {
    const api = fakeApi(null);
    h.api = api;
    const sync = await load();
    sync.saveRemoteProfile(sync.local());
    await settle(sync.profileSyncStatus);
    expect(api.patchProfile).not.toHaveBeenCalled();
    expect(sync.profileSyncStatus().skipped).toEqual(["needs_onboarding"]);
  });

  it("conflict retries once", async () => {
    const api = fakeApi();
    api.patchProfile.mockRejectedValueOnce(new ProblemError(409, "version_conflict", "x"));
    h.api = api;
    const sync = await load();
    const p = { ...sync.local(), vision: "Care within thirty minutes for every family." };
    sync.saveRemoteProfile(p);
    await settle(sync.profileSyncStatus);
    expect(api.getProfile).toHaveBeenCalledTimes(2);
    expect(api.patchProfile).toHaveBeenCalledTimes(2);
    expect(sync.profileSyncStatus().pending).toBe(false);

    api.patchProfile.mockRejectedValue(new ProblemError(428, "if_match_required", "x"));
    sync.saveRemoteProfile({ ...p, vision: "Another vision for the valley." });
    await settle(sync.profileSyncStatus);
    expect(api.patchProfile).toHaveBeenCalledTimes(4);
    expect(sync.profileSyncStatus().pending).toBe(true);
  });

  it("conflict retry keeps others' sections", async () => {
    const theirs = { ...DEMO_FORM, basics: { ...DEMO_FORM.basics, legal_name: "Their Name" } };
    const api = fakeApi();
    api.patchProfile.mockRejectedValueOnce(new ProblemError(409, "version_conflict", "x"));
    h.api = api;
    const sync = await load();
    const p = { ...sync.local(), vision: "Care within thirty minutes for every family." };
    await sync.loadRemoteProfile();
    api.getProfile.mockResolvedValue(view(5, theirs));
    sync.saveRemoteProfile(p);
    await settle(sync.profileSyncStatus);
    expect(api.patchProfile).toHaveBeenLastCalledWith({ mission: { ...DEMO_FORM.mission, vision_statement: p.vision } }, '"5"');
  });

  it("validation drops sections", async () => {
    const api = fakeApi();
    api.patchProfile.mockRejectedValueOnce(
      new ProblemError(422, "validation_error", "x", [{ field: "basics.website", code: "invalid_format", message: "Bad URL." }]),
    );
    h.api = api;
    const sync = await load();
    sync.saveRemoteProfile({ ...sync.local(), website: "https://new.example.org/" });
    await settle(sync.profileSyncStatus);
    expect(api.patchProfile).toHaveBeenCalledOnce();
    expect(sync.profileSyncStatus()).toMatchObject({ skipped: ["basics"], pending: false, etag: '"3"' });
  });

  it("network sets pending and retries", async () => {
    const api = fakeApi();
    api.patchProfile.mockRejectedValueOnce(new ProblemError(0, "network_error", "Failed to fetch"));
    h.api = api;
    const sync = await load();
    const p = { ...sync.local("2026-11-08T00:00:00Z"), completedSteps: 5, vision: "Care within thirty minutes for every family." };
    sync.saveRemoteProfile(p);
    await settle(sync.profileSyncStatus);
    expect(sync.profileSyncStatus().pending).toBe(true);
    storeLocal(p);
    await expect(sync.loadRemoteProfile()).resolves.toBeNull();
    await settle(sync.profileSyncStatus);
    expect(api.patchProfile).toHaveBeenCalledTimes(2);
    expect(sync.profileSyncStatus()).toMatchObject({ pending: false, etag: '"4"' });
  });
});
