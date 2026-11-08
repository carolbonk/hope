import { useHopeT } from "@/lib/hope/i18n";

/** Copy for Discover's "check amount/deadline" cards (found grants Hope couldn't fully read). */
type CheckCopy = {
  badge: (amount: boolean, deadline: boolean) => string;
  why: string;
  amount: string;
  deadline: string;
  amountUnknown: string;
  deadlineUnknown: string;
  currency: (c: string) => string;
  rolling: string;
  pageSays: (q: string) => string;
  dueOn: (d: string) => string;
  openPage: string;
  pass: string;
  keys: string;
};

const en: CheckCopy = {
  badge: (amount: boolean, deadline: boolean): string =>
    amount && deadline
      ? "Check amount and deadline"
      : amount
        ? "Check amount"
        : deadline
          ? "Check deadline"
          : "Check amount/deadline",
  why: "Hope found this grant but couldn't read every detail from the funder's page. Check the page before you plan around it.",
  amount: "Amount",
  deadline: "Deadline",
  amountUnknown: "Amount not found",
  deadlineUnknown: "Deadline not found",
  currency: (c: string): string => `Not in a currency Hope shows (${c})`,
  rolling: "Rolling, no fixed date",
  pageSays: (q: string): string => `Page says: "${q}"`,
  dueOn: (d: string): string => `Due ${d}`,
  openPage: "Open funder page",
  pass: "Pass",
  keys: "Keyboard: ← pass",
};

const es: CheckCopy = {
  badge: (amount, deadline) =>
    amount && deadline
      ? "Revisa el monto y la fecha"
      : amount
        ? "Revisa el monto"
        : deadline
          ? "Revisa la fecha"
          : "Revisa monto/fecha",
  why: "Hope encontró esta subvención pero no pudo leer todos los datos en la página del financiador. Revísala antes de planificar.",
  amount: "Monto",
  deadline: "Fecha límite",
  amountUnknown: "Monto no encontrado",
  deadlineUnknown: "Fecha no encontrada",
  currency: (c) => `En una moneda que Hope no muestra (${c})`,
  rolling: "Continua, sin fecha fija",
  pageSays: (q) => `La página dice: "${q}"`,
  dueOn: (d) => `Vence ${d}`,
  openPage: "Abrir página del financiador",
  pass: "Pasar",
  keys: "Teclado: ← pasar",
};

export function useCheckCopy() {
  return useHopeT().locale === "es" ? es : en;
}
