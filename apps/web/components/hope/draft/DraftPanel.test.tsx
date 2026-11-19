import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { I18nProvider } from "@/components/I18nProvider";
import { demoOpportunities } from "@/lib/hope/demo";
import { hopeTemplate } from "@/lib/hope/draft";
import { DEMO_PROFILE, SECTION_IDS } from "@/lib/hope/store";
import type { Application, Stage } from "@/lib/hope/types";
import { DraftPanel } from "./DraftPanel";

const opp = demoOpportunities(new Date("2026-11-07T12:00:00")).find(
  (o) => o.id === "opp-bayfront-youth",
)!;
const app = (stage: Stage, edited = false): Application =>
  ({
    id: `app:org-local-1:${opp.id}`,
    orgId: "org-local-1",
    opportunityId: opp.id,
    stage,
    approvals: { program: "approved", director: "approved" },
    evidence: {},
    comments: [],
    activity: [],
    sections: Object.fromEntries(
      SECTION_IDS.map((s) => [
        s,
        edited && s === "program"
          ? { text: "Our own words", origin: "human", updatedAt: "" }
          : { text: "", origin: "empty", updatedAt: "" },
      ]),
    ),
  }) as unknown as Application;

const show = (a: Application) => {
  const up = vi.fn();
  render(
    <I18nProvider locale="en">
      <DraftPanel opp={opp} app={a} up={up} />
    </I18nProvider>,
  );
  return up;
};
const fetchMock = vi.fn();
const reply = (status: number, body: unknown) =>
  fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify(body), { status }),
  );

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

it("is locked until the drafting stage", () => {
  show(app("approval"));
  expect(
    screen.getByText(/Drafting unlocks after program and director approval\./),
  ).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Draft with AI" })).toBeNull();
});

it("asks before overwriting human edits, and Cancel changes nothing", () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  const up = show(app("drafting", true));
  fireEvent.click(screen.getByRole("button", { name: "Draft with AI" }));
  expect(confirm).toHaveBeenCalledWith(
    "This will overwrite sections you edited. Continue?",
  );
  expect(fetchMock).not.toHaveBeenCalled();
  expect(up).not.toHaveBeenCalled();
});

it.each([
  [
    503,
    { error: "missing_openai_key" },
    "AI drafting is unavailable: OPENAI_API_KEY is not configured on the server. Nothing was changed.",
  ],
  [
    502,
    { error: "agent_failed" },
    "The AI agent failed to produce a draft. Nothing was changed — try again.",
  ],
])(
  "a %i shows the exact message and changes nothing",
  async (status, body, message) => {
    reply(status, body);
    const up = show(app("drafting"));
    fireEvent.click(screen.getByRole("button", { name: "Draft with AI" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(up).not.toHaveBeenCalled();
  },
);

it("a network failure shows the exact message", async () => {
  fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  const up = show(app("drafting"));
  fireEvent.click(screen.getByRole("button", { name: "Draft with AI" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Network error — nothing was changed.",
  );
  expect(up).not.toHaveBeenCalled();
});

it("after an error, the template fills all six sections as template", async () => {
  reply(503, { error: "missing_openai_key" });
  reply(
    200,
    hopeTemplate({
      locale: "en",
      mode: "template",
      profile: DEMO_PROFILE,
      opportunity: opp,
      ask: opp.amountMax,
    }),
  );
  const up = show(app("drafting"));
  fireEvent.click(screen.getByRole("button", { name: "Draft with AI" }));
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Use the built-in template instead",
    }),
  );
  await waitFor(() => expect(up).toHaveBeenCalledTimes(1));
  expect(JSON.parse(fetchMock.mock.calls[1]![1].body).mode).toBe("template");
  const [fn, event] = up.mock.calls[0]!;
  expect(event).toBe("draft:template");
  const next = fn(app("drafting")) as Application;
  for (const s of SECTION_IDS)
    expect(next.sections[s]).toMatchObject({ origin: "template" });
  expect(next.sections.budget.text).toContain("Total: USD 50,000");
});
