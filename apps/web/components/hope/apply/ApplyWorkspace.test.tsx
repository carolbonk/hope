import { fireEvent, render, screen, within } from "@testing-library/react";
import { I18nProvider } from "@/components/I18nProvider";
import { measure, type ApplicationView } from "@/lib/hope/sync/applications";
import { ApplyWorkspace, ServerNotice } from "./ApplyWorkspace";
import { useServerApplication } from "./useServerApplication";

const GRANT = "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10";
const APP = "9a1b2c3d-4e5f-4a6b-8c7d-0e1f2a3b4c5d";
const PAGE = "https://funder.example/apply";

function view(): ApplicationView {
  const need = { key: "need", prompt: "Statement of Need (5 words): Describe the gap.", url: PAGE, source: "page" as const, required: true, limit_text: "(5 words)", limit: { unit: "words" as const, max: 5 } };
  return {
    application_id: APP,
    grant_id: GRANT,
    title: "Rural Health Access",
    funder: "Example Agency",
    url: PAGE,
    stage: "drafting",
    questions_status: "found",
    version: 3,
    updated_at: "2026-11-07T12:00:00Z",
    approvals: {},
    evidence: {},
    events: [],
    requirements: { questions: [need], attachments: [{ name: "Logic model", quote: "Attachments: Logic model", url: PAGE }], budget: {}, submission: {}, eligibility: [], pages: [{ url: PAGE, status: "read" }, { url: "https://funder.example/rfp", status: "failed", reason: "403" }] },
    requirements_job: null,
    answers_job: null,
    questions: [need],
    answers: [{ question_key: "need", text: "We serve rural families in Chelan County.", origin: "ai", citations: [{ ref: "P1", kind: "profile", text: "Service area: Chelan County" }], to_confirm: ["local data showing the need"], updated_at: "2026-11-07T12:00:00Z" }],
    terms: [
      { key: "nofo", term: "NOFO", plain: "The federal announcement for this grant.", explained_by: "official", source_url: "https://www.grants.gov/learn-grants/grant-terminology", quote: "Read the NOFO.", url: PAGE, lead_days: 0, status: "info" },
      { key: "uei", term: "UEI", plain: "A free 12-character ID from SAM.gov.", explained_by: "official", source_url: "https://sam.gov/content/entity-registration", quote: "Provide your UEI.", url: PAGE, owner: "director", todo: "Get it on SAM.gov.", lead_days: 10, status: "action_needed" },
      { key: null, term: "Community navigator", plain: "A local guide who helps patients.", explained_by: "ai", quote: "Community navigators connect patients.", url: "pasted", lead_days: 0, status: "info" },
    ],
    facts: [{ need: "project timeline", answer: "Starts in March.", shared: true, updated_at: "2026-11-07T12:00:00Z" }],
    rules: [
      { key: "rule:elig1", kind: "eligibility", label: "Location", status: "not_met", reason: "This grant is for Ohio; your profile lists Chelan County, WA.", quote: "Applicants must be located in Ohio.", url: PAGE, owner: "director", confirmed_by_staff: false },
      { key: "rule:elig2", kind: "eligibility", label: "Who can apply", status: "unknown", reason: "Hope can't check this one from your profile.", quote: "Priority goes to grassroots groups.", url: PAGE, owner: "director", todo: "Confirm you meet this.", confirmed_by_staff: false },
      { key: "rule:match", kind: "budget", label: "Match / cost share", status: "unknown", reason: "A 100% match on $75,000 is $75,000.", quote: "A 1:1 cost share is required.", url: PAGE, owner: "finance", todo: "Line up $75,000 in match (cash or in-kind) and document where it comes from.", confirmed_by_staff: false },
      { key: "rule:audit", kind: "conditional", label: "Applicants requesting more than $50,000 must submit an audit.", status: "applies", reason: "Your request is $75,000; this is for requests over $50,000.", quote: "Applicants requesting more than $50,000 must submit an audit.", url: "pasted", owner: "finance", todo: "Required for you: Applicants requesting more than $50,000 must submit an audit.", confirmed_by_staff: false },
    ],
    changes: [{ what: "deadline", change: "changed", text: "March 15, 2027", before: "March 1, 2027" }],
    requirements_revision: 2,
    ask: { amount_minor: 7_500_000, currency: "USD" },
    checklist: {
      items: [
        { kind: "question", key: "need", label: "Statement of Need", status: "over_limit" },
        { kind: "attachment", key: "upload:logic", label: "Logic model", status: "upload_needed", owner: "program" },
      ],
      inputs_needed: [
        { owner: "program", text: "local data showing the need", question_key: "need" },
        { owner: "program", text: "Upload: Logic model" },
        { owner: "program", text: "project timeline", question_key: "need", answer: "Starts in March.", fact: "project timeline" },
        { owner: "finance", text: "Required for you: Applicants requesting more than $50,000 must submit an audit.", rule: "rule:audit" },
      ],
      complete: false,
    },
  };
}

function serve(v: ApplicationView) {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
    if (url.endsWith("/v1/applications")) return json({ items: [{ application_id: APP, grant_id: GRANT }], total: 1 });
    if (url.endsWith("/ask") || url.endsWith("/evidence")) return json({ ...v, version: 4 });
    if (url.endsWith("/facts")) return init?.headers && new Headers(init.headers).get("If-Match") === '"3"' ? json({ ...v, version: 4 }) : json({ code: "version_mismatch" }, 412);
    return json(v);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => vi.unstubAllGlobals());

function Harness() {
  const server = useServerApplication(GRANT);
  if (!server.view) return null;
  return (
    <>
      <ServerNotice notice={server.notice} onDismiss={server.clearNotice} />
      <ApplyWorkspace view={server.view} run={server.run} />
    </>
  );
}

