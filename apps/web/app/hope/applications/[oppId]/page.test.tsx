import { Suspense } from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { applicationId, emptyProfile, HOPE_KEY, ORG_ID } from "@/lib/hope/store";
import type { ApplicationView } from "@/lib/hope/sync/applications";
import type { Application, HopeState } from "@/lib/hope/types";

const GRANT = "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10";
const APP = "9a1b2c3d-4e5f-4a6b-8c7d-0e1f2a3b4c5d";
const ME = "11111111-2222-4333-8444-555555555555";
const TODAY = new Date("2026-11-07T12:00:00");

const unknowns = vi.hoisted(() => ({ on: false }));
vi.mock("@/lib/hope/opportunities", async () => {
  const { demoOpportunities } = await import("@/lib/hope/demo");
  const opp = demoOpportunities(new Date("2026-11-07T12:00:00")).find((o) => o.id === "opp-sunrise-ops")!;
  const grant = { ...opp, id: "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10", source: { kind: "grants_gov", url: "https://funder.example" } };
  return { useOpportunities: () => [unknowns.on ? { ...grant, amountMin: null, amountMax: null, deadline: null, deadlineText: "Rolling" } : grant] };
});

function serverView(over: Partial<ApplicationView> = {}): ApplicationView {
  return {
    application_id: APP,
    grant_id: GRANT,
    title: "General Operating Support",
    funder: "Sunrise",
    url: "https://funder.example",
    stage: "eligibility",
    approvals: {},
    evidence: {},
    events: [],
    questions_status: "unread",
    version: 3,
    updated_at: "2026-11-07T12:00:00Z",
    requirements: null,
    requirements_job: null,
    answers_job: null,
    questions: [],
    answers: [],
    terms: [],
    facts: [],
    rules: [],
    changes: [],
    requirements_revision: null,
    ask: null,
    checklist: { items: [], inputs_needed: [], complete: true },
    ...over,
  };
}

type Call = { method: string; path: string; ifMatch: string | null; body: Record<string, unknown> | null };

/** A tiny stand-in for the pillar H4 routes: versions, the stage rules and the ready gate. */
function serve(start: ApplicationView) {
  let v = start;
  const calls: Call[] = [];
  const failNext: { path?: string; status: number; body: unknown }[] = [];
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  const event = (kind: string, payload: Record<string, unknown>) => ({ kind, actor: ME, payload, at: new Date(Date.now() + v.events.length * 1000).toISOString() });
  const bump = (next: Partial<ApplicationView>, kind: string, payload: Record<string, unknown>) => {
    v = { ...v, ...next, version: v.version + 1, events: [event(kind, payload), ...v.events] };
    return json(v);
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const path = url.replace("http://api.test", "");
      const method = init.method ?? "GET";
      const ifMatch = new Headers(init.headers).get("If-Match");
      const body = init.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
      calls.push({ method, path, ifMatch, body });
      if (path === "/v1/me") return json({ user_id: ME, email: "ana@example.org", display_name: "Ana", agency_id: "a", onboarding_complete: true });
      if (path === "/v1/applications") return json({ items: [{ application_id: APP, grant_id: GRANT }], total: 1 });
      if (!path.startsWith(`/v1/applications/${APP}`)) return json({}, 404);
      if (method === "GET") return json(v);
      const fail = failNext.findIndex((f) => !f.path || path.endsWith(f.path));
      if (fail >= 0) {
        const [f] = failNext.splice(fail, 1);
        return json(f!.body, f!.status);
      }
      if (path.endsWith("/comments")) {
        v = { ...v, events: [event("comment", { text: body!.text }), ...v.events] };
        return json(v);
      }
      if (ifMatch !== `"${v.version}"`) return json({ code: "version_mismatch", title: "Version mismatch" }, 412);
      if (path.endsWith("/evidence") && String(body!.requirement_id).startsWith("rule:"))
        return bump({ rules: v.rules.map((r) => (r.key === body!.requirement_id ? { ...r, status: body!.status === "yes" ? "met" : "not_met", confirmed_by_staff: true } : r)) }, "evidence", body!);
      if (path.endsWith("/evidence")) return bump({ evidence: { ...v.evidence, [String(body!.requirement_id)]: { status: body!.status as "yes", note: null, by: ME, at: "2026-11-07T12:00:00Z" } } }, "evidence", body!);
      if (path.endsWith("/stage")) {
        if (body!.to === "ready" && !v.checklist.complete && !body!.override_reason)
          return json({ code: "stage_blocked", title: "Stage blocked", errors: [{ field: "stage", code: "blocked", message: "Finish the checklist first: Statement of Need" }] }, 409);
        return bump({ stage: body!.to as ApplicationView["stage"] }, "stage", { from: v.stage, ...body });
      }
      if (path.endsWith("/approvals")) {
        const step = body!.step as "program" | "director";
        if (body!.decision === "send_back") return bump({ stage: "eligibility", approvals: {} }, "send_back", { step, comment: body!.comment });
        const approvals = { ...v.approvals, [step]: { by: ME, at: "2026-11-07T12:00:00Z" } };
        return bump({ approvals, stage: step === "director" ? "drafting" : v.stage }, "approval", { step });
      }
      return json({}, 404);
    }),
  );
  return { calls, posts: (end: string) => calls.filter((c) => c.method === "POST" && c.path.endsWith(end)), failNext, view: () => v };
}

