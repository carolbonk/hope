import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FixtureOnboardingApi } from "@/api/onboarding/fixture";
import { DEMO_FORM, FixtureProfileApi } from "@/api/profile/fixture";
import { ProblemError } from "@/api/http";
import { invalidateSession } from "@/api/session";
import { AFTER_ONBOARDING, LOGIN_AGAIN, OnboardingWizard } from "./OnboardingWizard";
import { DRAFT_KEY } from "./useOnboardingDraft";

const nav = vi.hoisted(() => {
  let query = "";
  const subs = new Set<() => void>();
  return {
    get: () => query,
    set: (q: string) => {
      query = q;
      subs.forEach((f) => f());
    },
    subs,
    replace: vi.fn(),
  };
});

vi.mock("next/navigation", async () => {
  const React = await import("react");
  return {
    usePathname: () => "/onboarding",
    useSearchParams: () => {
      const q = React.useSyncExternalStore(
        (cb) => {
          nav.subs.add(cb);
          return () => nav.subs.delete(cb);
        },
        nav.get,
        nav.get,
      );
      return new URLSearchParams(q);
    },
    useRouter: () => ({ push: (url: string) => nav.set(url.split("?")[1] ?? ""), replace: nav.replace }),
  };
});

vi.mock("@/api/session", async (orig) => ({ ...(await orig<typeof import("@/api/session")>()), invalidateSession: vi.fn() }));

const renderWizard = (profile = new FixtureProfileApi("empty"), onboarding = new FixtureOnboardingApi()) => {
  render(<OnboardingWizard profile={profile} onboarding={onboarding} />);
  return { profile };
};

const title = () => screen.getByRole("heading", { level: 1 });

beforeEach(() => {
  act(() => nav.set(""));
  nav.replace.mockReset();
  vi.mocked(invalidateSession).mockReset();
  window.localStorage.clear();
});

