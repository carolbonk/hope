// H6 application help: the funder's own form, translated terms, drafted answers and the checklist,
// all from `/v1/applications`. Writes send `If-Match: <version>`; a stale version is a 412.
import { API_URL, apiFetch, ProblemError } from "@/api/http";

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
export type ApplicationView = {
  application_id: string;
  grant_id: string;
  title: string;
  funder: string;
  url: string;
  stage: string;
  questions_status: "unread" | "reading" | "found" | "not_found";
  version: number;
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
  return limit.includes_spaces === false ? text.replace(/\s+/g, "").length : text.length;
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

export async function exportMarkdown(id: string): Promise<string> {
  const res = await fetch(`${API_URL}${base(id)}/export.md`, { credentials: "include" });
  if (!res.ok) throw new ProblemError(res.status, `http_${res.status}`, res.statusText);
  return res.text();
}
