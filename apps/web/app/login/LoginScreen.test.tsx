import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nProvider } from "@/components/I18nProvider";
import { ProblemError } from "@/api/http";
import type { Locale } from "@/lib/locale";
import { LoginScreen } from "./LoginScreen";

const nav = vi.hoisted(() => {
  let query = "";
  const subs = new Set<() => void>();
  const set = (q: string) => {
    query = q;
    subs.forEach((f) => f());
  };
  return {
    get: () => query,
    set,
    subs,
    replace: vi.fn((url: string) => {
      if (url.startsWith("/login")) set(url.split("?")[1] ?? "");
    }),
  };
});

vi.mock("next/navigation", async () => {
  const React = await import("react");
  return {
    usePathname: () => "/login",
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
    useRouter: () => ({ push: nav.replace, replace: nav.replace, refresh: vi.fn() }),
  };
});

const session = vi.hoisted(() => ({
  state: { me: "signed_out" as "signed_out" | "new" | "onboarded", network: false },
  calls: [] as unknown[],
}));

vi.mock("@/api/session", async () => {
  const real = await vi.importActual<typeof import("@/api/session")>("@/api/session");
  const { ProblemError: PE } = await vi.importActual<typeof import("@/api/http")>("@/api/http");
  const user = { user_id: "u1", email: "demo@hope.org", display_name: "Dana Okafor" };
  const net = () => {
    if (session.state.network) throw new PE(0, "network_error", "Failed to fetch");
  };
  return {
    safeNext: real.safeNext,
    invalidateSession: vi.fn(),
    me: vi.fn(async () => {
      if (session.state.me === "signed_out") throw new PE(401, "not_signed_in", "Sign in to continue.");
      return { ...user, agency_id: "a1", onboarding_complete: session.state.me === "onboarded" };
    }),
    login: vi.fn(async (body: { email: string; password: string }) => {
      net();
      session.calls.push(body);
      if (body.email !== "demo@hope.org" || body.password !== "hope-demo")
        throw new PE(401, "invalid_credentials", "Wrong email or password.");
      session.state.me = "onboarded";
      return user;
    }),
    signup: vi.fn(async (body: { email: string; password: string; display_name: string; invite_code: string }) => {
      net();
      session.calls.push(body);
      if (body.email === "taken@hope.org") throw new PE(409, "email_taken", "Taken.");
      if (body.password === "short") throw new PE(422, "weak_password", "Weak.");
      if (body.invite_code !== "Xq7m-3Kp9-Lw2v-8Tz4") throw new PE(403, "signup_closed", "Closed.");
      session.state.me = "new";
      return user;
    }),
  };
});

const { invalidateSession } = await import("@/api/session");

function renderLogin(query = "", locale: Locale = "en") {
  act(() => nav.set(query));
  return render(
    <I18nProvider locale={locale}>
      <LoginScreen />
    </I18nProvider>,
  );
}

const ready = () => screen.findByRole("tablist");

beforeEach(() => {
  session.state = { me: "signed_out", network: false };
  session.calls = [];
  nav.replace.mockClear();
  vi.mocked(invalidateSession).mockClear();
  vi.unstubAllEnvs();
});

async function signIn(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  return user;
}

