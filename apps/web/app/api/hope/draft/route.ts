import { Agent, run } from "@openai/agents";
import { z } from "zod";
import { hopeTemplate, type HopeDraftRequest, type HopeDraftResult } from "@/lib/hope/draft";
import { agentInput } from "./input";

export const maxDuration = 60;

const SECTIONS = ["program", "alignment", "logicModel", "objectives", "budget", "budgetNarrative"] as const;

const Body = z.object({
  locale: z.enum(["en", "es"]),
  mode: z.enum(["agent", "template"]).default("agent"),
  ask: z.number().positive().max(1e9).nullable(),
  profile: z.object({}).passthrough(),
  opportunity: z.object({ id: z.string(), funder: z.string(), name: z.string(), currency: z.string(), amountMin: z.number().nullable(), amountMax: z.number().nullable() }).passthrough(),
});

const Output = z.object({
  sections: z.object(Object.fromEntries(SECTIONS.map((s) => [s, z.string()])) as Record<(typeof SECTIONS)[number], z.ZodString>),
  reviewerNotes: z.array(z.string()),
});

export async function POST(request: Request) {
  const parsed = Body.safeParse(await request.json().catch(() => null));
  if (!parsed.success || JSON.stringify(parsed.data).length > 40_000) return Response.json({ error: "invalid_request" }, { status: 400 });
  const req = parsed.data as unknown as HopeDraftRequest;

  // The template is only produced on explicit request, never as a silent fallback.
  if (req.mode === "template") return Response.json(hopeTemplate(req) satisfies HopeDraftResult);
  if (!process.env.OPENAI_API_KEY) return Response.json({ error: "missing_openai_key" }, { status: 503 });

  const agent = new Agent({
    name: "Hope grant writer",
    ...(process.env.OPENAI_MODEL ? { model: process.env.OPENAI_MODEL } : {}),
    instructions: [
      "You draft a funding application for a small nonprofit. The input JSON has the organization profile and the opportunity.",
      "Use ONLY facts in the input. Never invent statistics, partners or outcomes; write [TO CONFIRM: ...] for anything missing.",
      "Sections: program (program description), alignment (alignment with mission and intended outcomes), logicModel (inputs, activities, outputs, outcomes, impact),",
      "objectives (3-5 measurable objectives with target, date and measure), budget (line items summing exactly to the ask), budgetNarrative.",
      'When the ask or an amount is "amount not stated", the funder page gave no amount: write [TO CONFIRM: amount] instead of any figure.',
      "This is a DRAFT a person reviews and submits. List what they must verify in reviewerNotes.",
      `Write in ${req.locale === "es" ? "Spanish (Latin American, US Hispanic audience)" : "English"}.`,
    ].join("\n"),
    outputType: Output,
  });

  try {
    const result = await run(agent, JSON.stringify(agentInput(req)), { maxTurns: 4 });
    if (!result.finalOutput) throw new Error("empty agent output");
    return Response.json({ source: "agent", model: process.env.OPENAI_MODEL ?? "OpenAI default", ...result.finalOutput } satisfies HopeDraftResult);
  } catch (err) {
    console.error("hope draft agent failed", err);
    return Response.json({ error: "agent_failed" }, { status: 502 });
  }
}
