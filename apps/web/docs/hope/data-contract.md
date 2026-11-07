# Hope — shared data contract (frontend ⇄ backend)

Hope is a demo slice: funding discovery (swipe deck) connected to an application workspace through **one shared record**. Today the record lives in the browser (`localStorage`). This file is the contract the backend (Jimmy, Carol) implements so the UI (Carito) can switch from local storage to an API without redesigning screens.

Source of truth for the types: `lib/hope/types.ts`. Persistence and business rules: `lib/hope/store.ts`.

## Storage today

| Item | Value |
| --- | --- |
| Key | `hope:state:v1` |
| Scope | One browser. Not shared, not production storage, no sign-in. Shown in the UI. |
| Shape | `{ version: 1, profile, decisions, history, applications }` |
| Organization ID | `org-local-1` (single local org) |
| Application ID | `app:${orgId}:${opportunityId}` (stable, one per org/opportunity pair) |

Carito's prototype (`hope-ux-handoff.zip`) used `hope.ux.v1`, with applications keyed by opportunity ID. This build keeps `hope:state:v1` and maps the prototype fields like this: `narrative` → `sections.program` / `sections.alignment`; `budget` → `sections.budget` / `sections.budgetNarrative`; `notes` → `comments[]`; `eligibility` (boolean) → `evidence` (Yes / No / Unknown per requirement); `approved` (boolean) → `approvals.program` + `approvals.director`.

## Entities

### OrgProfile (one per organization)
Collected in five steps: identity → mission & programs → capacity → documents & requirements → review. Types: `lib/hope/types.ts`; rules: `lib/hope/dossier.ts`.

Completing the profile is **not** legal certification and does not guarantee eligibility for any opportunity. The UI says so on every step.

- **Identity:** `legalName, publicName, country ("" | US | MX | CO | other), jurisdiction, website, contactName, contactEmail, responsibleName, responsibleRole, legalStatus (501c3|other_nonprofit|fiscal_sponsor|unknown), has501c3 (yes|no|unknown — asked only when country = US), usTaxStatus (yes|no|unknown — US federal tax status, asked only when country is set and not US)`
- **Mission & programs:** `mission, vision, targetPopulation, servesMinors (yes|no|unknown), serviceArea, focusAreas[], programs[{ id, name, description, outcomes (measurable result), served (number | null) }]`
- **Capacity:** `annualBudget (number | null), currency (USD|EUR|MXN|COP), fiscalYear, staffCount, volunteerCount, foundedYear, experience, fundingNeed, intendedUse[]`
- **Documents & requirements:** `dossier{ [ReqId]: RequirementRecord }` (below)
- **Review:** `reviews{ [key]: { by, at, note, value, simulated: true } }, reviewRequest { at, delivery: "local_only" } | null, completedSteps (0–5), updatedAt`

`null` / `""` / `"unknown"` means **not answered** and is never shown as "No". Older `hope:state:v1` profiles are migrated in `normalizeProfile` (old `documents` → `dossier`, `samRegistered: yes` → `dossier.sam`).

### Document dossier (one per organization, shared by profile and every application)

`RequirementRecord = { status: pending|declared|not_applicable, naReason, evidenceRef, period, expires (YYYY-MM-DD | ""), comments[{ id, by, at, text }] }`

- `evidenceRef` is an **example filename or reference only**. Nothing is uploaded; sensitive documents must never go to `localStorage`. Real files need private storage plus access authorization (backend track).
- `not_applicable` requires `naReason`; otherwise it stays pending.
- `expires` in the past makes the item pending again ("expired").

| Group | ReqId |
| --- | --- |
| Identity & governance | `incorporation`, `irs_501c3`, `ein_letter` (separate from the 501(c)(3) letter), `bylaws`, `good_standing`, `board_list` |
| Registrations requested by a call | `w9`, `uei`, `sam` (UEI and SAM.gov are separate) |
| Finance & results | `annual_report`, `form_990` (990 / 990-EZ / 990-N / exemption, or local equivalent outside the US), `financials`, `annual_budget` (current annual budget — no separate "current-year budget") |
| Policies | `coi_policy`, `child_protection` |

`applicability(id, profile, opportunity?)` returns `usual | when_asked | auto_na | needs_info` with a reason:
- No country yet → US-specific items are `needs_info`.
- Non-US → `irs_501c3`, `ein_letter` are `auto_na`; `form_990` becomes "local equivalent"; `good_standing` is `when_asked`.
- US + `has501c3 = no` → `irs_501c3` is `auto_na`; `unknown` → `needs_info`.
- `uei`, `sam` are `when_asked` unless the opportunity lists them in `docs[]` or is `federal: true`.
- `w9` is not decided by country alone. It is `when_asked` unless the call lists it in `docs[]`. When a call asks for it:
  - US entity with a known legal/tax status → `usual`.
  - US entity with `legalStatus: "unknown"`, or a fiscal sponsor (whose W-9 the call wants is unclear) → `needs_info` ("Requires review").
  - Non-US entity: `usTaxStatus: "yes"` → `usual`; `"unknown"` → `needs_info` ("Requires review"); `"no"` → `auto_na`.
  - No country → `needs_info`. Hope never suggests an alternative form.
