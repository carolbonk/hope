// H6 application help: the funder's own form, translated terms, drafted answers and the checklist,
// all from `/v1/applications`. Writes send `If-Match: <version>`; a stale version is a 412.
// H4 on the server: eligibility evidence, internal approvals, comments and stage moves, mirrored into
// the browser `Application` with `mirror`.
import { API_URL, apiFetch, ProblemError } from "@/lib/api/http";
import type { Application, Stage, TriState } from "@/lib/hope/types";

export type Owner = "program" | "finance" | "director";
export type Limit = { unit: "words" | "characters" | "pages"; max: number; includes_spaces?: boolean | null };
export type Sourced = { text: string; url: string };
export type Question = { key: string; prompt: string; url: string; source: "page" | "pasted" | "standard"; section?: string | null; required: boolean; limit_text?: string | null; limit?: Limit | null; conflict?: boolean };
export type Attachment = { name: string; quote: string; url: string };
export type PageRead = { url: string; status: "read" | "failed" | "no_info"; reason?: string | null };
export type Requirements = {
  questions: Question[];
  attachments: Attachment[];
  budget: { format?: Sourced | null; max_request?: Sourced | null; match_rule?: Sourced | null; indirect_rule?: Sourced | null };
  submission: { method?: Sourced | null; deadline?: Sourced | null; deadline_date?: string | null };
  eligibility: Sourced[];
  pages: PageRead[];
};
export type Job = { job_id: string; status: string; error: string | null };
export type Citation = { ref: string | null; kind: "profile" | "funder" | "unsourced"; text: string; url?: string; path?: string };
export type Answer = { question_key: string; text: string; origin: "ai" | "template" | "human"; citations: Citation[]; to_confirm: string[]; updated_at: string };
export type TermStatus = "have" | "check" | "action_needed" | "at_risk" | "info";
export type Term = {
  key: string | null;
  term: string;
  plain: string;
  explained_by: "official" | "funder" | "hope" | "ai";
  source_url?: string | null;
  quote: string;
  url: string;
  owner?: Owner | null;
  todo?: string | null;
  lead_days: number;
  status: TermStatus;
  detail?: string | null;
};
export type RuleStatus = "met" | "not_met" | "unknown" | "applies" | "not_applicable";
export type Rule = { key: string; kind: "eligibility" | "budget" | "conditional"; label: string; status: RuleStatus; reason: string; quote: string; url: string; owner: Owner; todo?: string | null; confirmed_by_staff: boolean };
export type Change = { what: "question" | "limit" | "upload" | "deadline" | "max_request" | "eligibility" | "rule"; change: "added" | "removed" | "changed"; text: string; before?: string | null };
export type Fact = { need: string; answer: string; shared: boolean; updated_at: string };
export type ChecklistItem = { kind: "question" | "attachment" | "budget" | "deadline" | "submission" | "prep" | "rule"; key: string; label: string; status: string; detail?: string | null; owner?: Owner | null; count?: number | null; limit?: Limit | null; quote?: string | null; url?: string | null };
export type InputNeeded = { owner: Owner; text: string; question_key?: string | null; answer?: string | null; fact?: string | null; rule?: string | null };
export type Step = "program" | "director";
export type Approval = { by: string; at: string; comment?: string | null };
export type Evidence = { status: TriState; note?: string | null; by: string; at: string };
export type AppEvent = { kind: string; actor: string | null; payload: Record<string, unknown>; at: string };
export type ApplicationView = {
  application_id: string;
  grant_id: string;
  title: string;
  funder: string;
  url: string;
  stage: Stage;
  approvals: Partial<Record<Step, Approval>>;
  evidence: Record<string, Evidence>;
  events: AppEvent[];
  questions_status: "unread" | "reading" | "found" | "not_found";
  version: number;
  updated_at: string;
  requirements: Requirements | null;
  requirements_job: Job | null;
  answers_job: Job | null;
  questions: Question[];
  answers: Answer[];
  terms: Term[];
  facts: Fact[];
  rules: Rule[];
  changes: Change[];
  requirements_revision: number | null;
  ask: { amount_minor: number; currency: string } | null;
  checklist: { items: ChecklistItem[]; inputs_needed: InputNeeded[]; complete: boolean };
};

export const PASTED = "pasted";
const WORDS_PER_PAGE = 500;
const base = (id: string) => `/v1/applications/${id}`;
const post = <T>(path: string, body?: unknown, version?: number) =>
  apiFetch<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body), headers: version === undefined ? undefined : { "If-Match": `"${version}"` } });

export const running = (job: Job | null | undefined) => job?.status === "queued" || job?.status === "running";

/** Counts the way the funder does (and the backend's `measure`). */
export function measure(text: string, limit: Limit): number {
  const words = text.split(/\s+/).filter(Boolean).length;
  if (limit.unit === "words") return words;
  if (limit.unit === "pages") return Math.ceil(words / WORDS_PER_PAGE);
  const characters = Array.from(text);
  if (limit.includes_spaces !== false) return characters.length;
  // Python str.split() also treats U+001C–U+001F as whitespace, but not U+FEFF.
  return characters.filter((char) => !/\p{White_Space}/u.test(char) && !"\u001c\u001d\u001e\u001f".includes(char)).length;
}

