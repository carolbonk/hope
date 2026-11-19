// @vitest-environment node
import { demoOpportunities } from "@/lib/hope/demo";
import { emptyProfile } from "@/lib/hope/store";
import type { HopeDraftRequest } from "@/lib/hope/draft";
import { agentInput, NOT_STATED } from "./input";
import { POST } from "./route";

const agents = vi.hoisted(() => ({ run: vi.fn() }));
vi.mock("@openai/agents", () => ({
  Agent: class {
    constructor(public opts: unknown) {}
  },
  run: agents.run,
}));

const unknown = {
  ...demoOpportunities(new Date("2026-11-07T12:00:00"))[0]!,
  amountMin: null,
  amountMax: null,
  deadline: null,
};
const body = (mode: "agent" | "template") => ({
  locale: "en",
  mode,
  ask: null,
  profile: emptyProfile(),
  opportunity: unknown,
});
const post = (b: unknown) =>
  POST(
    new Request("http://test/api/hope/draft", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  );

afterEach(() => {
  vi.unstubAllEnvs();
  agents.run.mockReset();
});

it("accepts a grant with no amount and never shows a number for it", async () => {
  const res = await post(body("template"));
  expect(res.status).toBe(200);
  const text = JSON.stringify(await res.json());
  expect(text).toContain("[TO CONFIRM]");
  expect(text).not.toMatch(/NaN|null|USD 0\b/);
});

it("gets past validation in agent mode too", async () => {
  vi.stubEnv("OPENAI_API_KEY", "");
  expect((await post(body("agent"))).status).toBe(503);
});

it("tells the agent the amount is not stated", () => {
  const input = agentInput(body("agent") as unknown as HopeDraftRequest);
  expect(input.ask).toBe(NOT_STATED);
  expect(input.opportunity).toMatchObject({
    amountMin: NOT_STATED,
    amountMax: NOT_STATED,
  });
  expect(JSON.stringify(input)).not.toContain("NaN");
});

it("still rejects a bad ask", async () => {
  expect((await post({ ...body("template"), ask: -5 })).status).toBe(400);
});

const SIX = {
  program: "p",
  alignment: "a",
  logicModel: "l",
  objectives: "o",
  budget: "b",
  budgetNarrative: "n",
};
const priced = {
  ...body("agent"),
  ask: 25000,
  opportunity: { ...unknown, amountMin: 10000, amountMax: 25000 },
};

it("rejects invalid JSON, a missing field and an oversized body with 400 invalid_request", async () => {
  const raw = await POST(
    new Request("http://test/api/hope/draft", {
      method: "POST",
      body: "{not json",
    }),
  );
  expect(raw.status).toBe(400);
  expect(await raw.json()).toEqual({ error: "invalid_request" });
  expect((await post({ ...priced, locale: undefined })).status).toBe(400);
  expect(
    (
      await post({
        ...priced,
        profile: { ...emptyProfile(), mission: "x".repeat(40_001) },
      })
    ).status,
  ).toBe(400);
});

it("returns 503 missing_openai_key without calling the agent", async () => {
  vi.stubEnv("OPENAI_API_KEY", "");
  const res = await post(priced);
  expect(res.status).toBe(503);
  expect(await res.json()).toEqual({ error: "missing_openai_key" });
  expect(agents.run).not.toHaveBeenCalled();
});

it("template mode returns all six sections and never calls the agent", async () => {
  vi.stubEnv("OPENAI_API_KEY", "");
  const res = await post({ ...priced, mode: "template" });
  expect(res.status).toBe(200);
  const data = await res.json();
  expect(data.source).toBe("template");
  expect(Object.keys(data.sections).sort()).toEqual(Object.keys(SIX).sort());
  expect(agents.run).not.toHaveBeenCalled();
});

it("agent mode returns the agent's sections with source agent", async () => {
  vi.stubEnv("OPENAI_API_KEY", "test-key");
  agents.run.mockResolvedValue({
    finalOutput: { sections: SIX, reviewerNotes: ["check the budget"] },
  });
  const res = await post(priced);
  expect(res.status).toBe(200);
  expect(await res.json()).toMatchObject({
    source: "agent",
    sections: SIX,
    reviewerNotes: ["check the budget"],
  });
  expect(agents.run.mock.calls[0]![2]).toEqual({ maxTurns: 4 });
});

it("an agent error or empty output is 502 agent_failed", async () => {
  vi.stubEnv("OPENAI_API_KEY", "test-key");
  vi.spyOn(console, "error").mockImplementation(() => {});
  agents.run.mockRejectedValueOnce(new Error("boom"));
  const failed = await post(priced);
  expect(failed.status).toBe(502);
  expect(await failed.json()).toEqual({ error: "agent_failed" });
  agents.run.mockResolvedValueOnce({ finalOutput: undefined });
  expect((await post(priced)).status).toBe(502);
});