describe("LoginScreen", () => {
  it("sign in redirects by onboarding state", async () => {
    renderLogin("next=%2Fhope%2Fpipeline");
    await ready();
    await signIn("Demo@Hope.org ", "hope-demo");
    await waitFor(() => expect(nav.replace).toHaveBeenLastCalledWith("/hope/pipeline"));
    expect(invalidateSession).toHaveBeenCalledOnce();
    expect(session.calls[0]).toEqual({ email: "demo@hope.org", password: "hope-demo" });
  });

  it("invalid credentials", async () => {
    renderLogin();
    await ready();
    await signIn("demo@hope.org", "wrong-password");
    expect(await screen.findByText("That email or password isn't right.")).toBeInTheDocument();
    const password = screen.getByLabelText("Password");
    expect(password).toHaveValue("");
    await waitFor(() => expect(password).toHaveFocus());
  });

  it("create account goes to onboarding", async () => {
    renderLogin("tab=signup");
    await ready();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Your name"), " Dana Okafor ");
    await user.type(screen.getByLabelText("Email"), "dana@riverbendhealth.example.org");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.type(screen.getByLabelText("Invite code"), "Xq7m-3Kp9-Lw2v-8Tz4");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(nav.replace).toHaveBeenLastCalledWith("/onboarding"));
    expect(session.calls[0]).toEqual({
      email: "dana@riverbendhealth.example.org",
      password: "correct-horse-battery",
      display_name: "Dana Okafor",
      invite_code: "Xq7m-3Kp9-Lw2v-8Tz4",
    });
    expect(invalidateSession).toHaveBeenCalledOnce();
  });

  it("email taken offers sign in", async () => {
    renderLogin("tab=signup");
    await ready();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Your name"), "Dana");
    await user.type(screen.getByLabelText("Email"), "taken@hope.org");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.type(screen.getByLabelText("Invite code"), "Xq7m-3Kp9-Lw2v-8Tz4");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("There's already an account with this email. Sign in instead?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sign in instead" }));
    expect(nav.get()).toContain("tab=signin");
    expect(screen.getByRole("tab", { name: "Sign in" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByLabelText("Email")).toHaveValue("taken@hope.org");
  });

  it("client validation copy", async () => {
    renderLogin("tab=signup");
    await ready();
    const user = userEvent.setup();
    const submit = () => user.click(screen.getByRole("button", { name: "Create account" }));
    await submit();
    expect(screen.getByText("Enter your name.")).toBeInTheDocument();
    expect(screen.getByText("Enter your email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(screen.getByText("Enter your team's invite code.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Your name")).toHaveFocus());
    await user.type(screen.getByLabelText("Email"), "nope");
    await user.type(screen.getByLabelText("Password"), "short");
    await submit();
    expect(screen.getByText("Enter an email like name@example.org.")).toBeInTheDocument();
    expect(screen.getByText("Use at least 8 characters.")).toBeInTheDocument();
    expect(session.calls).toHaveLength(0);
  });

  it("tabs sync with url", async () => {
    renderLogin("tab=signup&next=%2Fhope%2Fprofile");
    await ready();
    expect(screen.getByRole("tab", { name: "Create account" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Create your Hope account");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "dana@hope.org");
    await user.click(screen.getByRole("tab", { name: "Sign in" }));
    expect(nav.get()).toBe("tab=signin&next=%2Fhope%2Fprofile");
    expect(screen.queryByLabelText("Invite code")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveValue("dana@hope.org");
    act(() => screen.getByRole("tab", { name: "Sign in" }).focus());
    await user.keyboard("{ArrowRight}");
    expect(nav.get()).toContain("tab=signup");
  });

  it("redirects when already signed in", async () => {
    session.state.me = "onboarded";
    renderLogin("next=%2Fhope%2Fprofile");
    expect(screen.getByRole("status")).toHaveTextContent("Checking your session…");
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/hope/profile"));
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
  });

  it("unsafe next falls back to discover", async () => {
    for (const next of ["https://evil.example", "//x"]) {
      session.state.me = "onboarded";
      nav.replace.mockClear();
      const view = renderLogin(`next=${encodeURIComponent(next)}`);
      await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/hope/discover"));
      view.unmount();
    }
  });

  it("demo hint fills credentials", async () => {
    const view = renderLogin();
    await ready();
    expect(screen.queryByText("Demo: demo@hope.org / hope-demo")).not.toBeInTheDocument();
    view.unmount();
    vi.stubEnv("NEXT_PUBLIC_HOPE_DEMO", "1");
    renderLogin();
    await ready();
    expect(screen.getByText("Demo: demo@hope.org / hope-demo")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Use the demo account" }));
    expect(screen.getByLabelText("Email")).toHaveValue("demo@hope.org");
    expect(screen.getByLabelText("Password")).toHaveValue("hope-demo");
    await waitFor(() => expect(screen.getByRole("button", { name: "Sign in" })).toHaveFocus());
    expect(session.calls).toHaveLength(0);
  });

  it("signed out notice", async () => {
    renderLogin("signedOut=1");
    expect(await screen.findByText("You're signed out.")).toBeInTheDocument();
    expect(nav.replace).toHaveBeenCalledWith("/login");
  });

  it("network error copy", async () => {
    renderLogin();
    await ready();
    session.state.network = true;
    await signIn("demo@hope.org", "hope-demo");
    expect(await screen.findByText("We couldn't reach Hope. Check your connection and try again.")).toBeInTheDocument();
  });

  it("signup closed asks for invite code", async () => {
    renderLogin("tab=signup");
    await ready();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Your name"), "Dana");
    await user.type(screen.getByLabelText("Email"), "dana@hope.org");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.type(screen.getByLabelText("Invite code"), "wrong-code");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(
      await screen.findByText("That invite code isn't right. Ask your team for the current code."),
    ).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Invite code")).toHaveFocus());
  });

  it("renders spanish copy", async () => {
    renderLogin("tab=signup", "es");
    expect(screen.getByRole("status")).toHaveTextContent("Comprobando tu sesión…");
    await ready();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Crear cuenta" }));
    for (const text of [
      "Escribe tu nombre.",
      "Escribe tu correo electrónico.",
      "Escribe tu contraseña.",
      "Escribe el código de invitación de tu equipo.",
    ])
      expect(screen.getByText(text)).toBeInTheDocument();
    expect(ProblemError).toBeDefined();
  });
});