export async function findApplication(grantId: string): Promise<ApplicationView | null> {
  const list = await apiFetch<{ items: { application_id: string; grant_id: string }[] }>("/v1/applications");
  const hit = list.items.find((a) => a.grant_id === grantId);
  return hit ? getApplication(hit.application_id) : null;
}

export const getApplication = (id: string) => apiFetch<ApplicationView>(base(id));
export const readRequirements = (id: string) => post<ApplicationView>(`${base(id)}/requirements/jobs`);
export const pasteForm = (id: string, body: { text: string } | { pdf_base64: string }) => post<ApplicationView>(`${base(id)}/requirements/paste`, body);
export const draftAll = (id: string) => post<ApplicationView>(`${base(id)}/answers/draft-all`);
export const draftOne = (id: string, key: string, confirmOverwrite = false) =>
  post<ApplicationView>(`${base(id)}/answers/${encodeURIComponent(key)}/draft`, { confirm_overwrite: confirmOverwrite });
export const editAnswer = (id: string, key: string, text: string, version: number) =>
  apiFetch<ApplicationView>(`${base(id)}/answers/${encodeURIComponent(key)}`, { method: "PATCH", body: JSON.stringify({ text }), headers: { "If-Match": `"${version}"` } });
export const setAsk = (id: string, amountMinor: number, version: number) => post<ApplicationView>(`${base(id)}/ask`, { amount_minor: amountMinor }, version);
export const confirmRule = (id: string, key: string, yes: boolean, version: number) =>
  post<ApplicationView>(`${base(id)}/evidence`, { requirement_id: key, status: yes ? "yes" : "no" }, version);
export const supplyFact = (id: string, need: string, answer: string, version: number) => post<ApplicationView>(`${base(id)}/facts`, { need, answer }, version);

export const moveStage = (id: string, to: Stage, version: number, overrideReason?: string) =>
  post<ApplicationView>(`${base(id)}/stage`, overrideReason ? { to, override_reason: overrideReason } : { to }, version);
export const review = (id: string, body: { step: Step; decision: "approve" | "send_back"; comment?: string }, version: number) =>
  post<ApplicationView>(`${base(id)}/approvals`, body, version);
export const addComment = (id: string, text: string) => post<ApplicationView>(`${base(id)}/comments`, { text });

/** The server's own gate for `ready` (`READY_BLOCKERS` in the pillar API). */
const READY_BLOCKERS = new Set(["missing", "over_limit", "to_confirm", "upload_needed", "passed"]);
export const readyGaps = (view: ApplicationView) => view.checklist.items.filter((i) => READY_BLOCKERS.has(i.status));

/** What the server said: a blocked move's reason, else the problem's `detail`. */
export const problemMessage = (err: ProblemError) => err.errors[0]?.message ?? err.message;

/** A short, stable label for one server event, in the browser activity format (`stage:approval`). */
export function eventLabel(e: AppEvent): string {
  const p = e.payload;
  if (e.kind === "stage") return `stage:${p.to}`;
  if (e.kind === "evidence") return `evidence:${p.requirement_id}=${p.status}`;
  if (e.kind === "approval") return `${p.step}:approved`;
  if (e.kind === "send_back") return `${p.step}:sent_back`;
  if (e.kind === "draft" || e.kind === "edit") return `${e.kind}:${p.question_key}`;
  return e.kind;
}

/** The server record as the browser `Application`: stage, approvals, evidence, comments and activity.
 * `who` names an actor (the signed-in user or a teammate). Sections stay as they are. */
export function mirror(view: ApplicationView, app: Application, who: (actor: string | null) => string): Application {
  const events = [...view.events].reverse();
  const lastSendBack = events.findLast((e) => e.kind === "send_back");
  const sentBack = view.stage !== "approval" && !view.approvals.program && lastSendBack ? (lastSendBack.payload.step as Step) : null;
  const approval = (step: Step) => (view.approvals[step] ? "approved" : sentBack === step ? "sent_back" : "pending");
  return {
    ...app,
    stage: view.stage,
    approvals: { program: approval("program"), director: approval("director") },
    evidence: Object.fromEntries(Object.entries(view.evidence).map(([k, e]) => [k, { status: e.status, note: e.note ?? "" }])),
    comments: events
      .filter((e) => (e.kind === "comment" && e.payload.text) || (e.kind === "send_back" && e.payload.comment))
      .map((e) => ({ id: `${e.at}:${e.kind}`, author: who(e.actor), text: String(e.payload.text ?? e.payload.comment), at: e.at })),
    activity: events.map((e) => ({ at: e.at, event: `${eventLabel(e)} · ${who(e.actor)}` })),
    updatedAt: view.updated_at,
  };
}

export async function exportMarkdown(id: string): Promise<string> {
  const res = await fetch(`${API_URL}${base(id)}/export.md`, { credentials: "include" });
  if (!res.ok) throw new ProblemError(res.status, `http_${res.status}`, res.statusText);
  return res.text();
}