describe("OnboardingWizard", () => {
  it("blocks continue until valid", async () => {
    const user = userEvent.setup();
    renderWizard();
    expect(await screen.findByRole("heading", { level: 1, name: "Basics" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue →" }));
    expect(screen.getByText("Legal name is required.")).toBeInTheDocument();
    expect(screen.getByText("EIN is required.")).toBeInTheDocument();
    expect(screen.getByText("Service area is required.")).toBeInTheDocument();
    expect(title()).toHaveTextContent("Basics");

    await user.type(screen.getByLabelText("Legal name *"), "Riverbend Community Health Alliance");
    await user.type(screen.getByLabelText("EIN *"), "843917265");
    expect(screen.getByLabelText("EIN *")).toHaveValue("84-3917265");
    await user.type(screen.getByLabelText("City *"), "Wenatchee");
    await user.selectOptions(screen.getByLabelText("State *"), "WA");
    await user.click(screen.getByRole("button", { name: "+ Washington" }));
    await user.click(screen.getByRole("button", { name: "Continue →" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Mission and values" })).toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem(DRAFT_KEY)!).basics.ein).toBe("84-3917265");
  });

  it("restores draft from local storage and keeps future steps disabled", async () => {
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...DEMO_FORM, ntee_codes: [] }));
    act(() => nav.set("step=programs"));
    renderWizard();
    expect(await screen.findByRole("heading", { level: 1, name: "Cause" })).toBeInTheDocument();
    expect(screen.getByText("We restored your progress.")).toBeInTheDocument();
    const rail = screen.getByRole("complementary", { name: "Setup progress" });
    expect(within(rail).getByRole("button", { name: /6 Review/ })).toBeDisabled();
  });

  it("suggests NTEE codes with citations and limits to 3", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...DEMO_FORM, ntee_codes: [] }));
    renderWizard();
    await screen.findByRole("heading", { level: 1, name: "Cause" });
    await user.click(screen.getByRole("button", { name: "Suggest codes" }));
    const list = await screen.findByRole("list", { name: "Suggested NTEE codes" });
    expect(within(list).getByText(/“dental” \[c1\]/)).toBeInTheDocument();
    await user.click(within(list).getByRole("button", { name: "Add E32 Community Clinics" }));
    expect(within(list).getByRole("button", { name: "E32 added" })).toBeDisabled();
    expect(within(screen.getByRole("list", { name: "Selected NTEE codes" })).getByText("Primary")).toBeInTheDocument();
  });

  it("finish saves and redirects", async () => {
    const user = userEvent.setup();
    const profile = new FixtureProfileApi("existing");
    renderWizard(profile);
    expect(await screen.findByRole("heading", { level: 1, name: "Review" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Finish and find grants" }));
    expect(nav.replace).toHaveBeenCalledWith(AFTER_ONBOARDING);
    expect((await profile.getProfile())!.version).toBe(4);
  });

  it("redirects to sign in on 401 at mount", async () => {
    const profile = new FixtureProfileApi("empty");
    profile.getProfile = () => Promise.reject(new ProblemError(401, "not_signed_in", "Sign in to continue."));
    renderWizard(profile);
    await vi.waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/login?next=%2Fonboarding"));
    expect(LOGIN_AGAIN).toBe("/login?next=%2Fonboarding");
  });

  it("redirects to sign in on 401 at save", async () => {
    const user = userEvent.setup();
    const profile = new FixtureProfileApi("existing");
    profile.saveProfile = () => Promise.reject(new ProblemError(401, "not_signed_in", "Sign in to continue."));
    renderWizard(profile);
    await user.click(await screen.findByRole("button", { name: "Finish and find grants" }));
    expect(nav.replace).toHaveBeenCalledWith("/login?next=%2Fonboarding");
    expect(invalidateSession).not.toHaveBeenCalled();
  });

  it("invalidates the session after finish, before redirecting", async () => {
    const user = userEvent.setup();
    let invalidatedFirst = false;
    vi.mocked(invalidateSession).mockImplementation(() => {
      invalidatedFirst = !nav.replace.mock.calls.length;
    });
    renderWizard(new FixtureProfileApi("existing"));
    await user.click(await screen.findByRole("button", { name: "Finish and find grants" }));
    expect(invalidateSession).toHaveBeenCalledOnce();
    expect(invalidatedFirst).toBe(true);
    expect(nav.replace).toHaveBeenCalledWith(AFTER_ONBOARDING);
  });

  it("server errors map to steps", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify(DEMO_FORM));
    renderWizard(new FixtureProfileApi("invalid"));
    await screen.findByRole("heading", { level: 1, name: "Review" });
    await user.click(screen.getByRole("button", { name: "Finish and find grants" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Basics" })).toBeInTheDocument();
    expect(screen.getByText("This EIN prefix isn't assigned by the IRS. Check the number.")).toBeInTheDocument();
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("shows the conflict copy on 409", async () => {
    const user = userEvent.setup();
    renderWizard(new FixtureProfileApi("conflict"));
    await screen.findByRole("heading", { level: 1, name: "Review" });
    await user.click(screen.getByRole("button", { name: "Finish and find grants" }));
    expect(await screen.findByText("Someone else saved the profile while you were editing.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load their version" })).toBeInTheDocument();
  });

  it("exact amount switches band", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...DEMO_FORM, budget: { budget_band: "<250k", annual_operating_budget_usd: null, fiscal_year_end: "12-31" } }));
    act(() => nav.set("step=budget"));
    renderWizard();
    await screen.findByRole("heading", { level: 1, name: "Budget" });
    await user.type(screen.getByLabelText("Exact budget (optional)"), "3120000");
    await user.tab();
    expect(screen.getByText("This amount is in the $1M–$5M band.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "$1M–$5M" })).toHaveAttribute("aria-checked", "true");
  });

  it("adds and removes programs", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify(DEMO_FORM));
    act(() => nav.set("step=programs"));
    renderWizard();
    await screen.findByRole("heading", { level: 1, name: "Programs" });
    expect(screen.queryByRole("button", { name: /Remove Mobile Dental Clinic/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "+ Add another program" }));
    expect(screen.getAllByLabelText("Program name *")).toHaveLength(2);
    expect(screen.getAllByLabelText("Program name *")[1]).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Remove program 2" }));
    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(screen.getAllByLabelText("Program name *")).toHaveLength(1);
  });
});
