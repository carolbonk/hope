import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { w1 } from "./testing";

const nav = vi.hoisted(() => ({ replace: vi.fn(), path: "/hope/saved" }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.path,
  useRouter: () => ({ replace: nav.replace, push: nav.replace }),
}));

async function guard(online: boolean) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_HOPE_API_URL", online ? "http://api.test" : "");
  const { RequireSession } = await import("./RequireSession");
  render(
    <RequireSession>
      <p>page content</p>
    </RequireSession>,
  );
}

const flush = () => act(async () => {});

beforeEach(() => {
  nav.replace.mockReset();
  window.history.replaceState(null, "", "/hope/saved?tab=all");
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

it("offline renders the page with no request", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  await guard(false);
  expect(screen.getByText("page content")).toBeInTheDocument();
  await flush();
  expect(fetch).not.toHaveBeenCalled();
});

it("shows the checking state without a flash of content, then the page", async () => {
  let resolve!: (r: Response) => void;
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((r) => (resolve = r))));
  await guard(true);
  expect(screen.getByRole("status")).toHaveTextContent("Loading your workspace…");
  expect(screen.queryByText("page content")).not.toBeInTheDocument();
  await act(async () => resolve(w1("me.get/onboarded")));
  expect(screen.getByText("page content")).toBeInTheDocument();
  expect(nav.replace).not.toHaveBeenCalled();
});

it("redirects a signed-out user to /login with next", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(w1("me.get/signed_out")));
  await guard(true);
  await flush();
  expect(nav.replace).toHaveBeenCalledWith(`/login?next=${encodeURIComponent("/hope/saved?tab=all")}`);
  expect(screen.queryByText("page content")).not.toBeInTheDocument();
});

it("redirects to /onboarding until onboarding is complete", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(w1("me.get/not_onboarded")));
  await guard(true);
  await flush();
  expect(nav.replace).toHaveBeenCalledWith("/onboarding");
  expect(screen.queryByText("page content")).not.toBeInTheDocument();
});

it("shows the unreachable state and retries", async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError("Failed to fetch")).mockResolvedValue(w1("me.get/onboarded"));
  vi.stubGlobal("fetch", fetch);
  await guard(true);
  await flush();
  expect(screen.getByRole("alert")).toHaveTextContent("Hope can't reach the server.");
  expect(screen.getByRole("alert")).toHaveTextContent("Check that make demo is running, then try again.");
  await userEvent.click(screen.getByRole("button", { name: /reload/i }));
  await flush();
  expect(screen.getByText("page content")).toBeInTheDocument();
});

it("treats a 5xx as unreachable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("down", { status: 503 })));
  await guard(true);
  await flush();
  expect(screen.getByRole("alert")).toBeInTheDocument();
});

it("redirects when any /v1 call returns 401 mid-use", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(w1("me.get/onboarded")));
  await guard(true);
  await flush();
  expect(screen.getByText("page content")).toBeInTheDocument();
  await act(async () => void window.dispatchEvent(new Event("hope:unauthorized")));
  expect(nav.replace).toHaveBeenCalledWith(`/login?next=${encodeURIComponent("/hope/saved?tab=all")}`);
});

it("refetches /v1/me on window focus and shares one cached request", async () => {
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(w1("me.get/onboarded")));
  vi.stubGlobal("fetch", fetch);
  await guard(true);
  await flush();
  expect(fetch).toHaveBeenCalledTimes(1);
  fetch.mockImplementation(() => Promise.resolve(w1("me.get/signed_out")));
  await act(async () => void window.dispatchEvent(new Event("focus")));
  await flush();
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(nav.replace).toHaveBeenCalledWith(expect.stringMatching(/^\/login\?next=/));
});

it("safeNext keeps only same-site paths", async () => {
  vi.resetModules();
  const { safeNext } = await import("./index");
  expect(safeNext("/hope/saved?x=1")).toBe("/hope/saved?x=1");
  for (const bad of [null, undefined, "", "https://evil.example", "//evil.example", "/\\evil.example", "hope"]) {
    expect(safeNext(bad)).toBe("/hope/discover");
  }
});
