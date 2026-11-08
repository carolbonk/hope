import type { Money } from "@hope/schemas";
import { apiFetch, online } from "@/api/http";
import type { Currency, Opportunity, Purpose } from "../types";

/** One `GET /v1/grants` item (H3's `GrantCard`); only the fields this adapter reads. */
export type GrantCard = {
  grant_id: string;
  title: string;
  funder: string;
  url: string;
  summary: string | null;
  amount_text?: string | null;
  amount_max: Money | null;
  amount_min?: Money | null;
  deadline_text?: string | null;
  deadline: string | null;
  eligibility_summary?: string | null;
  discovered_at: string;
};

/** A found grant the deck can't use as a full card: what Hope read, with the unknowns left unknown. */
export type CheckCard = {
  id: string;
  title: string;
  funder: string;
  url: string;
  summary: string | null;
  /** Major units, only when the page gave an amount in a UI currency. */
  amount: { min: number; max: number; currency: Currency } | null;
  /** The page's own words, when Hope quoted any. */
  amountText: string | null;
  /** Set when the page's amount is in a currency the UI doesn't show. */
  otherCurrency: string | null;
  deadline: string | null;
  deadlineText: string | null;
  verifiedAt: string;
};

export type NeedsCheckReason = "no_amount" | "no_deadline" | "currency";

const CURRENCIES: readonly Currency[] = ["USD", "EUR", "MXN", "COP"];
const STATUSES = ["new", "saved", "passed"] as const;
const ELIGIBILITY_FALLBACK = "Funder's eligibility rules (check the source page)";

const FOCUS_KEYWORDS: Record<string, string[]> = {
  mentoring: ["mentor"],
  youth: ["youth", "young people", "teen"],
  family: ["family", "families"],
  mental_health: ["mental health", "behavioral"],
  safety: ["safety", "violence"],
  school_based: ["school"],
  capacity: ["capacity", "operating"],
  arts: ["arts", "mural"],
};

/** Matches at a word start, so "mentor" also finds "mentoring" and "school" finds "schools". */
const hasWord = (text: string, word: string) => new RegExp(`\\b${word.replace(/ /g, "\\s+")}`, "i").test(text);

function isCurrency(c: string | undefined): c is Currency {
  return CURRENCIES.includes((c ?? "USD") as Currency);
}

/** Why a found grant can't be a deck card (the deck needs an amount, a date and a UI currency). */
export function needsCheck(g: { amount_max: Money | null; deadline: string | null }): NeedsCheckReason | null {
  if (!g.amount_max) return "no_amount";
  if (!g.deadline) return "no_deadline";
  if (!isCurrency(g.amount_max.currency)) return "currency";
  return null;
}

function purposeOf(text: string): Purpose {
  if (/general\s+operating/i.test(text)) return "general_operating";
  if (hasWord(text, "capacity")) return "capacity";
  if (hasWord(text, "capital")) return "capital";
  return "program";
}

function isFederal(url: string): boolean {
  try {
    return new URL(url).hostname.toLowerCase().endsWith(".gov");
  } catch {
    return false;
  }
}

export function toOpportunity(card: GrantCard): Opportunity | null {
  if (needsCheck(card) || !card.amount_max || !card.deadline) return null;
  const text = `${card.title} ${card.summary ?? ""}`;
  const eligibility = card.eligibility_summary?.trim() || null;
  const requirements: Opportunity["requirements"] = [{ id: "funder_eligibility", label: eligibility ?? ELIGIBILITY_FALLBACK }];
  if (eligibility && /501\(c\)\(3\)/i.test(eligibility)) requirements.push({ id: "c3", label: "501(c)(3)", field: "has501c3", expect: "yes" });
  const federal = isFederal(card.url);
  const amountMax = card.amount_max.amount_minor / 100;
  return {
    id: card.grant_id,
    funder: card.funder,
    name: card.title,
    amountMin: card.amount_min ? card.amount_min.amount_minor / 100 : amountMax,
    amountMax,
    currency: (card.amount_max.currency ?? "USD") as Currency,
    geography: [],
    fundingType: "grant",
    focusAreas: Object.keys(FOCUS_KEYWORDS).filter((key) => FOCUS_KEYWORDS[key]!.some((w) => hasWord(text, w))),
    purpose: purposeOf(text),
    deadline: card.deadline,
    requirements,
    federal,
    ...(federal ? { docs: ["uei", "sam"] as const satisfies Opportunity["docs"] } : {}),
    source: { kind: "verified", url: card.url, verifiedAt: card.discovered_at.slice(0, 10) },
    funderContext: null,
  };
}

/** A card for the "check amount/deadline" part of the deck, or `null` when `toOpportunity` takes it. */
export function toCheckCard(card: GrantCard): CheckCard | null {
  if (!needsCheck(card)) return null;
  const max = card.amount_max && isCurrency(card.amount_max.currency) ? card.amount_max : null;
  const text = (t: string | null | undefined) => t?.trim() || null;
  return {
    id: card.grant_id,
    title: card.title,
    funder: card.funder,
    url: card.url,
    summary: text(card.summary),
    amount: max ? { min: (card.amount_min ?? max).amount_minor / 100, max: max.amount_minor / 100, currency: (max.currency ?? "USD") as Currency } : null,
    amountText: text(card.amount_text),
    otherCurrency: card.amount_max && !max ? (card.amount_max.currency ?? null) : null,
    deadline: card.deadline,
    deadlineText: text(card.deadline_text),
    verifiedAt: card.discovered_at.slice(0, 10),
  };
}

type GrantList = { items: GrantCard[]; total?: number };
const PAGE = 100;

async function listAll(status: (typeof STATUSES)[number]): Promise<GrantCard[]> {
  const cards: GrantCard[] = [];
  for (let offset = 0; ; offset += PAGE) {
    const page = await apiFetch<GrantList>(
      `/v1/grants?status=${status}&sort=fit&include_past=true&limit=${PAGE}${offset ? `&offset=${offset}` : ""}`,
    );
    cards.push(...page.items);
    if (page.items.length < PAGE || cards.length >= (page.total ?? 0)) return cards;
  }
}

let inflight: Promise<GrantCard[][]> | null = null;

/** One set of `/v1/grants` reads shared by callers in the same moment (Discover asks twice on mount). */
function listStatuses(): Promise<GrantCard[][]> {
  inflight ??= Promise.all(STATUSES.map(listAll)).finally(() => {
    inflight = null;
  });
  return inflight;
}

/** H0's contract: never rejects; `null` = use the demo catalog (sync off, nothing found yet, or any error). */
export async function fetchOpportunities(): Promise<Opportunity[] | null> {
  if (!online) return null;
  try {
    const lists = await listStatuses();
    const cards = lists.flatMap((l) => l.map(toOpportunity)).filter((o): o is Opportunity => o !== null);
    return cards.length ? cards : null;
  } catch (err) {
    console.warn("hope sync: opportunities", err);
    return null;
  }
}

/** Undecided found grants missing an amount, a deadline or a UI currency. Never rejects; `[]` when sync is off or on error. */
export async function fetchCheckCards(): Promise<CheckCard[]> {
  if (!online) return [];
  try {
    const [fresh = []] = await listStatuses();
    return fresh.map(toCheckCard).filter((c): c is CheckCard => c !== null);
  } catch (err) {
    console.warn("hope sync: check cards", err);
    return [];
  }
}