function seed() {
  const app = { id: applicationId(ORG_ID, GRANT), orgId: ORG_ID, opportunityId: GRANT, stage: "saved", approvals: { program: "pending", director: "pending" }, evidence: {}, sections: {}, comments: [], activity: [], createdAt: TODAY.toISOString(), updatedAt: TODAY.toISOString() } as unknown as Application;
  const state: HopeState = { version: 1, profile: emptyProfile(), decisions: { [GRANT]: { decision: "saved", at: TODAY.toISOString() } }, history: [GRANT], applications: { [app.id]: app } };
  window.localStorage.setItem(HOPE_KEY, JSON.stringify(state));
  return app.id;
}
const stored = (id: string) => (JSON.parse(window.localStorage.getItem(HOPE_KEY)!) as HopeState).applications[id]!;

async function renderPage(online: boolean) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_HOPE_API_URL", online ? "http://api.test" : "");
  const { I18nProvider } = await import("@/components/I18nProvider");
  const { default: ApplicationPage } = await import("./page");
  const params = Promise.resolve({ oppId: GRANT });
  await act(async () => {
    render(
      <I18nProvider locale="en">
        <Suspense>
          <ApplicationPage params={params} />
        </Suspense>
      </I18nProvider>,
    );
  });
}

const c3 = () => screen.getByText("501(c)(3)", { selector: "legend" }).closest("fieldset") as HTMLElement;

