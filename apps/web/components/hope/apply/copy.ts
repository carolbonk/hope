"use client";

import { useHopeT } from "@/lib/hope/i18n";

// EN/ES copy for the server-backed H4 workspace (eligibility, approvals, the Ready gate).
const en = {
  loading: "Loading this application…",
  recorded: "Any signed-in teammate can approve for now. Hope records who approved and when.",
  approved: "Approved",
  approvedBy: (who: string, at: string) => `Approved by ${who} · ${at}`,
  you: "You",
  teammate: "A teammate",
  hope: "Hope",
  evidenceLocked: "Eligibility is locked while the application is in review.",
  gateTitle: "The checklist isn't complete",
  gateIntro: "Hope's checklist still has these gaps. To mark it ready anyway, write why. The reason is saved in Activity.",
  gateReason: "Why is it ready anyway?",
  gateShort: "Write at least 10 characters.",
  gateConfirm: "Mark ready anyway",
  cancel: "Cancel",
  gap: { missing: "Not answered", over_limit: "Over the limit", to_confirm: "Something to confirm", upload_needed: "Upload needed", passed: "Deadline passed" } as Record<string, string>,
};

const es: typeof en = {
  loading: "Cargando esta solicitud…",
  recorded: "Por ahora cualquier persona del equipo con sesión iniciada puede aprobar. Hope registra quién aprobó y cuándo.",
  approved: "Aprobado",
  approvedBy: (who, at) => `Aprobado por ${who} · ${at}`,
  you: "Tú",
  teammate: "Una persona del equipo",
  hope: "Hope",
  evidenceLocked: "La elegibilidad está bloqueada mientras la solicitud está en revisión.",
  gateTitle: "La lista no está completa",
  gateIntro: "A la lista de Hope todavía le faltan estos puntos. Para marcarla lista de todos modos, escribe por qué. El motivo queda en Actividad.",
  gateReason: "¿Por qué está lista de todos modos?",
  gateShort: "Escribe al menos 10 caracteres.",
  gateConfirm: "Marcar lista de todos modos",
  cancel: "Cancelar",
  gap: { missing: "Sin respuesta", over_limit: "Excede el límite", to_confirm: "Algo por confirmar", upload_needed: "Falta subir", passed: "La fecha límite pasó" },
};

export function useServerCopy() {
  const { locale } = useHopeT();
  return locale === "es" ? es : en;
}
