import { useHopeT } from "@/lib/hope/i18n";

/** Copy for saved grants whose funder page gave no date. */
type NoDateCopy = { title: string; hint: string; unknown: string; rolling: string };

const en: NoDateCopy = {
  title: "No date yet",
  hint: "Hope couldn't find a deadline on these funders' pages. Check the page; they aren't on the calendar.",
  unknown: "Deadline not found",
  rolling: "Rolling, no fixed date",
};

const es: NoDateCopy = {
  title: "Sin fecha todavía",
  hint: "Hope no encontró una fecha límite en las páginas de estos financiadores. Revisa la página; no están en el calendario.",
  unknown: "Fecha no encontrada",
  rolling: "Continua, sin fecha fija",
};

export function useNoDateCopy(): NoDateCopy {
  return useHopeT().locale === "es" ? es : en;
}
