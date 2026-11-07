# SC09: Agency profile

| | |
|---|---|
| Route | `/profile` (query: `as_of`, `history`, `section`; hash anchors `#mission`, `#capacity`, `#legal`, `#financials`, `#approvals`, `#programs`, `#program-{program_id}`, `#documents`) |
| Feature folder | `apps/web/src/features/profile/` (extends today's `ProfileEditor.tsx`, `SectionShell.tsx`, `sections.tsx`) |
| Built by | S09 |
| Primary users | Development director / org admin (weekly while onboarding, then monthly); finance director (each budget cycle, audit or NICRA renewal) |
| Can act | Edit sections, upload documents, propose a SAM.gov update: `org_admin`, `development_director`, `finance_director`, `program_lead`. Force a SAM.gov refresh: `org_admin`. View: any signed-in user |
| Status | Draft |

## 1. Purpose and user goals

The profile is everything Hope knows about the agency. Eligibility, scoring, budgets and
compliance all read it, so a wrong EIN or an expired SAM registration costs real grants.
Users arrive:
- from the nav;
- from SC03's "Complete your profile (63%)" empty state or a matched-program chip (`#program-{id}`);
- from a `profile.stale_field` notification ("SAM registration expires in 30 days");
- from SC10 after a decision.

Within 5 seconds the screen must answer:
1. Is our profile complete and current? (completeness score, alerts)
2. Is anything blocking federal applications? (SAM.gov registration status)
3. Is anything waiting for approval? (pending proposals count)

**Primary action:** fix what's missing or stale, by editing a section or uploading a
document that Hope extracts from.
**Secondary actions:**
- propose an update from SAM.gov;
- view the version history and diffs;
- view the profile as of a past date.

## 2. Information hierarchy

1. **Health strip.** Completeness score, active alerts and the SAM.gov status come first,
   because they tell the user whether the profile is fit to use.
2. **Pending-approval banner.** Shown only when proposals are pending, because edits to
   protected sections don't take effect until approved.
3. **Sections.** Mission and Capacity are editable directly. Legal, Financials and Approval
   hierarchy are marked "Requires approval (HITL-0)". Each section shows where its data came
   from (provenance), so users trust or correct it.
4. **Documents.** Upload and extraction status, with links to the proposals each document
   produced.
5. **Programs and grant history.** Read-only in this screen (see Open questions).

Hidden behind a click:
- **Version history and field diffs** (the History drawer): needed for audits, not daily work.
- **Dropped extraction values:** shown inside a document row, because most users only care
  about what was found.
- **Raw provenance details** (confidence, source reference): shown in a popover.

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ Agency profile                                         [🕘 Version history]  [⬆ Upload doc] │  <- PageHeader
│ Riverbend Community Health Alliance · version 14 · effective Sep 30, 2026 · by Marcus Lee   │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌ Completeness ──────┐ ┌ Needs attention (2) ───────────────┐ ┌ SAM.gov registration ─────┐ │  <- health strip (3 Cards raised)
│ │   (63%)  ◔         │ │ ⚠ SAM registration expires in 24 d │ │ ✓ Active · UEI R7KX4M2N9P1Q│ │
│ │ 6 of 16 missing    │ │   Dec 1, 2026 → Renew at SAM.gov ↗  │ │ Expires May 18, 2027 (192d)│ │
│ │ [See what's missing]│ │ ✕ Audit is older than 18 months    │ │ Checked 4 h ago  [↻]       │ │
│ └────────────────────┘ │   FY2024 audit → Upload new audit   │ │ ⚠ 1 difference from profile│ │
│                        └─────────────────────────────────────┘ │ [Propose update from SAM]  │ │
│                                                                 └───────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ 🔒 2 changes are waiting for approval (oldest due Nov 11).               [Review changes →] │  <- banner (Card inset, amber)
├──────────────────────────────────────────────┬──────────────────────────────────────────────┤
│ Mission                      Saves directly  │ Capacity                     Saves directly  │  <- section Cards (2-col grid)
│ Mission statement [__________________ ]      │ Grant writer FTE [ 1.5 ]                     │
│ Vision            [__________________ ]      │ Monthly hours    [ 120 ]                     │
│ Theory of change  [__________________ ]      │ Max concurrent   [ 4 ]                       │
│ Focus areas  (Rural health ×)(Oral ×) [+]    │ Cost-share capacity [$ 50,000.00 ]           │
│ NTEE codes   (E32 ×)(F30 ×) [+]              │                                              │
│                         [Reset] [Save]       │                         [Reset] [Save]       │
├──────────────────────────────────────────────┼──────────────────────────────────────────────┤
│ Legal        🔒 Requires approval (HITL-0)   │ Financials   🔒 Requires approval (HITL-0)   │
│ ⓘ From SAM.gov · verified by Dana · Sep 12   │ ⓘ From NICRA-2026.pdf · 86% · Nov 6          │
│ Legal name [Riverbend Community Health …]    │ Fiscal year ends  [06-30]  (FY2027 = Jul 1, 2026-Jun 30, 2027) │
│ DBA        (Riverbend Health ×) [+]          │ Operating budget  [$ 1,850,000.00]  Band: 1m-5m (auto) │
│ EIN [84-3917265]   UEI [R7KX4M2N9P1Q]        │ Indirect rate (Negotiated NICRA ▾) [26.50]% base [MTDC ▾] │
│ Tax status [501(c)(3) public charity ▾]      │   Agreement expires [2027-06-30]             │
│ State of incorporation [WA]                  │ Fringe rate [28.00]%                         │
│ SAM status [Active ▾] expires [2027-05-18]   │ Last audit (Single audit ▾) FY [2025] Findings (○ yes ● no) │
│                  [Reset] [Submit for approval]│                  [Reset] [Submit for approval]│
├──────────────────────────────────────────────┴──────────────────────────────────────────────┤
│ Approval hierarchy  🔒 Requires approval (HITL-0)                                            │
│ Gate               │ Approver roles               │ Min │ SLA   │ Escalate to   │           │
│ HITL-0 Profile     │ org_admin, finance_director  │ 1   │ 72 h  │ –             │ [✎] [🗑]  │
│ HITL-1 Go/No-Go    │ development_director         │ 1   │ 120 h │ exec director │ [✎] [🗑]  │
│ [+ Add rule]                                       [Reset] [Submit for approval]            │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Documents                                              [⬆ Upload a 990, audit or NICRA]      │  <- Card raised, id="documents"
│ File               │ Type      │ Uploaded        │ Status                            │       │
│ NICRA-2026.pdf     │ NICRA     │ Nov 6 · Dana    │ ✓ 4 fields found → Review         │       │
│ Audit-FY2025.pdf   │ Audit     │ Nov 7 · Dana    │ ◌ Reading document…               │       │
│ scan-990.pdf       │ Form 990  │ Nov 5 · Marcus  │ ✕ Scanned PDF, text not readable  │       │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Programs (2)  · read-only                     │ Grant history (5) · read-only               │
│ ▸ After-school STEM Lab · active · US-OH      │ HHS ACF · $250,000 · awarded · 2024-2026    │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

Version history drawer (480 px, right):
┌──────────────────────────────────────┐
│ Version history                  [×] │
│ ● v14 Sep 30, 2026 · Marcus Lee      │
│ ○ v13 Sep 12, 2026 · Dana Ortiz      │
│ ○ v12 Aug 2, 2026 · Dana Ortiz       │
│ Compare [v13 ▾] → [v14 ▾]            │
│ Field                Before   After  │
│ 🔒 legal.uei         –        R7KX…  │
│ mission.ntee_codes   E32      E32,F30│
│ [View profile as of v13 →]           │
└──────────────────────────────────────┘
```

Mobile (<= 640 px):
- The health strip becomes three stacked cards. "Needs attention" is shown first when it has alerts.
- Sections stack in one column, ordered Legal, Financials, Mission, Capacity, Approvals,
  Documents, Programs, so the protected sections with alerts come first.
- Each section is collapsible: closed by default except the first one with an error or alert.
- The approval-hierarchy table becomes a list of rule cards.
- The History drawer becomes a full-screen sheet.
- The Save/Submit buttons stick to the bottom of the open section.

## 4. Content inventory

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Agency name | `GET /v1/agencies/{id}/profile` → `profile.legal.legal_name` | "Riverbend Community Health Alliance" | Ellipsis after 60 chars, with a tooltip |
| Version line | `version`, `valid_from`, `recorded_by` | "version 14 · effective Sep 30, 2026 · by Marcus Lee" | `recorded_by` shown as a display name if S01's user list is available, else the raw id; `agent:*` shows "Hope" |
| As-of banner | `?as_of` + `valid_from` of the returned version | "Viewing the profile as it was on Sep 12, 2026 (version 13). Back to current" | All inputs read-only; Save and Upload hidden |
| Completeness | `GET .../profile/completeness` → `score`, `missing[]` | Ring "63%", "6 of 16 missing" | Ring tone: < 50 red ✕, 50-79 amber ⚠, ≥ 80 green ✓, always with text. "See what's missing" opens a popover listing labelled paths (`legal.uei` → "UEI (Legal)"), each a link to the section anchor that focuses the input |
| Alerts | `GET .../profile/alerts` → `alerts[]` | "SAM registration expires in 24 days (Dec 1, 2026)" | Order: `expired` first, then `7d`, `30d`, `60d`, `18m`. Icons: expired ✕ red, 7d ✕ red, 30d ⚠ amber, 60d ⓘ blue, 18m ✕ red. Action links: SAM → "Renew at SAM.gov ↗" (https://sam.gov); NICRA → "Upload new NICRA" (opens upload with kind preset); audit → "Upload new audit" |
| Alert copy by reason | `reason`, `days_remaining`, `ref_date` | `sam_expiring`: "SAM registration expires in {n} days"; `sam_expired`: "SAM registration expired on {date}"; `nicra_expiring`: "Indirect rate agreement expires in {n} days"; `nicra_expired`: "Indirect rate agreement expired on {date}"; `audit_outdated`: "Your FY{fy} audit is more than 18 months old" | `fy` = year of `ref_date` for a 12-31 fiscal-year end, else the FY computed from `fiscal_year_end` |
| SAM status | `GET .../registration` → `active`, `registration_status`, `registration_expiration_date`, `days_until_expiry`, `exclusion_flagged`, `checked_at`, `stale`, `mismatches[]` | "✓ Active · UEI R7KX4M2N9P1Q · Expires May 18, 2027 (192 d) · Checked 4 h ago" | `blocks_federal` true → red ✕ "Not active for federal awards"; `exclusion_flagged` → red ✕ "Exclusion on record"; `stale` → amber "Showing the last check from {time}; SAM.gov didn't respond" |
| SAM mismatches | `mismatches[]` (`path`, `profile`, `sam`) | "Expiry: profile Dec 1, 2026 · SAM.gov May 18, 2027" | Max 3, then "+n more". The button "Propose update from SAM.gov" shows only when mismatches exist and the user can edit |
| Pending banner | `GET .../profile/proposals?status=pending` → `items.length`, min `due_at` | "2 changes are waiting for approval (oldest due Nov 11)." | Hidden when 0. Red "overdue" text if `due_at` < now |
| Section badge | `lib/lifecycle.ts::isProtectedSection` | "🔒 Requires approval (HITL-0)" or "Saves directly" | Protected = `legal`, `financials`, `approval_hierarchy` (`PROTECTED_PROFILE_PATHS`) |
| Section pending chip | proposals whose `changes[].path` starts with the section key | "🔒 Change waiting for approval · View" | Links to `/profile/proposals?proposal={id}` |
| Provenance chip | `profile.legal.provenance`, `profile.financials.provenance` | "From SAM.gov · verified by Dana · Sep 12" | `source` labels: user_input "Entered by", document_extraction "From {filename}" (filename from sources), sam_gov "From SAM.gov", irs "From IRS", crm_sync "From CRM", erp_sync "From accounting", system "Set by Hope". The popover shows `confidence` as %, `source_ref` and `captured_at` |
| EIN | `legal.ein` | `84-3917265` | Input mask `NN-NNNNNNN`. Client checks the format; the server checks the IRS prefix (422 shown inline) |
| UEI | `legal.uei` | `R7KX4M2N9P1Q` | Uppercase on input; 12 chars, no I/O, first char not 0 |
| Tax status | `legal.tax_status` | Select with labels: "501(c)(3) public charity", "501(c)(3) private foundation", "501(c)(4)", "501(c)(6)", "Fiscally sponsored", "Government", "Tribal", "Other" | |
| Fiscal year end | `financials.fiscal_year_end` | `06-30`, helper "FY2027 = Jul 1, 2026 – Jun 30, 2027" | The helper is computed client-side with the same rule as `validators.fiscal_year_bounds`: FYs are named by the calendar year they end in |
| Operating budget | `financials.annual_operating_budget` | `$ 1,850,000.00` | Typed in dollars, sent as `amount_minor` (cents) via `lib/money.ts`. Never a float in the payload |
| Budget band | `financials.budget_band` | "1m-5m (set by Hope)" | Read-only; recalculated by the server |
| Indirect / fringe rate | `indirect_rate.rate_bps`, `fringe_rate_bps` | Shown as a percent with 2 decimals (2650 bps → "26.50%") | Input in percent, sent as integer bps (`Math.round(pct*100)`) |
| Last audit | `financials.last_audit` (`type`, `fiscal_year`, `findings`) | "Single audit · FY2025 · No findings" | |
| Approval rules | `approval_hierarchy[]` | Table: gate label (`lib/gates.ts::GATES[gate].title`), roles, `min_approvals`, `sla_hours`, `escalate_to_role` | At least one rule is required (the server returns 422 otherwise) |
| Documents | `GET /v1/agencies/{id}/sources` → `items[]` | Filename, kind label, `uploaded_at` + uploader, status | Status copy: queued "Waiting to be read", processing "Reading document…", proposed "{accepted.length} fields found → Review", nothing_found "Nothing Hope could use was found", failed by `error_code` (needs_ocr "Scanned PDF, text not readable yet", active_content "File rejected: it contains active content", extraction_failed "Hope couldn't read this file"). Newest first, 10 rows, "Show all" |
| Dropped values | `dropped{path: reason}` | "UEI: confidence 0.31 below 0.5" | Inside the expanded row only |
| Programs | `profile.programs[]` | name, status, geography | Each row has `id="program-{program_id}"` for SC03 deep links |
| Grant history | `profile.grant_history[]` | funder, amount (`Money`), outcome, period | Read-only |
| History list | `GET .../profile/history` | "v14 Sep 30, 2026 · Marcus Lee" | Newest first |
| Diff table | `GET .../profile/diff?from_version=&to_version=` | path label, before, after, 🔒 when `protected` | Money and bps fields formatted as above; lists shown comma-joined |

## 5. Components

- **Page header:** `PageHeader` with `Button` actions (secondary).
- **Health strip:** three `Card` (`neu-raised`).
  - The completeness ring is a local `ProgressRing` (SVG, with a text label inside).
  - The alerts list uses `Badge` + text.
  - The SAM card uses `Badge`, a `Button` with an icon for refresh, and a `Button` primary for
    "Propose update from SAM.gov".
- **Pending banner:** `Card` (`neu-inset`) with an amber `Badge` "lock" icon and a link `Button`.
- **Sections:** today's `SectionShell` (`Card` `neu-raised`, form, Reset/Save) with
  `TextField`, `TextArea`, `SelectField` and `Segmented`. Tag inputs (focus areas, NTEE, DBA)
  are a local `TagInput` built from `TextField` + `Badge` chips.
- **Approval hierarchy:** `Table`/`Th`/`Td`/`Tr`; the rule editor opens in a `Modal`.
- **Documents:** `Card` + `Table`. The upload flow opens a `Modal` with a file picker (the
  shared `FileDrop` is requested in S09's Shared contract additions; until then, a local
  `FileDrop` in `features/profile/`) and a kind `SelectField`.
- **Version history:** the shared `Drawer` (requested in SC03; until then `Modal`
  `variant="sheet"`).
- **Toasts:** `SuccessNotice` / `ErrorNotice` inline in the section that acted. There is no
  global toast in the MVP.

## 6. Interactions

1. **Edit a direct section (Mission, Capacity).**
   - Inputs mark the section dirty and Save becomes enabled.
   - Save → `PATCH /v1/agencies/{id}/profile`, headers `If-Match: <etag>` and
     `Content-Type: application/merge-patch+json`. The body is the section's merge patch,
     with `null` for cleared optional fields, for example
     `{"capacity": {"monthly_hours_available": 120}}`.
   - Pending UI: the Save button shows a spinner and the inputs are disabled.
   - `200 committed` → "Saved. The profile is now version 15." The new `ETag` is kept, and
     the header, completeness and alerts refetch.
   - `200 no_change` → "Nothing changed."
   - `409 version_conflict` → "Someone else updated the profile since you opened it." with
     "Reload and keep my edits". That button refetches the profile, keeps this section's draft
     values, and re-enables Save.
   - `422 validation_failed` → each `errors[]` entry that starts with a field path is shown
     under that input; the others in the section's error notice.
   - `403 forbidden` → "You can view the profile but not change it." The section becomes
     read-only.
   - `428` (should not happen) → treated like `version_conflict`.
2. **Edit a protected section (Legal, Financials, Approval hierarchy).**
   - The button reads "Submit for approval"; the call is the same.
   - `202 pending_approval` → the section shows "Sent for approval. {approver roles} will
     review it (due {due_at})." with "View request", which links to
     `/profile/proposals?proposal={proposal_id}`.
   - The inputs reset to the current (unchanged) values, the pending banner count increments,
     and the section shows the pending chip.
3. **Open a missing field.** In the completeness popover, click "UEI (Legal)". This scrolls
   to `#legal`, expands it on mobile, and focuses the UEI input.
4. **Upload a document.** Header or Documents "Upload" opens a modal with the file picker
   (accepts .pdf, .docx, .html, .xml, up to 25 MB) and Type (Form 990, Audit, NICRA, Annual
   report, Strategic plan, Other; preset when opened from an alert).
   - Upload runs three steps with a 3-step progress line: "Uploading…" → "Registering…" → "Queued".
     1. Compute SHA-256 with `crypto.subtle.digest`.
     2. `POST /v1/ingest/artifacts` `{filename, media_type, sha256, size_bytes}`.
     3. `PUT upload_url` (the file body, `Content-Type` = `media_type`).
     4. `POST /v1/agencies/{id}/sources` `{artifact_id, kind}`.
   - `202`/`200` → the modal closes and the new row is at the top.
   - `413 source_too_large` → "This file is larger than 25 MB."
   - `415 unsupported_media_type` → "Hope can read PDF, Word, HTML and XML files."
   - `404 artifact_not_found` → "The upload didn't finish. Try again."
   - A failed `PUT` → "The upload didn't finish. Check your connection and try again."
5. **Watch extraction.** While any row is `queued` or `processing`, poll
   `GET /v1/agencies/{id}/sources` every 5 s, for at most 5 min, then show "Still working —
   refresh later". When a row becomes `proposed`, the status links to
   `/profile/proposals?proposal={proposal_id}`. Expanding a row shows `accepted[]` labels and
   `dropped{}` reasons.
6. **Refresh SAM.gov** (`org_admin`). `GET /v1/agencies/{id}/registration?refresh=true`.
   - The card shows "Checking SAM.gov…".
   - `503 sam_not_configured` → "SAM.gov checks aren't set up yet. An administrator needs to
     add a SAM.gov API key."
   - `502 sam_unavailable` → "SAM.gov didn't respond. Try again in a few minutes."
   - `409 uei_missing` → "Add your UEI in the Legal section to check SAM.gov." with a link
     to `#legal`.
7. **Propose an update from SAM.gov.** `POST /v1/agencies/{id}/registration/sync`.
   - `202` → "Update sent for approval." with "View request".
   - `200 no_change` → "Your profile already matches SAM.gov."
8. **Version history.** "Version history" sets `?history=1`, opens the drawer and calls
   `GET .../profile/history`. Choosing two versions calls
   `GET .../profile/diff?from_version=&to_version=` (defaults: the previous version → current).
   "View profile as of v13" navigates to `/profile?as_of={valid_from of v13}`, which calls
   `GET .../profile?as_of=`.
9. **Leave with unsaved edits.** A `beforeunload` prompt, plus an in-app confirm on nav
   clicks: "You have unsaved changes in Mission. Leave without saving?"
10. **Keyboard.**
    - `Ctrl/⌘+S` saves the focused section.
    - `Esc` closes the drawer or modal.
    - `g h` opens the history drawer.
    - In a tag input, Enter adds a chip and Backspace on an empty input removes the last one.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading | The header title skeleton, 3 health-card skeletons (ring placeholder plus 2 lines) and 4 section skeletons (title plus 3 input bars) |
| Onboarding pending (`404 onboarding_pending`) | "Your agency profile is waiting for approval." with "View the onboarding request", which links to `/profile/proposals?proposal={proposal_id}` |
| No agency (`/v1/me.agency_id` is null) | Redirect to `/onboarding` for `org_admin`. Others see "Your organization hasn't been set up yet. Ask an administrator to finish onboarding." |
| Error (network / 5xx) | `ErrorNotice` "We couldn't load the agency profile." with "Try again" |
| Completeness error | Inside the card: "Completeness couldn't be calculated." with Retry. The rest of the page still works |
| Alerts empty | "✓ Nothing needs attention." |
| SAM not configured | The SAM card: "SAM.gov checks aren't set up yet." Admins also see "Your Hope administrator needs to add a SAM.gov API key to this deployment." (it's the `HOPE_SAM_API_KEY` server setting, not a screen) |
| No UEI | The SAM card: "Add your UEI to check your SAM.gov registration." with "Go to Legal" |
| SAM stale | Amber line: "Showing the last check from {relative time}. SAM.gov didn't respond." |
| Documents empty | "No documents yet. Upload your latest Form 990, audit or indirect rate agreement and Hope will suggest updates for you to approve." |
| As-of view | A banner (`neu-inset`): "Viewing the profile as it was on {date} (version {n}). Changes are turned off." with "Back to current" |
| Version conflict | In the section: "Someone else updated the profile since you opened it." with "Reload and keep my edits" |
| Permission (view-only role) | Every section shows "View only" instead of Save; the Upload and Propose buttons are hidden; one line under the header: "You can view the profile. Ask an administrator or development director to make changes." |
| Offline | A top banner: "You're offline. Changes can't be saved until you reconnect." Save is disabled |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| App shell | `GET /v1/me` | `agency_id`, `roles` | Session |
| Mount, `as_of` change | `GET /v1/agencies/{id}/profile[?as_of=]` | `version`, `valid_from`, `recorded_by`, `profile.*`, `ETag` | Refetch after every successful save or decision; on window focus if older than 5 min |
| Mount, after save | `GET .../profile/completeness` | `score`, `missing[]` | With the profile |
| Mount, after save | `GET .../profile/alerts` | `alerts[]`, `as_of` | With the profile |
| Mount | `GET .../registration` | see content inventory | No auto refetch; manual refresh only |
| Mount, after protected submit | `GET .../profile/proposals?status=pending` | `items[].proposal.changes[].path`, `due_at`, `proposal.proposal_id` | Refetch on focus |
| Mount, polling | `GET /v1/agencies/{id}/sources` | `items[]` | Every 5 s while any row is queued/processing (max 5 min) |
| Save | `PATCH .../profile` | `status`, `version`, `proposal.proposal_id`, `ETag` | Invalidates profile, completeness, alerts, proposals |
| Upload | `POST /v1/ingest/artifacts`, `PUT upload_url`, `POST .../sources` | `artifact_id`, `upload_url`, `source_id` | Invalidates sources |
| SAM refresh / sync | `GET .../registration?refresh=true`, `POST .../registration/sync` | as above | Invalidates registration / proposals |
| History drawer | `GET .../profile/history`, `GET .../profile/diff` | `version`, `valid_from`, `recorded_by`; `path`, `old`, `new`, `protected` | Cached until the version changes |

## 9. Responsive behaviour

- ≥ 1280 px: the health strip has 3 columns and the sections use a 2-column grid. Approval
  hierarchy, Documents and Programs/Grant history span both columns.
- 1024-1279 px: the same, but the SAM card's mismatch list collapses to "1 difference — show".
- 641-1023 px: the health strip has 2 columns (SAM wraps below). The sections use 1 column.
- ≤ 640 px: the mobile layout from section 3, with collapsible sections and sticky Save. The
  upload modal becomes a full-screen sheet.

## 10. Accessibility

- **Headings:** each section is a `<section aria-labelledby>` with an `h2`. Health cards are `h2`s too.
- **Tab order:** header actions → health strip (see-missing link, alert links, SAM actions) →
  pending banner → sections in visual order → documents → programs.
- **Protection:** "Requires approval" uses the lock icon plus text and
  `aria-describedby="hitl0-help"`. The help text reads: "Changes here are reviewed by
  {roles} before they take effect."
- **Completeness ring:** `role="img"`, `aria-label="Profile 63% complete, 6 of 16 items missing"`.
- **Live regions:**
  - Save results and upload progress go to an `aria-live="polite"` region in each section.
  - Polling status changes ("NICRA-2026.pdf: 4 fields found") are announced once.
- **Field errors:** linked with `aria-describedby`. On a 422, focus moves to the first
  invalid input.
- **Dialogs:** the drawer and modals trap focus, close on Esc, and return focus to the button
  that opened them.
- **Status:** alerts and SAM status always use an icon and text, never colour alone. Every
  card and input has a 1 px border with at least 3:1 contrast.
- **Reduced motion:** with `prefers-reduced-motion`, the ring doesn't animate and spinners
  become a static "…" icon.

## 11. Fixture data

`api/profile/fixture.ts` (extends today's `FIXTURE_PROFILE`, version 14, Riverbend) provides:
- **Profile:** the full profile, plus version 13 and version 12 for history and diff (v13→v14
  changes `legal.uei` and `mission.ntee_codes`).
- **Completeness:** 63 with 6 missing; a variant at 100 with 0 missing.
- **Alerts:** `sam_expiring` 30d, `audit_outdated`, `nicra_expired`, and an empty variant.
- **Registration:** active with no mismatch; active with 1 mismatch (expiry); `stale: true`;
  `blocks_federal` with `exclusion_flagged`; plus errors `sam_not_configured`, `uei_missing`
  and `sam_unavailable`.
- **Proposals:** 2 pending (one Financials from a NICRA, `due_at` tomorrow; one Legal from a
  user, overdue).
- **Sources:**
  - one row per status (queued, processing, proposed with 4 accepted and 1 dropped,
    nothing_found, failed `needs_ocr`, failed `active_content`);
  - a queued row that becomes `proposed` on the 2nd poll;
  - an empty list.
- **PATCH results:** committed (v15); pending_approval; no_change; `version_conflict` (when
  the etag is not "14"); `validation_failed` for EIN `07-1234567` ("legal.ein prefix 07 is
  not an IRS-assigned prefix"); `forbidden` for viewer roles.
- **Uploads:** success; `source_too_large` for files > 25 MB; `unsupported_media_type` for `.png`.
- **Pending onboarding:** a "pending onboarding" profile (`404 onboarding_pending`).
- **Session:** a view-only session (roles `["board_chair"]`).

## 12. Analytics and success measures

Events:
- `profile_viewed {completeness, alert_count, pending_count}`
- `profile_section_saved {section, result: committed|pending_approval|no_change|error_code}`
- `profile_missing_field_opened {path}`
- `profile_source_uploaded {kind, media_type, size_bucket}`
- `profile_source_processed {kind, status, accepted_count}`
- `profile_sam_refreshed {result}`
- `profile_sam_sync_proposed {mismatch_count}`
- `profile_history_opened`

Success:
- completeness ≥ 80% within 14 days of onboarding for 80% of agencies;
- median days from a `sam_expiring` 30d alert to a renewed expiry in the profile under 21;
- at least 60% of uploaded documents end in `proposed`.

## 13. Acceptance criteria

- [ ] AC1 The header shows the name, version, effective date and author; the health strip shows completeness (ring + text), alerts in severity order with the exact copy per `reason`, and the SAM card.
- [ ] AC2 Protected sections show the lock badge and "Submit for approval"; a 202 shows the "Sent for approval" message with the link to SC10, resets the inputs and increments the pending banner.
- [ ] AC3 Direct sections save with `If-Match` and a merge-patch body; a 200 updates the version and refetches completeness and alerts.
- [ ] AC4 `version_conflict` offers "Reload and keep my edits", which keeps the section's draft after reloading.
- [ ] AC5 `validation_failed` errors appear under the matching inputs, and focus moves to the first one.
- [ ] AC6 Money is entered in dollars and sent as integer `amount_minor`; rates are entered in percent and sent as integer bps; the budget band is read-only.
- [ ] AC7 The completeness popover lists labelled missing fields, and each link focuses its input.
- [ ] AC8 Upload computes the SHA-256, calls the three endpoints in order, shows progress, and handles `source_too_large`, `unsupported_media_type`, `artifact_not_found` and a failed PUT with the exact copy.
- [ ] AC9 The documents list polls every 5 s while rows are queued or processing, stops after 5 min, and links `proposed` rows to SC10.
- [ ] AC10 The SAM card shows active, stale, blocks-federal and each error state with the exact copy; refresh is only shown to `org_admin`; "Propose update from SAM.gov" only shows with mismatches and calls the sync endpoint.
- [ ] AC11 The history drawer lists versions, shows the diff between two chosen versions with lock icons on protected paths, and "View as of" renders a read-only as-of view.
- [ ] AC12 View-only roles see no Save, Upload or Propose controls and see the view-only line.
- [ ] AC13 The onboarding-pending and no-agency states render the exact copy and links.
- [ ] AC14 `#program-{id}` and `#legal` anchors scroll to and focus the right element.
- [ ] AC15 The mobile layout (≤ 640 px) has stacked health cards, collapsible sections in the order given, and a sticky Save.
- [ ] AC16 axe finds no violations in the default, as-of, history-open and upload-modal states.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `features/profile/HealthStrip.test.tsx::renders completeness alerts and sam card` |
| AC2 | `features/profile/ProfileEditor.test.tsx::marks protected sections and submits them as HITL-0 proposals` (existing, updated) |
| AC3 | `ProfileEditor.test.tsx::saves direct section with if-match and merge patch` |
| AC4 | `ProfileEditor.test.tsx::version conflict keeps draft after reload` |
| AC5 | `ProfileEditor.test.tsx::maps validation errors to fields` (plus the existing `validates EIN format before submitting`) |
| AC6 | `features/profile/sections.test.tsx::money and rate conversion` |
| AC7 | `HealthStrip.test.tsx::missing field links focus inputs` |
| AC8 | `features/profile/SourcesCard.test.tsx::upload flow and errors` |
| AC9 | `SourcesCard.test.tsx::polls until processed` (fake timers) |
| AC10 | `features/profile/RegistrationCard.test.tsx::states roles and sync` |
| AC11 | `features/profile/HistoryDrawer.test.tsx::lists versions diff and as-of` |
| AC12 | `ProfileEditor.test.tsx::view only role` |
| AC13 | `ProfileEditor.test.tsx::onboarding pending and no agency` |
| AC14 | `ProfileEditor.test.tsx::anchors focus targets` |
| AC15 | `ProfileEditor.test.tsx::mobile layout` (matchMedia mock) |
| AC16 | `features/profile/ProfileEditor.a11y.test.tsx` (vitest-axe) |

## 15. Open questions

- **Should Programs and Grant history be editable here?** Recommended default: read-only in
  the MVP. Programs are edited through uploads and a later "Programs" spec. Grant history
  comes from S23 award outcomes and S24 CRM sync. Flag it for C2 if users need it sooner.
- **Display names for `recorded_by` and `proposed_by`.** Recommended default: use S01's
  `GET /v1/users` when the viewer may call it, else show the user id. Agents show "Hope".
  Ask S01 to add `display_name` lookups for non-admin viewers (Catalog change).
- **Unsaved edits across sections.** Recommended default: each section saves on its own;
  there is no global "Save all", because protected and direct sections behave differently.
