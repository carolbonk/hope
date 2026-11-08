import type { Stage } from "@/lib/hope/types";

export type DeadlineItem = { id: string; oppId: string; name: string; funder: string; stage: Stage; deadline: string; days: number };

export const SOON_DAYS = 14;

export const appHref = (item: DeadlineItem) => `/hope/applications/${item.oppId}`;

export function urgency(days: number): "overdue" | "soon" | "later" {
  return days < 0 ? "overdue" : days <= SOON_DAYS ? "soon" : "later";
}

export const parseDay = (iso: string) => new Date(iso + "T00:00:00");

export const intlLocale = (locale: string) => (locale === "es" ? "es-US" : "en-US");