const renderIt = () =>
  render(
    <I18nProvider locale="en">
      <Harness />
    </I18nProvider>,
  );

test("counts the way the funder does", () => {
  expect(measure("one two  three", { unit: "words", max: 5 })).toBe(3);
  expect(measure("a b", { unit: "characters", max: 5, includes_spaces: false })).toBe(2);
  expect(measure("a b", { unit: "characters", max: 5 })).toBe(3);
});

test("shows the funder's own question, the translated terms with sources, and the to-do list", async () => {
  serve(view());
  renderIt();
  expect(await screen.findByText(/1\. Statement of Need \(5 words\): Describe the gap\./)).toBeInTheDocument();
  expect(screen.getByText(/7\/5 words/)).toHaveTextContent("2 over the limit");
  expect(screen.getByText("local data showing the need", { selector: "li" })).toBeInTheDocument();
  expect(screen.getByText(/1 page couldn't be read/)).toBeInTheDocument();

  const uei = document.querySelector('[data-term="uei"]') as HTMLElement;
  expect(within(uei).getByText("“Provide your UEI.”")).toBeInTheDocument();
  expect(within(uei).getByText("Action needed")).toBeInTheDocument();
  expect(within(uei).getByRole("link", { name: "Source: sam.gov (official) ↗" })).toHaveAttribute("href", "https://sam.gov/content/entity-registration");
  expect(document.querySelector('[data-term="nofo"]')).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "Show all 3" }));
  const ai = document.querySelector('[data-term="Community navigator"]') as HTMLElement;
  expect(within(ai).getByText("Hope's best reading. Check with the funder.")).toBeInTheDocument();
  expect(within(ai).getByText("From your pasted form")).toBeInTheDocument();

  const todo = document.querySelector('[data-need="local data showing the need"]') as HTMLElement;
  expect(within(todo).getByLabelText("Your answer: local data showing the need")).toBeInTheDocument();
  expect(within(document.querySelector('[data-need="Upload: Logic model"]') as HTMLElement).queryByRole("textbox")).toBeNull();
  expect(screen.getByText("Hope never submits. A person submits through the funder's portal.")).toBeInTheDocument();
});

test("answering a to-do once sends the version and offers a redraft", async () => {
  const fetch = serve(view());
  renderIt();
  const todo = (await screen.findByLabelText("Your answer: local data showing the need")) as HTMLTextAreaElement;
  fireEvent.change(todo, { target: { value: "38% of adults have no regular doctor (2024 CHNA)." } });
  fireEvent.click(within(todo.closest("li")!).getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Saved. Redraft the answer that needs it.")).toBeInTheDocument();
  const call = fetch.mock.calls.find(([url]) => String(url).endsWith("/facts"))!;
  expect(JSON.parse(String(call[1]!.body))).toEqual({ need: "local data showing the need", answer: "38% of adults have no regular doctor (2024 CHNA)." });
  expect(within(todo.closest("li")!).getByRole("button", { name: "Redraft" })).toBeInTheDocument();
});

test("checks the grant's own rules, shows what changed, and reuses answers from other grants", async () => {
  const v = { ...view(), stage: "eligibility" as const };
  const fetch = serve(v);
  renderIt();
  const fit = await screen.findByRole("region", { name: "Who can apply" });
  const ohio = fit.querySelector('[data-rule="rule:elig1"]') as HTMLElement;
  expect(within(ohio).getByText("Not met")).toBeInTheDocument();
  expect(within(ohio).getByText("“Applicants must be located in Ohio.”")).toBeInTheDocument();
  expect(within(ohio).getByText(/your profile lists Chelan County, WA/)).toBeInTheDocument();
  expect(within(ohio).queryByRole("button", { name: "We meet this" })).toBeNull();

  const audit = document.querySelector('[data-rule="rule:audit"]') as HTMLElement;
  expect(within(audit).getByText("Applies to you")).toBeInTheDocument();
  expect(within(audit).getByText(/your pasted form/i)).toBeInTheDocument();

  expect(within(screen.getByTestId("changes")).getByText(/March 15, 2027/)).toHaveTextContent("Deadline: March 15, 2027 (was March 1, 2027)");
  expect(screen.getByText("Answered on another grant. Check it still fits this one.")).toBeInTheDocument();
  const auditTodo = document.querySelector('[data-need^="Required for you"]') as HTMLElement;
  expect(within(auditTodo).queryByRole("textbox")).toBeNull();

  const ask = screen.getByLabelText("How much are you requesting?");
  expect(ask).toHaveValue("75000");
  fireEvent.change(ask, { target: { value: "$40,000" } });
  fireEvent.click(within(ask.closest("form") as HTMLElement).getByRole("button", { name: "Save" }));
  const grass = document.querySelector('[data-rule="rule:elig2"]') as HTMLElement;
  await vi.waitFor(() => expect(fetch.mock.calls.some(([u]) => String(u).endsWith("/ask"))).toBe(true));
  const [, init] = fetch.mock.calls.find(([u]) => String(u).endsWith("/ask"))!;
  expect(JSON.parse(String(init?.body))).toEqual({ amount_minor: 4_000_000 });
  expect(new Headers(init?.headers).get("If-Match")).toBe('"3"');

  fireEvent.click(within(grass).getByRole("button", { name: "We meet this" }));
  await vi.waitFor(() => expect(fetch.mock.calls.some(([u]) => String(u).endsWith("/evidence"))).toBe(true));
  const [, ev] = fetch.mock.calls.find(([u]) => String(u).endsWith("/evidence"))!;
  expect(JSON.parse(String(ev?.body))).toEqual({ requirement_id: "rule:elig2", status: "yes" });
});
