import type { Money } from "@hope/schemas";

const MINOR_DIGITS = 2;

export function formatMoney(money: Money | null | undefined, opts: { compact?: boolean } = {}): string {
  if (!money) return "—";
  const fmt = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: money.currency ?? "USD",
    notation: opts.compact ? "compact" : "standard",
    minimumFractionDigits: 0,
    maximumFractionDigits: opts.compact ? 1 : MINOR_DIGITS,
  });
  return fmt.format(money.amount_minor / 10 ** MINOR_DIGITS);
}

/** Parses a user-typed major-unit amount ("1,250,000.50") into integer minor units without floats. */
export function parseMajorToMinor(input: string): number | null {
  const cleaned = input.replace(/[\s,$]/g, "");
  const match = /^(\d+)(?:\.(\d{0,2}))?$/.exec(cleaned);
  if (!match) return null;
  const [, whole = "0", frac = ""] = match;
  return Number(whole) * 100 + Number(frac.padEnd(MINOR_DIGITS, "0"));
}

export function minorToMajorString(amountMinor: number): string {
  const whole = Math.trunc(amountMinor / 100);
  const frac = Math.abs(amountMinor % 100);
  return frac ? `${whole}.${String(frac).padStart(2, "0")}` : String(whole);
}

export const formatBps = (bps: number | null | undefined): string =>
  bps == null ? "—" : `${(bps / 100).toFixed(bps % 100 ? 2 : 0)}%`;
