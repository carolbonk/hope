import type { Opportunity, OrgProfile, SectionId } from "./types";

export type HopeDraftRequest = { locale: "en" | "es"; profile: OrgProfile; opportunity: Opportunity; ask: number; mode: "agent" | "template" };
export type HopeDraftResult = { source: "agent" | "template"; model?: string; sections: Record<SectionId, string>; reviewerNotes: string[] };
export type HopeDraftError = "missing_openai_key" | "agent_failed" | "invalid_request";

const fmt = (n: number | null, c: string) => (n == null ? "[TO CONFIRM]" : `${c} ${Math.round(n).toLocaleString("en-US")}`);

/** Deterministic template built only from the profile and opportunity. Used only when the user asks for it. */
export function hopeTemplate({ locale, profile: p, opportunity: o, ask }: HopeDraftRequest): HopeDraftResult {
  const es = locale === "es";
  const c = o.currency;
  const tc = es ? "[POR CONFIRMAR]" : "[TO CONFIRM]";
  const lines = [
    [es ? "Personal del programa" : "Program staff", 0.6],
    [es ? "Materiales y actividades" : "Materials and activities", 0.15],
    [es ? "Evaluación y datos" : "Evaluation and data", 0.1],
    [es ? "Costos indirectos" : "Indirect costs", 0.15],
  ] as const;
  const budget = lines.map(([l, s]) => `• ${l}: ${fmt(ask * s, c)}`).join("\n") + `\n${es ? "Total" : "Total"}: ${fmt(ask, c)}`;
  return {
    source: "template",
    sections: {
      program: es
        ? `${o.name} — ${o.funder}\n\n${p.mission || tc}\n\nPoblación: ${p.targetPopulation || tc}. Área de servicio: ${p.serviceArea || tc}.\n\n${p.fundingNeed || tc}`
        : `${o.name} — ${o.funder}\n\n${p.mission || tc}\n\nPopulation: ${p.targetPopulation || tc}. Service area: ${p.serviceArea || tc}.\n\n${p.fundingNeed || tc}`,
      alignment: es
        ? `Visión: ${p.vision || tc}\nEnfoques compartidos con el financiador: ${o.focusAreas.filter((f) => p.focusAreas.includes(f)).join(", ") || tc}.`
        : `Vision: ${p.vision || tc}\nFocus areas shared with the funder: ${o.focusAreas.filter((f) => p.focusAreas.includes(f)).join(", ") || tc}.`,
      logicModel: es
        ? `Insumos: ${tc}\nActividades: ${tc}\nProductos: ${tc}\nResultados a corto plazo: ${tc}\nImpacto a largo plazo: ${tc}`
        : `Inputs: ${tc}\nActivities: ${tc}\nOutputs: ${tc}\nShort-term outcomes: ${tc}\nLong-term impact: ${tc}`,
      objectives: es
        ? `1. ${tc} (meta, fecha y cómo se mide)\n2. ${tc}\n3. ${tc}`
        : `1. ${tc} (target, date and how it is measured)\n2. ${tc}\n3. ${tc}`,
      budget,
      budgetNarrative: es
        ? `Se solicitan ${fmt(ask, c)} de un presupuesto anual de ${fmt(p.annualBudget, p.currency)}. ${tc}`
        : `We request ${fmt(ask, c)} against an annual budget of ${fmt(p.annualBudget, p.currency)}. ${tc}`,
    },
    reviewerNotes: [es ? "Plantilla: completa cada [POR CONFIRMAR]." : "Template: fill in every [TO CONFIRM]."],
  };
}
