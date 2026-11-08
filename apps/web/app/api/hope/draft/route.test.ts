// @vitest-environment node
import { demoOpportunities } from "@/lib/hope/demo";
import { emptyProfile } from "@/lib/hope/store";
import type { HopeDraftRequest } from "@/lib/hope/draft";
import { agentInput, NOT_STATED } from "./input";
import { POST } from "./route";

const unknown = { ...demoOpportunities(new Date("2026-11-07T12:00:00"))[0]!, amountMin: null, amountMax: null, deadline: null };
const body = (mode: "agent" | "template") => ({ locale: "en", mode, ask: null, profile: emptyProfile(), opportunity: unknown });
const post = (b: unknown) => POST(new Request("http://test/api/hope/draft", { method: "POST", body: JSON.stringify(b) }));

afterEach(() => vi.unstubAllEnvs());

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
  expect(input.opportunity).toMatchObject({ amountMin: NOT_STATED, amountMax: NOT_STATED });
  expect(JSON.stringify(input)).not.toContain("NaN");
});

it("still rejects a bad ask", async () => {
  expect((await post({ ...body("template"), ask: -5 })).status).toBe(400);
});
