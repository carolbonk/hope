import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { w1 } from "@/api/session/testing";

const nav = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/hope/discover",
  useRouter: () => ({ replace: nav.replace, push: nav.replace }),
}));

const STATE = JSON.stringify({ version: 1, profile: {}, decisions: {}, history: [], applications: {} });

async function renderNav(online: boolean) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_HOPE_API_URL", online ? "http://api.test" : "");
  const { HopeNav } = await import("./ui");
  render(<HopeNav />);
  await act(async () => {});
}

beforeEach(() => {
  nav.replace.mockReset();
  window.localStorage.setItem("hope:state:v1", STATE);
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

it("offline shows the PR #34 nav with no Sign out and no request", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  await renderNav(false);
  expect(screen.getByRole("navigation", { name: /hope/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Discover" })).toHaveAttribute("aria-current", "page");
  expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it("online shows the signed-in name and signs out without clearing browser state", async () => {
  const fetch = vi.fn((url: string) => Promise.resolve(url.endsWith("/v1/auth/logout") ? w1("auth.logout/ok") : w1("me.get/onboarded")));
  vi.stubGlobal("fetch", fetch);
  await renderNav(true);
  expect(screen.getByText("Dana Okafor")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await act(async () => {});
  expect(fetch).toHaveBeenCalledWith("http://api.test/v1/auth/logout", expect.objectContaining({ method: "POST", credentials: "include" }));
  expect(nav.replace).toHaveBeenCalledWith("/login");
  expect(window.localStorage.getItem("hope:state:v1")).toBe(STATE);
});

it("stays and explains when sign-out fails", async () => {
  const fetch = vi.fn((url: string) =>
    url.endsWith("/v1/auth/logout") ? Promise.reject(new TypeError("Failed to fetch")) : Promise.resolve(w1("me.get/onboarded")),
  );
  vi.stubGlobal("fetch", fetch);
  await renderNav(true);
  await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await act(async () => {});
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't sign out. Try again.");
  expect(nav.replace).not.toHaveBeenCalled();
});

it("truncates long names at 24 characters", async () => {
  const long = { ...(await w1("me.get/onboarded").json()), display_name: "Alexandria Montgomery-Okafor" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(long), { status: 200 })));
  await renderNav(true);
  expect(screen.getByTitle("Alexandria Montgomery-Okafor").textContent).toHaveLength(24);
});
