const HOUR = 3_600_000;
const DAY = 24 * HOUR;

export type Urgency = "overdue" | "urgent" | "soon" | "ok";

export interface Countdown {
  label: string;
  urgency: Urgency;
  msRemaining: number;
}

export function countdown(due: string | Date, now: Date, thresholds = { urgentMs: DAY, soonMs: 3 * DAY }): Countdown {
  const ms = new Date(due).getTime() - now.getTime();
  const abs = Math.abs(ms);
  const days = Math.floor(abs / DAY);
  const hours = Math.floor((abs % DAY) / HOUR);
  const span = days >= 1 ? `${days}d ${hours}h` : hours >= 1 ? `${hours}h` : `${Math.max(1, Math.floor(abs / 60_000))}m`;
  if (ms < 0) return { label: `${span} overdue`, urgency: "overdue", msRemaining: ms };
  const urgency: Urgency = ms <= thresholds.urgentMs ? "urgent" : ms <= thresholds.soonMs ? "soon" : "ok";
  return { label: `${span} left`, urgency, msRemaining: ms };
}

export const daysUntil = (due: string | Date, now: Date): number =>
  Math.ceil((new Date(due).getTime() - now.getTime()) / DAY);

export const formatDateTime = (iso: string): string =>
  new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));

export const formatDate = (iso: string): string =>
  new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(new Date(iso));

export const addHours = (base: Date, hours: number): string => new Date(base.getTime() + hours * HOUR).toISOString();
export const addDays = (base: Date, days: number): string => addHours(base, days * 24);
