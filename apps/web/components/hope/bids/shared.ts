import type { BidItem, ItemStatus, Member } from "./api";

/** Server grants (the only ones that can have a bid) have UUID ids; demo opportunities don't. */
export const GRANT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const statusTone: Record<ItemStatus, string> = {
  missing: "bg-[#f6e3df] text-red-800",
  working: "bg-[#f1ead8] text-[#6b5520]",
  ready: "bg-[#dcefe9] text-teal-ink",
};

/** A user id as a display name: "You", a teammate's name, or a generic label. Never an email. */
export const namer = (members: Member[], me: string | undefined, labels: { you: string; teammate: string }) => (id: string | null) =>
  !id ? "" : id === me ? labels.you : (members.find((m) => m.user_id === id)?.display_name ?? labels.teammate);

export type ItemFilter = "all" | "missing" | "unassigned" | "unreviewed";
export const matches = (i: BidItem, f: ItemFilter) =>
  f === "missing" ? i.status !== "ready" : f === "unassigned" ? !i.owner : f === "unreviewed" ? i.review?.decision !== "approved" || i.review.stale : true;
