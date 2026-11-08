# H6: Application help built from each grant's own requirements

| | |
|---|---|
| Wave | After H1-H3 work end to end (the save on H3 starts it) |
| Depends on | H0 (auth, jobs, web tools, model gateway, store); H1 `/v1/profile`; H2 `grant_candidates` + `hope_discovery` fetch/quote helpers; H3 save |
| Screens | SC27/SC28 `/hope/applications/[oppId]` (built; H6 swaps its data source, no page rebuilt) |
| Migrations | `db/migrations/0720_applications.sql` (range 0720-0729) |
| Status | Built (PR #53) |

## Goal

Every funder asks different things. Once a nonprofit saves a grant, Hope:
1. **reads that grant's application requirements** from the funder's own pages: questions, word / character / page
   limits, required attachments, budget format, how and where to submit, and the deadline;
2. **turns them into a checklist** for this grant, marking what the profile and dossier already cover and what staff
   still have to supply;
3. **drafts an answer to each real question** from the profile, within its limit, with `[TO CONFIRM: ...]` for
   anything not in the profile, and every claim citing the profile or the funder's page;
4. **stores the application on the server**: requirements, answers, edits, comments, approvals and stage.

Staff edit, approve and submit. **Hope never submits.**

Today H4/H5 keep the application in the browser and H5 drafts the same 6 sections for every grant. H6 replaces both
with server data. When a grant's questions can't be found, the 6 H5 sections stay as a labelled fallback.

## Rules (same as H2)

- **LLMs suggest, code decides.** Every model call is `ModelGateway.structured(...)` with a Pydantic model in
  `hope_applications/models.py`. The model never outputs a limit number, money, a date, a stage or a URL code didn't
  give it.
- **No quote, no requirement.** Every question, limit, attachment and budget rule keeps the exact quote and URL it
  came from; code checks the quote is on the page (`hope_discovery.extract` helpers). A requirement without a quote
  is dropped.
- **Code parses numbers.** "500 words", "2,500 characters including spaces", "no more than 2 pages", "$25,000
  maximum request" are parsed in code (`parse_limit`, `hope_discovery.parse.parse_amount`).
- **Not found is never no.** A missing budget format is `not_found`, shown as "Check the funder's portal", never
  "no budget needed".
- **Untrusted text.** Page text is wrapped with `untrusted(..., label="web_page")`. The model has no tools.
- **Tenancy and money.** `tenant_tx` as `hope_app`; `Money` in integer minor units everywhere on the server and
  wire (fixes H5's known gap: `ask_minor` + currency).
- **Never overwrite human work.** An answer with `origin = human` is never replaced without `confirm_overwrite`.

## Behaviour: backend

### A. Application record

- Created by `POST /v1/grants/{grant_id}/save` (H3) if none exists: one per tenant and grant, `UNIQUE (tenant_id,
  grant_id)`. Pass then save again reuses it; reset never deletes it.
- Stages are code-controlled, in order: `saved -> eligibility -> approval -> drafting -> ready`. The allowed
  transitions are the H4/H5 gates, now enforced by the API (409 `stage_blocked` with the reason).
- Every change writes a row to `application_events` (who, when, what). This is the activity log and comments.
- Concurrency: `version` integer; every write needs `If-Match` (as `/v1/profile`), else 412.

### B. Reading the requirements (job kind `requirements`)

Starts automatically after the first save, and again on "Re-read requirements". One at a time per application.

1. **Pages (code).** Start at the grant's URL. Follow same-site links whose text or URL matches
   `apply|application|guideline|rfp|request for proposal|nofo|instructions|faq|budget|template|loi|letter of
   inquiry` (PDF included), best first, up to 6 pages and 400k characters total. Robots, SSRF and size limits come
   from `hope_core.web.fetch`. Blocked pages (403) are listed in the job result.
2. **Extract (LLM, one call per page, retry once).** Returns `RequirementsExtraction`:
   - `questions[]`: `{prompt: Quote, limit: Quote | null, section: str | null, required: bool}` (max 25);
   - `attachments[]`: `{name: str, quote: Quote}` (max 20), e.g. "IRS determination letter", "board list",
     "most recent audit";
   - `budget`: `{format: Quote | null, template_link_index: int | null, max_request: Quote | null,
     indirect_rule: Quote | null, match_rule: Quote | null}`;
   - `submission`: `{method: Quote | null, portal_link_index: int | null, deadline: Quote | null}`;
   - `eligibility[]`: quotes, reused for the H4 checklist.
3. **Verify (code).** Drop anything whose quote isn't on the page. Parse limits into `{unit: words | characters |
   pages, max: int, includes_spaces: bool | null}`; unparseable limits keep the quote and `max = null`. Parse
   amounts and the deadline with the H2 parsers. Merge pages: same question text (normalised) becomes one question
   with several sources; conflicting limits keep both quotes and flag `conflict`.
4. **Save.** `application_requirements` replaces the previous read as a new `revision`; answers stay linked to
   questions by `question_key` (a hash of the normalised prompt), so re-reading never loses drafted text.
5. **Result.** `found_questions = 0` sets `questions_status = not_found`; the UI falls back to the 6 H5 sections
   and says "We couldn't find this funder's questions. Check the portal; these are standard sections."

### C. Checklist (code only)

`GET /v1/applications/{id}` returns `checklist[]`, built on every read:
- one item per question: `missing | drafted | edited | over_limit`;
- one per attachment: matched to the H4 dossier documents by name rules (`irs_letter`, `board_list`, `audit`,
  `budget`, `w9`, ...) with dossier status, otherwise `upload_needed`;
- budget: `not_found | needs_budget | drafted`, with the parsed max request and match / indirect rules;
- eligibility rows (H4 rule: evidence beats profile beats unknown);
- deadline and submission method, with their quotes.
`inputs_needed[]` lists every `[TO CONFIRM: ...]` from drafts plus checklist gaps, grouped for program / finance /
director, so the right person fills them.

### D. Drafting an answer (LLM per question)

`POST /v1/applications/{id}/answers/{question_key}/draft` (or `.../draft-all`, a job):
- Input: the profile digest with `P#` ids (H2 `build_digest`), the question and its limit, the grant's quotes with
  `W#` ids, and the other answers' first lines (to avoid repeating).
- Output `AnswerDraft`: `text`, `claims[] {sentence_index, refs[]}`, `to_confirm[]`.
- Code: drop refs that don't exist; count words / characters as the funder does; if over the limit, one retry
  asking for a shorter answer, then save with `over_limit` rather than truncating mid-sentence. Store
  `origin = ai`, model, prompt version and citations.
- Budget: when the funder has a format, draft line items as integer minor units that code sums to `ask_minor`
  (rejected if they don't sum); otherwise the H5 budget + narrative sections.

### E. Edits, review and approval

- `PATCH /v1/applications/{id}/answers/{question_key}` `{text}` sets `origin = human`.
- `POST /v1/applications/{id}/approvals` `{step: program | director, decision: approve | send_back, comment}`: the
  H4 rules, recorded with the signed-in user and time. Roles aren't assigned yet, so any signed-in user may approve;
  the UI says so and shows who approved (H4).
- `POST /v1/applications/{id}/stage` `{to: "ready", override_reason?}` needs both approvals and a complete checklist
  (no `missing`, `over_limit`, `to_confirm`, `upload_needed` or `passed` item). Otherwise 409 `stage_blocked`, unless
  `override_reason` (10-500 chars) is given; the reason is saved on the stage event. The web asks for it in `ReadyGate`.
- `GET /v1/applications/{id}/export.md`: every question with its limit and answer, the attachment list and the
  budget, ready to paste into the funder's portal.

### F. API summary

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/applications` | list with stage, deadline, checklist counts |
| GET | `/v1/applications/{id}` | record + requirements + answers + checklist + `inputs_needed` |
| POST | `/v1/applications/{id}/requirements/jobs` | re-read; 409 `job_running` |
| GET | `/v1/applications/{id}/requirements/jobs/{job_id}` | progress, pages read / blocked |
| POST | `/v1/applications/{id}/answers/{key}/draft` | one answer; `confirm_overwrite` |
| POST | `/v1/applications/{id}/answers/draft-all` | job |
| PATCH | `/v1/applications/{id}/answers/{key}` | human edit, `If-Match` |
| POST | `/v1/applications/{id}/evidence` | H4 eligibility evidence per requirement |
| POST | `/v1/applications/{id}/comments` | |
| POST | `/v1/applications/{id}/approvals` | |
| POST | `/v1/applications/{id}/stage` | code-checked transition |
| GET | `/v1/applications/{id}/export.md` | |

Errors use the existing problem format: 401 `not_signed_in`, 404 `application_not_found`, 409 `stage_blocked` /
`job_running`, 412 `version_mismatch`, 422 `validation_failed`, 428 `if_match_required`.

## Data (`0720_applications.sql`, all with tenant RLS)

- `applications (application_id, tenant_id, grant_id UNIQUE per tenant, stage, version, ask_minor, currency,
  questions_status, created_at, updated_at)`
- `application_requirements (application_id, revision, questions jsonb, attachments jsonb, budget jsonb,
  submission jsonb, eligibility jsonb, pages jsonb, read_at)`
- `application_answers (application_id, question_key, text, origin, model, prompt_version, citations jsonb,
  to_confirm jsonb, word_count, char_count, updated_by, updated_at)`
- `application_events (event_id, application_id, kind, actor, payload jsonb, at)` for comments, evidence,
  approvals, stage changes and drafts.

Shared contracts (`ApplicationView`, `Requirement`, `ChecklistItem`, `AnswerView`) go in `hope_core.schemas`,
then `hope-export-schemas`.

## Behaviour: web (no page rebuilt)

`lib/hope/sync/applications.ts` loads and writes the server record behind the existing `useHope()` application
functions. The workspace shows the funder's questions (with limit and live word count) instead of the 6 fixed
sections when `questions_status = found`. `/api/hope/draft` stays only as the fallback for `not_found`.
Offline or signed out, the browser-only behaviour stays.

## Owns

```text
services/applications/ (hope_applications: agent, models, prompts, parse_limit, checklist, mock)
services/pillar/src/hope_pillar/api/applications.py
db/migrations/0720_applications.sql
apps/web/lib/hope/sync/applications.ts (+ test)
```

## Acceptance criteria

- [ ] AC1 Saving a grant creates one application and starts a requirements job; saving again reuses both.
- [ ] AC2 Every question, limit, attachment and budget rule has a quote found on its page; others are dropped.
- [ ] AC3 "500 words", "2,500 characters (including spaces)", "two pages" parse to the right unit and max.
- [ ] AC4 No questions found sets `not_found` and the 6-section fallback, with the exact notice.
- [ ] AC5 A drafted answer stays within its limit or is marked `over_limit`; it is never cut mid-sentence.
- [ ] AC6 Every drafted claim cites a `P#` or `W#`; uncited facts appear as `[TO CONFIRM: ...]` and in `inputs_needed`.
- [ ] AC7 Human edits are never overwritten without `confirm_overwrite`.
- [ ] AC8 Stage gates are enforced by the API; `ready` is refused while questions are missing or over limit.
- [ ] AC9 Budget lines are integer minor units summing exactly to `ask_minor`.
- [ ] AC10 Another tenant can't read or change an application (RLS test).

## Test plan (offline)

`MockProvider` + `hope_applications.mock.register`, `RecordedWebTools` with 3 recorded funders (a community
foundation with an online form, a state agency RFP PDF, a funder with no published questions), `HOPE_JOBS_INLINE=1`.
Unit: `parse_limit`, quote verification, question merging, checklist rules, word counting, budget sum. API: every
route incl. 401/404/409/412/422 and RLS. Contract snapshot in `services/pillar/tests/snapshots/openapi`.

## Build order

1. Migration, store functions, `GET/POST` application record, stage gates, events (no LLM).
2. Requirements job: link following, extraction, verification, `parse_limit`, merge.
3. Checklist and `inputs_needed`.
4. Per-question drafting and export.
5. Web sync adapter; questions replace the fixed sections when found.

## Out of scope

Submitting to funders or logging into their portals, uploading or storing attachment files, real reviewer roles,
DOCX/PDF export.

## Decisions needed

1. Grants.gov API for federal requirements (structured NOFO data) vs. pages only (H2 rule: OpenAI is the only
   outside service). Default: pages only.
2. Does H6 need real roles (program / finance / director) now, or keep "simulated" approvals? Default: simulated.
