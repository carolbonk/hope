import type { Money } from "@hope/schemas";
import { apiFetch, online } from "@/lib/api/http";
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

export type NeedsCheckReason = "no_amount" | "no_deadline" | "currency";

const CURRENCIES: readonly Currency[] = ["USD", "EUR", "MXN", "COP"];
const STATUSES = ["new", "saved", "passed"] as const;
const ELIGIBILITY_FALLBACK = "Funder's eligibility rules (check the source page)";

const FOCUS_KEYWORDS: Record<string, string[]> = {
  mentoring: ["mentor"],
  youth: ["youth", "young people", "teen"],
  family: ["family", "families"],
  mental_health: ["mental health", "behavioral", "substance use"],
  health: ["health", "dental", "clinic", "medical", "family planning"],
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

const counties = (text: string) => [...new Set(text.match(/\b[A-Z][a-z]+(?: [A-Z][a-z]+)? County, [A-Z]{2}\b/g) ?? [])];

/** Places the funder's text names as "Chelan County, WA". A federal notice is limited only by counties its
 * eligibility names; one its summary merely mentions still covers the United States. */
function geographyOf(text: string, eligibility: string, federal: boolean): string[] {
  if (!federal) return counties(`${text} ${eligibility}`);
  const limited = counties(eligibility);
  return limited.length ? limited : ["United States"];
}

/** "Mental health" and "behavioral health" are not general health. */
const focusText = (key: string, text: string) => (key === "health" ? text.replace(/\b(mental|behavioral)\s+health/gi, "") : text);

function isFederal(url: string): boolean {
  try {
    return new URL(url).hostname.toLowerCase().endsWith(".gov");
  } catch {
    return false;
  }
}

/** A deck card for every found grant. Unknowns stay `null` (see `isCheck`); nothing is guessed. */
export function toOpportunity(card: GrantCard): Opportunity {
  const text = `${card.title} ${card.summary ?? ""}`;
  const eligibility = card.eligibility_summary?.trim() || null;
  const requirements: Opportunity["requirements"] = [{ id: "funder_eligibility", label: eligibility ?? ELIGIBILITY_FALLBACK }];
  if (eligibility && /501\(c\)\(3\)/i.test(eligibility)) requirements.push({ id: "c3", label: "501(c)(3)", field: "has501c3", expect: "yes" });
  const federal = isFederal(card.url);
  const max = card.amount_max && isCurrency(card.amount_max.currency) ? card.amount_max : null;
  const amountMax = max ? max.amount_minor / 100 : null;
  const words = (t: string | null | undefined) => t?.trim() || null;
  return {
    id: card.grant_id,
    funder: card.funder,
    name: card.title,
    amountMin: max ? (card.amount_min ?? max).amount_minor / 100 : null,
    amountMax,
    currency: (max?.currency ?? "USD") as Currency,
    geography: geographyOf(text, eligibility ?? "", federal),
    fundingType: "grant",
    focusAreas: Object.keys(FOCUS_KEYWORDS).filter((key) => FOCUS_KEYWORDS[key]!.some((w) => hasWord(focusText(key, text), w))),
    purpose: purposeOf(text),
    deadline: card.deadline,
    ...(needsCheck(card)
      ? {
          amountText: words(card.amount_text),
          deadlineText: words(card.deadline_text),
          otherCurrency: card.amount_max && !max ? (card.amount_max.currency ?? null) : null,
          summary: words(card.summary),
        }
      : {}),
    requirements,
    federal,
    ...(federal ? { docs: ["uei", "sam"] as const satisfies Opportunity["docs"] } : {}),
    source: { kind: "verified", url: card.url, verifiedAt: card.discovered_at.slice(0, 10) },
    funderContext: null,
  };
}

/** A grant still missing an amount or a date: Discover marks it "⚠ Check" and every page shows the unknown. */
export const isCheck = (o: Opportunity) => o.amountMax === null || o.deadline === null;

/** "Rolling" only when the page said so; otherwise an unknown date is just not found. */
export const isRolling = (o: Opportunity) => !o.deadline && /rolling|ongoing|open until|year[-\s]round/i.test(o.deadlineText ?? "");

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
    const cards = lists.flat().map(toOpportunity);
    return cards.length ? cards : null;
  } catch (err) {
    console.warn("hope sync: opportunities", err);
    return null;
  }
}