beforeEach(() => {
  window.localStorage.clear();
  unknowns.on = false;
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

const RULE = { key: "rule:c3", kind: "eligibility" as const, label: "Registered 501(c)(3)", status: "unknown" as const, reason: "Your profile doesn't say.", quote: "Applicants must be 501(c)(3) organizations.", url: "https://funder.example", owner: "director" as const, confirmed_by_staff: false };
const REQS = { questions: [], attachments: [], budget: {}, submission: {}, eligibility: [], pages: [] };

test("the grant's rules (#63) gate approval; approvals and stage moves are recorded on the server with If-Match", async () => {
  const server = serve(serverView({ requirements: REQS, rules: [RULE] }));
  const id = seed();
  await renderPage(true);

  expect(await screen.findByRole("button", { name: "Send to internal approval" })).toBeDisabled();
  expect(screen.queryByText("501(c)(3)", { selector: "legend" })).toBeNull();
  fireEvent.click(within(document.querySelector('[data-rule="rule:c3"]') as HTMLElement).getByRole("button", { name: "We meet this" }));
  await vi.waitFor(() => expect(screen.getByRole("button", { name: "Send to internal approval" })).toBeEnabled());
  expect(server.posts("/evidence")[0]).toMatchObject({ ifMatch: '"3"', body: { requirement_id: "rule:c3", status: "yes" } });

  fireEvent.click(screen.getByRole("button", { name: "Send to internal approval" }));
  await vi.waitFor(() => expect(server.view().stage).toBe("approval"));
  expect(server.posts("/stage")[0]).toMatchObject({ ifMatch: '"4"', body: { to: "approval" } });

  const program = (await screen.findByText("Program review", { selector: "p" })).parentElement!.parentElement!;
  fireEvent.click(within(program).getByRole("button", { name: "Send back" }));
  expect(await screen.findByText("Add a comment explaining what to change.")).toBeInTheDocument();
  expect(server.posts("/approvals")).toHaveLength(0);

  fireEvent.click(within(program).getByRole("button", { name: "Approve" }));
  expect(await screen.findByText(/^Approved by Ana · /)).toBeInTheDocument();
  expect(server.posts("/approvals")[0]).toMatchObject({ ifMatch: '"5"', body: { step: "program", decision: "approve" } });
  expect(screen.getByText(/Hope records who approved and when/)).toBeInTheDocument();

  const director = screen.getByText("Director review", { selector: "p" }).parentElement!.parentElement!;
  fireEvent.click(within(director).getByRole("button", { name: "Approve" }));
  await vi.waitFor(() => expect(stored(id).stage).toBe("drafting"));
  expect(stored(id).approvals).toEqual({ program: "approved", director: "approved" });
  expect(server.view().approvals.director).toMatchObject({ by: ME });
});

test("send back needs a comment, and the comment is saved on the server", async () => {
  const server = serve(serverView({ stage: "approval", evidence: { c3: { status: "yes", by: ME, at: "2026-11-07T12:00:00Z" } } }));
  seed();
  await renderPage(true);
  const program = (await screen.findByText("Program review", { selector: "p" })).parentElement!.parentElement!;
  fireEvent.change(screen.getByLabelText("Internal review comments", { selector: "textarea" }), { target: { value: "Budget figure is out of date." } });
  fireEvent.click(within(program).getByRole("button", { name: "Send back" }));
  await vi.waitFor(() => expect(server.view().stage).toBe("eligibility"));
  expect(server.posts("/approvals")[0]!.body).toEqual({ step: "program", decision: "send_back", comment: "Budget figure is out of date." });
  expect(await screen.findByText("Budget figure is out of date.", { selector: "p" })).toBeInTheDocument();

  fireEvent.change(screen.getByPlaceholderText("Write a comment"), { target: { value: "Updated the budget." } });
  fireEvent.click(screen.getByRole("button", { name: "Add comment" }));
  expect(await screen.findByText("Updated the budget.")).toBeInTheDocument();
  expect(server.posts("/comments")[0]).toMatchObject({ ifMatch: null, body: { text: "Updated the budget." } });
});

test("Mark ready lists the checklist gaps and only moves with an override reason", async () => {
  const items = [
    { kind: "question" as const, key: "need", label: "Statement of Need", status: "over_limit" },
    { kind: "budget" as const, key: "budget", label: "Budget form", status: "missing" },
    { kind: "question" as const, key: "mission", label: "Mission", status: "drafted" },
  ];
  const server = serve(serverView({ stage: "drafting", approvals: { program: { by: ME, at: "2026-11-07T12:00:00Z" }, director: { by: ME, at: "2026-11-07T12:00:00Z" } }, checklist: { items, inputs_needed: [], complete: false } }));
  seed();
  await renderPage(true);

  fireEvent.click(await screen.findByRole("button", { name: "Mark ready for human submission" }));
  const gaps = await screen.findByTestId("ready-gaps");
  expect(gaps).toHaveTextContent("Statement of Need · Over the limit");
  expect(gaps).toHaveTextContent("Budget form · Not answered");
  expect(gaps).not.toHaveTextContent("Mission");
  expect(server.posts("/stage")).toHaveLength(0);

  fireEvent.click(screen.getByRole("button", { name: "Mark ready anyway" }));
  expect(await screen.findByText("Write at least 10 characters.")).toBeInTheDocument();
  expect(server.posts("/stage")).toHaveLength(0);

  fireEvent.change(screen.getByLabelText("Why is it ready anyway?"), { target: { value: "Funder confirmed the budget form is optional." } });
  fireEvent.click(screen.getByRole("button", { name: "Mark ready anyway" }));
  await vi.waitFor(() => expect(server.view().stage).toBe("ready"));
  expect(server.posts("/stage")[0]!.body).toEqual({ to: "ready", override_reason: "Funder confirmed the budget form is optional." });
  await vi.waitFor(() => expect(screen.queryByTestId("ready-gaps")).toBeNull());
});

test("shows the server's message on 409/422 and refetches on a version conflict", async () => {
  const server = serve(serverView({ stage: "saved" }));
  seed();
  await renderPage(true);
  server.failNext.push({ path: "/stage", status: 409, body: { code: "stage_blocked", title: "Stage blocked", errors: [{ field: "stage", code: "blocked", message: "Can't move from saved to eligibility." }] } });
  fireEvent.click(await screen.findByRole("button", { name: "Start eligibility review" }));
  expect(await screen.findByText("Can't move from saved to eligibility.")).toBeInTheDocument();

  server.failNext.push({ path: "/comments", status: 422, body: { code: "validation_failed", title: "Unprocessable", detail: "Comment is too long." } });
  fireEvent.change(screen.getByPlaceholderText("Write a comment"), { target: { value: "Hello" } });
  fireEvent.click(screen.getByRole("button", { name: "Add comment" }));
  expect(await screen.findByText("Comment is too long.")).toBeInTheDocument();

  const gets = () => server.calls.filter((c) => c.method === "GET" && c.path === `/v1/applications/${APP}`).length;
  const before = gets();
  server.failNext.push({ path: "/stage", status: 412, body: { code: "version_mismatch", title: "Version mismatch" } });
  fireEvent.click(screen.getByRole("button", { name: "Start eligibility review" }));
  expect(await screen.findByText("Someone else changed this application. We loaded the latest version.")).toBeInTheDocument();
  await vi.waitFor(() => expect(gets()).toBe(before + 1));
});

test("demo mode keeps the browser-only workspace", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const id = seed();
  await renderPage(false);
  fireEvent.click(await screen.findByRole("button", { name: "Start eligibility review" }));
  fireEvent.click(within(c3()).getByLabelText("Yes"));
  expect(stored(id).stage).toBe("eligibility");
  expect(stored(id).evidence.c3).toEqual({ status: "yes", note: "" });
  expect(screen.getByText(/Simulated roles/)).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

test("a saved check card shows its unknown amount and date honestly, never as passed", async () => {
  vi.stubGlobal("fetch", vi.fn());
  unknowns.on = true;
  seed();
  await renderPage(false);
  const header = (await screen.findByRole("heading", { level: 1 })).closest("header")!;
  expect(header).toHaveTextContent("Amount not found");
  expect(header).toHaveTextContent("Deadline: Rolling, no fixed date");
  expect(header).not.toHaveTextContent("$");
  expect(header).not.toHaveTextContent(/Invalid|NaN/);
  expect(within(header).getByText(/Rolling/)).not.toHaveClass("text-red-800");
});
