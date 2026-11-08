// My bids on the server (`/v1/bids`, pillar `bids.py`). The server decides blockers, the plan and every
// transition; writes send `If-Match: <version>` and a stale copy is a 412.
import { apiFetch } from "@/lib/api/http";
import type { Limit } from "@/lib/hope/sync/applications";

export type ItemStatus = "missing" | "working" | "ready";
export type Phase = "preparing" | "final_reviewed" | "submitted";
export type Decision = "approved" | "changes_requested";
export type BlockerCode = "no_requirements" | "checklist_incomplete" | "no_owner" | "not_ready" | "not_reviewed" | "stale_review" | "deadline_passed";
export type Review = { by: string; at: string; decision: Decision; comment: string; stale: boolean };
export type BidItem = {
  key: string;
  kind: string;
  label: string;
  checklist_status: string;
  quote: string | null;
  url: string | null;
  limit: Limit | null;
  owner: string | null;
  due: string | null;
  status: ItemStatus;
  note: string;
  evidence_ref: string;
  review: Review | null;
};
export type Blocker = { code: BlockerCode; key?: string | null; detail?: string | null };
export type Milestone = { key: "owners" | "drafts" | "reviews" | "final_review"; due: string; done: boolean };
export type BidSummary = {
  application_id: string;
  grant_id: string;
  title: string;
  funder: string;
  deadline: string | null;
  phase: Phase;
  ready: number;
  total: number;
  blockers: number;
  updated_at: string;
};
export type BidView = BidSummary & {
  url: string;
  version: number;
  items: BidItem[];
  blocker_list: Blocker[];
  plan: Milestone[];
  final_review: { by: string; at: string; comment: string } | null;
  submission: { receipt: string; portal: string; submitted_at: string; recorded_by: string; recorded_at: string; sent_by_hope: false } | null;
  created_at: string;
};
export type Member = { user_id: string; display_name: string };
export type ItemChanges = Partial<{ owner: string | null; due: string | null; status: ItemStatus; note: string; evidence_ref: string }>;

const one = (grantId: string) => `/v1/bids/${encodeURIComponent(grantId)}`;
const write = (path: string, method: "POST" | "PUT", body: unknown, version: number) =>
  apiFetch<BidView>(path, { method, body: JSON.stringify(body), headers: { "If-Match": `"${version}"` } });

export const listBids = () => apiFetch<{ items: BidSummary[]; total: number }>("/v1/bids").then((r) => r.items);
export const startBid = (grantId: string) => apiFetch<BidView>("/v1/bids", { method: "POST", body: JSON.stringify({ grant_id: grantId }) });
export const getBid = (grantId: string) => apiFetch<BidView>(one(grantId));
/** Display names only: the email the API also returns is never kept. */
export const listMembers = () =>
  apiFetch<{ items: Member[] }>("/v1/members").then((r) => r.items.map(({ user_id, display_name }) => ({ user_id, display_name })));
export const updateItem = (grantId: string, key: string, changes: ItemChanges, version: number) =>
  write(`${one(grantId)}/items/${encodeURIComponent(key)}`, "PUT", changes, version);
export const reviewItem = (grantId: string, key: string, decision: Decision, comment: string, version: number) =>
  write(`${one(grantId)}/items/${encodeURIComponent(key)}/review`, "POST", { decision, comment }, version);
export const finalReview = (grantId: string, comment: string, version: number) => write(`${one(grantId)}/final-review`, "POST", { comment }, version);
export const recordSubmission = (grantId: string, body: { receipt: string; portal: string; submitted_at: string }, version: number) =>
  write(`${one(grantId)}/submission`, "POST", body, version);