- `needs_info` is shown as **Requires review / Requiere revisión**.
- `child_protection`: minors yes → `usual`; no → `auto_na`; unknown → `needs_info`.

Only `usual` and `needs_info` items appear in the pending list. `oppDocs(opportunity, profile)` gives the per-call checklist shown in the application workspace — read from the same dossier, never copied.

#### Statuses and the three separate states
Each field / requirement is **pending**, **declared** (by the organization; "No" and "Not applicable + reason" are declarations) or **reviewed (simulated)**. A simulated review is tied to the value it saw; any edit drops it back to declared.

"Verified" is never shown: there is no sign-in, no authorized reviewer and no lookup against IRS/SAM.gov. A backend may introduce a real `verified` status only when it enforces reviewer identity and stores the evidence (`simulated: false`).

The review step shows three independent states (`summary(profile)`):
1. **Profile complete** — required fields answered.
2. **Documentation reviewed** — reviewed by an authorized person. Always "Not yet" in this prototype; simulated reviews don't count.
3. **Eligibility for an opportunity** — decided per call in its workspace, never by the profile.

Users can explore opportunities with pending items; each call has its own requirements.

#### Review request
"Request team review" stores `reviewRequest = { at, delivery: "local_only" }` and the UI states it was **not sent** — there is no backend, sign-in or reviewer queue. A backend should set `delivery: "sent"` only after the server accepts it.

### Opportunity (catalog, read-only for the nonprofit)
`id, funder, name, amountMin, amountMax, currency, geography[], fundingType (grant|contract|sponsorship|in_kind), focusAreas[], purpose, deadline (YYYY-MM-DD), requirements[{ id, label, field?, expect? }], docs?: ReqId[] (documents this call asks for), federal?: boolean, source { kind: demo|verified, url?, verifiedAt? }, funderContext { previousGrantees[], awardHistory[], sourceUrl? } | null`

- Every current opportunity is fictional, with `source.kind = "demo"` (`lib/hope/demo.ts`).
- `verified` opportunities need `url` + `verifiedAt`; the card shows both.
- `funderContext` is shown only when sourced; otherwise the UI shows an honest empty state.

### Decision (discovery)
`decisions[opportunityId] = { decision: saved|passed, at }` plus `history[]` for undo. **Saved means the nonprofit is interested. It never means the funder responded.**

### Application (one per org/opportunity pair)
`id, orgId, opportunityId, stage (saved|eligibility|approval|drafting|ready), approvals { program, director: pending|approved|sent_back }, evidence{ [requirementId]: { status: yes|no|unknown, note } }, sections{ program|alignment|logicModel|objectives|budget|budgetNarrative: { text, origin: empty|ai|template|human, updatedAt } }, comments[{ id, author, text, at }], activity[{ at, event }] (last 50), createdAt, updatedAt`

Required documents are not stored per application: the workspace reads them from the organization dossier with `oppDocs`. Saving creates this record; passing and then saving again reuses the same ID, and undo never deletes edits.

## Rules the backend must keep

1. **Eligibility** (`requirementStatus`, `eligibility`): recorded evidence wins → known profile facts → otherwise Unknown. Result: `meets` (all Yes), `not_qualified` (any No), `needs_review` (any Unknown).
2. **Stage gates**: `eligibility → approval` only when no requirement is No/Unknown. Director review only after program approval. Send back requires a comment. Drafting only after both approvals. `ready` = ready for **human** submission. Hope never submits.
3. **Approvals** are simulated (no sign-in or role enforcement) and are always labeled "Approved (simulated)". They are internal readiness steps, never funder approval.
4. **Drafts**: AI or template output never silently overwrites a section whose `origin` is `human`; the UI asks first.
5. **Match reasons** (`matchReasons`): shared focus areas, geography, purpose matches intended use, award ≤ 40% of annual budget. These are explanations, not eligibility claims.

## API

Existing:

- `POST /api/hope/draft` with body `{ locale, mode: "agent"|"template", ask, profile, opportunity }`
  - `200 { source, model?, sections{6}, reviewerNotes[] }`
  - `503 { error: "missing_openai_key" }`, `502 { error: "agent_failed" }`, `400` for an invalid body
  - The template is returned only for `mode: "template"`, which the user must click explicitly.
  - Env vars: `OPENAI_API_KEY` (required for the agent), `OPENAI_MODEL` (optional).

Proposed (not built, for the backend track):

| Method | Path | Replaces |
| --- | --- | --- |
| GET/PUT | `/api/orgs/:orgId/profile` | `saveProfile` |
| GET | `/api/opportunities?geo&amount&type&focus&deadline&purpose` | `demoOpportunities` |
| PUT | `/api/orgs/:orgId/decisions/:oppId` | `decide` / `undo` |
| GET | `/api/orgs/:orgId/applications` | `state.applications` |
| PATCH | `/api/applications/:appId` | `updateApplication` (send a section-level patch plus `updatedAt` for optimistic concurrency) |
| POST | `/api/applications/:appId/approvals` | approval actions, enforced server-side by role |

Real approvals need sign-in and server-enforced roles. Until then the UI labels approvals as **simulated**.
