import { fireEvent, render, screen, within } from "@testing-library/react";
import { I18nProvider } from "@/components/I18nProvider";
import { measure, type ApplicationView } from "@/lib/hope/sync/applications";
import { ApplyWorkspace } from "./ApplyWorkspace";

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
    checklist: {
      items: [
        { kind: "question", key: "need", label: "Statement of Need", status: "over_limit" },
        { kind: "attachment", key: "upload:logic", label: "Logic model", status: "upload_needed", owner: "program" },
      ],
      inputs_needed: [
        { owner: "program", text: "local data showing the need", question_key: "need" },
        { owner: "program", text: "Upload: Logic model" },
      ],
      complete: false,
    },
  };
}

function serve(v: ApplicationView) {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
    if (url.endsWith("/v1/applications")) return json({ items: [{ application_id: APP, grant_id: GRANT }], total: 1 });
    if (url.endsWith("/facts")) return init?.headers && new Headers(init.headers).get("If-Match") === '"3"' ? json({ ...v, version: 4 }) : json({ code: "version_mismatch" }, 412);
    return json(v);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => vi.unstubAllGlobals());

const renderIt = () =>
  render(
    <I18nProvider locale="en">
      <ApplyWorkspace grantId={GRANT} />
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
