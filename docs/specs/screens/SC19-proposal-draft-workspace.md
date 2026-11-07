# SC19: Proposal draft workspace

| | |
|---|---|
| Route | `/frameworks/[frameworkId]/draft` (query: `section`, `view=edit\|preview\|full`) |
| Feature folder | `apps/web/src/features/proposal/` |
| Built by | M6 (MVP). S20 later adds HITL-4 review on top |
| Primary users | Development director / program director (the grant writer): several sessions a day while drafting. Executive director: once before the HITL-4 approval |
| Can act | Draft with AI, redraft, edit and save: `development_director`, `program_director`, `admin`. View only: `finance_director`, `executive_director`, `aor` |
| Status | Draft |

## 1. Purpose and user goals

This is where the application's narrative gets written. Users arrive:
- from the workflow timeline (SC08) when the workflow enters `Drafting`;
- from the budget review (SC13) after sign-off ("Continue to the narrative");
- from an approval request (SC06) whose HITL-4 artifact is this draft.

Within 5 seconds the screen must answer:
1. How far along is the draft? (sections drafted, sections needing review, overall `ready`)
2. What does this section need to say? (the RFP's instructions, criteria and word limit, next to the text)
3. Can I trust the numbers? (budget figures are live placeholders; untraced numbers are flagged)

**Primary action:** "Draft with AI" (first visit), then edit and save each section.
**Secondary actions:**
- redraft one section with guidance;
- insert a budget figure;
- preview the full draft;
- jump to the budget.

## 2. Information hierarchy

1. **Draft status bar.** It shows progress ("6 of 6 drafted · 1 needs review"), the workflow
   state and the lock state. Writers need to know whether they are done and whether they may
   still edit.
2. **The current section's text** with its word-limit meter. This is the work itself.
3. **The requirement card**: the RFP instructions and evaluation criteria for this section,
   always visible above the editor, because reviewers score against them.
4. **Findings.** Untraced numbers, literal money and unknown placeholders appear right under
   the editor, because they block `ready`.
5. **Evidence.** The profile and RFP snippets the AI used live in a collapsible side panel:
   useful to check a claim, not needed for every edit.

Hidden behind a click:
- **Token use and cost of the last run:** in a popover on the run status. They matter for
  the hackathon budget, not for writing.
- **The raw markdown of placeholders:** shown in Edit mode only. Preview shows the
  resolved dollar values.

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│ Youth STEM Mentoring Demonstration Grants                       [Preview full draft] [Budget →]│  <- PageHeader
│ Administration for Children and Families · Due Dec 22, 2026 (44 days) · Workflow: Drafting     │
├───────────────────────────────────────────────────────────────────────────────────────────────┤
│ ✓ 6 of 6 sections drafted · ⚠ 1 needs review · Last AI run 2 min ago ⓘ   [✨ Redraft all]       │  <- status bar (Card raised)
├───────────────────────┬───────────────────────────────────────────────────┬───────────────────┤
│ Sections              │ Goals, objectives and outcomes        v1 · AI      │ Evidence (3)  [‹] │
│ ✓ Project summary     │ ┌ What the funder asks for ───────────────────────┐│ RFP: Outcomes     │
│   212/250             │ │ Describe measurable objectives for each goal…   ││ "Describe measur…"│
│ ✓ Statement of need   │ │ Scored on: Clear measurable outcomes (20 pts)   ││ Outcome: Youth    │
│ ✓ Project design      │ │ Limit: 600 words                                ││ served 2025 = 312 │
│ ⚠ Goals & outcomes  ◀ │ └─────────────────────────────────────────────────┘│ Program: After-   │
│   488/600             │ (Edit | Preview)                [＋ Budget figure ▾]│ school STEM Lab   │
│ ✓ Org. capacity       │ ┌─────────────────────────────────────────────────┐│                   │
│ ✓ Budget narrative    │ │ ### Goal 1: Expand mentoring                     ││                   │
│                       │ │ We will serve 450 students across…               ││                   │
│                       │ │ …                                                ││                   │
│                       │ └─────────────────────────────────────────────────┘│                   │
│                       │ 488 / 600 words ▇▇▇▇▇▇▇▇░░                         │                   │
│                       │ ⚠ 1 number can't be traced                         │                   │
│                       │   "450": not in your profile, the RFP or budget [Show]                 │
│                       │ [Redraft this section ▾]      [Discard] [Save ⌘S]  │                   │
└───────────────────────┴───────────────────────────────────────────────────┴───────────────────┘

While a run is in progress, the status bar shows:
│ ◌ Drafting with AI… 3 of 6 sections done · ~25 s left                                         │
and section rows not yet done show a skeleton line and "Waiting…".

Redraft popover:
┌ Redraft "Goals, objectives and outcomes" ─────┐
│ Guidance for Hope (optional, 500 chars)        │
│ [Use only outcome numbers from our profile.  ] │
│ This replaces the current text with a new      │
│ version. Your saved versions are kept.         │
│                         [Cancel] [Redraft ✨]   │
└────────────────────────────────────────────────┘
```

Mobile (<= 640 px):
- The section rail becomes a select at the top ("Section 4 of 6: Goals & outcomes ▾", with
  status icons in its options).
- The requirement card collapses to a single line, "What the funder asks for ▸".
- The Evidence panel moves behind an "Evidence (3)" button that opens a full-screen sheet.
- The Edit/Preview toggle and Save become a sticky bottom bar.
- "Redraft all" moves into an overflow menu (⋯) in the header.

## 4. Content inventory

| Element | Source (`GET /v1/frameworks/{id}/narratives`) | Format and example | Rules |
|---|---|---|---|
| Opportunity title | `opportunity.title` | "Youth STEM Mentoring Demonstration Grants" | One line, ellipsis at 80 chars, full title in a tooltip |
| Funder and due | `opportunity.funder_name`, `opportunity.application_due` | "Administration for Children and Families · Due Dec 22, 2026 (44 days)" | Days in red with "!" if ≤ 7, amber if ≤ 14; "No deadline" if null. Local timezone |
| Workflow state | `workflow.state` | `Badge` "Workflow: Drafting" | Uses `lib/lifecycle.ts` labels. Hidden if `workflow` is null |
| Lock | `locked`, `workflow.state` | Banner "This draft is locked because the application is being packaged." | All inputs read-only when `locked` |
| Progress | `sections[]` (`version ≥ 1`), `status` | "✓ 6 of 6 sections drafted · ⚠ 1 needs review" | `ready: true` → "✓ Ready for executive review". Counts use icon + text |
| Run status | `run.status`, `run.finished_at`, `completed_section_ids`, `section_ids` | "Last AI run 2 min ago"; running: "Drafting with AI… 3 of 6 sections done" | ETA = the average seconds per completed section × the remaining count, shown only after 1 section is done |
| Run cost popover | `run.tokens_used`, `run.cost_usd`, `run.requested_by` | "18,450 tokens · about $0.01 · started by you" | `cost_usd` with 2 decimals, "< $0.01" below 0.005 |
| Run outcome notice | `run.status`, `run.error_code` | see section 7 | Shown once per run until dismissed |
| Section rail item | `sections[].title`, `status`, `word_count`, `requirement.word_limit` | "⚠ Goals & outcomes 488/600" | Icons: drafted/edited ✓, needs_review ⚠, not_started ○, running ◌. Over the word limit → "✕ 652/600" in red |
| Section header | `title`, `version`, `source`, `updated_by`, `updated_at` | "v3 · edited by you · 10:41" / "v1 · AI" / "v1 · Sample" (`seed`) | `updated_by` = "workflow" shows "Hope" |
| Requirement card | `requirement.instructions`, `evaluation_criteria[]`, `word_limit`, `page_limit` | "Scored on: Clear measurable outcomes" | Instructions clamp to 4 lines with "Show more". Hidden when every field is empty |
| Editor text | `body_md` (Edit) / `rendered_md` (Preview) | Markdown | Max 20,000 chars (a counter appears after 18,000) |
| Placeholder chip (Preview) | `placeholders[]` + `rendered_md` | "$185,000" with a dotted underline; tooltip "Budget: total request" | Labels: request_total "Total request", direct_total "Direct costs", indirect_total "Indirect costs", mtdc_base "MTDC base", cost_share_total "Cost share", project_total "Project total", periods "Budget periods", category.X "{Category} costs". `[budget pending]` shown in amber |
| Budget figure menu | the placeholder vocabulary (M6 Behaviour 3), with values from `rendered_md` resolution | "Total request — $185,000" | Inserts `{{budget.request_total}}` at the cursor. Disabled with the tooltip "Finish the budget first" when `budget_ready` is false |
| Word meter | `word_count`, `requirement.word_limit` | "488 / 600 words" plus a bar | ≥ 90% amber "Close to the limit", over red "Over by {n} words". With no limit, only the count. The live count while typing is computed client-side with the same rule (whitespace tokens of the rendered text) |
| Findings | `findings[]` (`code`, `token`, `detail`) | "“450”: not in your profile, the RFP or budget" | Copy by code: `untraced_number` "“{token}” can't be traced to your profile, the RFP or the budget"; `literal_money` "“{token}” is a dollar amount. Use a budget figure instead"; `unknown_placeholder` "“{token}” isn't a budget figure Hope knows"; `over_word_limit` "Over the {limit}-word limit"; `may_exceed_page_limit` "May run over {page_limit} pages". "Show" highlights it |
| Evidence panel | `sections[].evidence_ids` → `evidence[id].label`, `.text` | "Outcome: Youth served 2025 = 312" | Text clamps to 3 lines. RFP items have an "RFP" badge, profile items a "Profile" badge. Profile items link to `/profile#program-{id}` etc. |
| Full preview | all `sections[].rendered_md` in order | One scrolling document with `##` per section title | Read-only. "Copy all" copies the rendered markdown |

## 5. Components

- **Page header:** `PageHeader` with secondary `Button`s ("Preview full draft", "Budget →").
- **Status bar:** `Card` (`glass-panel`) with `Badge`s.
  - "Redraft all" is a primary `Button` with an icon (it reads "Draft with AI" when nothing
    is drafted yet).
  - The run popover is a local `Popover` built from `Card` (`glass-panel`) with focus
    management. A shared `Popover` primitive comes later (see Open questions).
- **Section rail:** a `nav` list of `Button`s (`glass-active` when selected) with `Badge`
  status icons.
- **Requirement card:** `Card` (`glass-inset`).
- **Edit/Preview toggle:** `Segmented`.
- **Editor:** `TextArea` (`glass-inset`, monospace, auto-grows to 70 vh, then scrolls).
- **Preview:** the `MarkdownView` primitive requested from M0, or a local fallback with
  `react-markdown` and `skipHtml`. Placeholder spans and finding `<mark>`s are injected after
  rendering by matching text nodes.
- **Budget figure menu:** a local `Menu` (button + `role="menu"` list).
- **Findings:** a list of `Badge` + text + "Show" link buttons.
- **Redraft:** `Modal` (dialog) with a `TextArea` and buttons.
- **Evidence:** the `Drawer` primitive from M0, as a docked side panel on desktop and a sheet
  on mobile.
- **Notices:** M0's `Toast` for saves and run results; `ErrorNotice` for page errors.

## 6. Interactions

1. **Open the page.** `GET /v1/frameworks/{frameworkId}/narratives`. Select `?section`, or
   else the first `needs_review` section, else the first section. `?view` restores Edit or
   Preview.
2. **Draft with AI / Redraft all** (draft roles, not locked). The button asks for
   confirmation when any section has `source: "human"`: "Redraft all sections? This
   replaces your edited text in {n} sections with new AI drafts. Earlier versions are kept."
   - Call: `POST /v1/frameworks/{id}/narratives/draft` with body `{}`.
   - `202` → the status bar switches to the running state. Poll `GET .../narratives` every
     2 s, at most 10 min. Sections appear in the rail as each one completes. The open
     section's editor becomes read-only, with "Hope is redrafting this section…".
   - `409 draft_in_progress` → "A draft is already running. Showing its progress." Polling
     starts.
   - `409 budget_missing` → "Finish the budget before drafting, so Hope can reference your
     budget figures." with "Go to budget" (`/frameworks/{id}/budget`).
   - `409 draft_locked` → the locked banner.
   - `403 forbidden` → the button is not rendered for view-only roles. If it is still hit:
     "You can view this draft but not change it."
3. **Redraft one section.** Opens the Redraft modal. Call:
   `POST .../narratives/draft` with
   `{"section_ids": ["outcomes"], "guidance": "Use only outcome numbers from our profile."}`.
   It behaves like step 2, except only that section shows the running state.
   - `400 unknown_section` (should not happen) → reload the page data.
   - `422 validation_failed` → "Guidance must be 500 characters or fewer."
4. **Edit and save.**
   - Typing marks the section dirty: a "•" appears in the rail, and Save and Discard enable.
   - Every 1 s the draft is stored in `localStorage` under
     `hope:draft:{frameworkId}:{sectionId}:{content_hash}`.
   - Save (⌘/Ctrl+S) → `PUT .../narratives/{section_id}` with `{"body_md": "…", "base_hash": "<content_hash shown>"}`.
   - Pending UI: Save shows a spinner and the textarea stays editable.
   - `200` → toast "Saved · version {n}". The section, `draft_hash` and findings update, and
     the local copy is cleared. If the save produced findings, they show "⚠ Saved with {n}
     things to review".
   - `409 stale_artifact` → modal "This section changed since you opened it (someone saved
     or Hope redrafted it)." with two options:
     - "Load the latest and keep my text as a copy": reloads, and puts the user's text in a
       read-only "Your unsaved text" panel with "Copy".
     - "Cancel".
   - `409 draft_in_progress` → "Hope is redrafting right now. Save again when it finishes."
     The text stays.
   - `409 draft_locked` → the locked banner. The text stays in local storage.
   - `422 unknown_placeholder` → inline under the editor: "These aren't budget figures Hope
     knows: {keys}. Use “Budget figure” to insert one."
   - `422 validation_failed` → "A section can't be empty." / "Sections are limited to 20,000
     characters."
   - Network error → "Couldn't save. Your text is kept on this device. Try again."
5. **Discard.** Confirm "Discard your unsaved changes to {title}?". Reverts to `body_md` and
   clears the local copy.
6. **Restore unsaved text.** On load, if a local copy exists for the current `content_hash`,
   a banner reads "You have unsaved changes from {time}." with "Restore" and "Discard". A
   copy for an older hash shows "You have unsaved text from an older version." with "Show".
7. **Insert a budget figure.** In Edit mode, open the menu and choose an item. This inserts
   `{{budget.<key>}}` at the cursor and returns focus to the textarea.
8. **Show a finding.** In Preview, this scrolls to and pulses the `<mark>` (no pulse with
   reduced motion). In Edit, it selects the first occurrence of `token` in the textarea.
9. **Preview full draft.** Sets `?view=full`, which shows every section in order, read-only.
   "Copy all" copies the rendered markdown and shows the toast "Copied {n} sections".
10. **Navigate away with unsaved changes.** In-app links ask "You have unsaved changes in
    {title}. Leave without saving?". `beforeunload` covers browser navigation.
11. **Keyboard.**
    - ⌘/Ctrl+S saves.
    - Alt+↑ / Alt+↓ moves to the previous / next section (asking first if there are unsaved
      changes).
    - ⌘/Ctrl+Shift+P toggles Edit/Preview.
    - `e` toggles the Evidence panel when focus is not in the editor.
    - Esc closes menus, modals and the drawer.
12. **Deep links.** `?section={section_id}&view=preview` selects a section and mode. The
    rail and toggle update the URL with `replaceState`.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading | Header skeleton (2 lines), a status-bar skeleton, 6 rail skeleton rows, and an editor skeleton (a requirement card block plus 8 text lines) |
| Not found (`404 not_found`) | "We couldn't find this proposal. It may have been replaced by a newer budget version." with "Go to workflows" (`/workflows`) |
| No budget yet (`budget_ready: false`, nothing drafted) | "Hope drafts the narrative after the budget is ready, so every dollar figure comes from your budget." with "Go to budget". The Draft button is disabled |
| Not started (budget ready, every section `version: 0`) | Empty-state card: "Ready to draft {n} sections for {opportunity title}. Hope writes from your agency profile and the RFP. Dollar amounts come from your budget." with "✨ Draft with AI" (draft roles) or "A program or development director can start the draft." (others) |
| Running | Status bar "Drafting with AI… {done} of {total} sections done". Pending sections: "Waiting…" with a skeleton line. Announced politely once per completed section |
| Succeeded | Toast "Draft ready: {n} sections. {m} need your review." (just "Draft ready: {n} sections." when `m` = 0) |
| Partial | Notice (amber): "Hope drafted {n} sections. {m} have numbers it couldn't trace. Review them before sending this for approval." |
| Budget exceeded | Notice (amber): "Hope stopped after {n} of {total} sections to stay within the AI budget for one draft. Redraft the remaining sections one at a time." Each remaining section shows "Redraft this section" |
| Failed: `provider_error` | Notice (red): "The AI service didn't respond. Your existing text is unchanged. Try again in a minute." with "Try again" |
| Failed: `timeout` | Notice (red): "The draft took too long and was stopped. Try again, or redraft one section at a time." |
| Failed: `internal` | Notice (red): "Something went wrong while drafting. Your existing text is unchanged." |
| Ready | Status bar: "✓ Ready for executive review" (green, check icon). In `AwaitingExecApproval`: "Waiting for executive approval. Editing now will require a new approval." |
| Locked | Banner (`glass-inset`): "This draft is locked because the application is being packaged ({state}). View only." |
| View-only role | Under the header: "You can read this draft. Program and development directors can edit it." No Draft, Redraft, Save or Budget-figure controls |
| Stale artifact | The modal described in Interactions 4 |
| Error loading (network / 5xx) | `ErrorNotice` "We couldn't load the draft." with "Try again". The last loaded data stays visible if there is any |
| Polling error | Status bar: "Lost connection to the draft run. Retrying…" (exponential backoff up to 30 s) |
| Offline | Top banner "You're offline. You can keep writing; Save works when you reconnect." Save is disabled; text is stored locally |
| Section empty after an AI run (should not happen) | "Hope returned no text for this section. Redraft it or write it yourself." |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| App shell | `GET /v1/me` | `roles`, `user_id` | Session |
| Mount, after save or run | `GET /v1/frameworks/{id}/narratives` | everything in section 4 | Refetch on window focus if older than 60 s (skipped when the section is dirty, to avoid clobbering it) |
| Running | `GET /v1/frameworks/{id}/narratives` | `run.*`, `sections[]` | Every 2 s while `run.status == "running"`, at most 10 min, with backoff on errors |
| Draft / redraft | `POST /v1/frameworks/{id}/narratives/draft` | `run` | Starts polling |
| Save | `PUT /v1/frameworks/{id}/narratives/{section_id}` | `section`, `draft_hash` | Updates local state. No full refetch needed |

There is no other endpoint. Opportunity, workflow state and evidence all come in the one
`GET`, so the screen works even before M1's or M4's screens exist.

## 9. Responsive behaviour

- ≥ 1440 px: three columns. The rail is 240 px, the editor flexible, and the Evidence panel 320 px, open by default.
- 1024-1439 px: the rail is 220 px and the editor flexible. The Evidence panel starts closed
  and overlays from the right.
- 641-1023 px: the rail collapses to the section select. The requirement card stays
  expanded. Evidence is a drawer.
- ≤ 640 px: the mobile layout in section 3, with a sticky bottom bar (Edit/Preview, Save) and
  full-screen sheets for Evidence and Redraft.

## 10. Accessibility

- **Landmarks:** the rail is `<nav aria-label="Sections">`; the current item has
  `aria-current="page"`. The editor region is `<section aria-labelledby="section-title">`.
- **Tab order:** header actions → status bar → rail → requirement card → Edit/Preview →
  Budget figure → editor → findings → Redraft/Discard/Save → Evidence.
- **Editor:** a labelled `<textarea>` ("{section title} text").
  - The word meter is `aria-describedby` on the textarea, and its "Over by n words" text is
    in an `aria-live="polite"` region (throttled to once per 2 s while typing).
  - Findings use `role="list"`; each "Show" is a button with
    `aria-label="Show “450” in the text"`.
- **Status:** status icons always come with text (✓ "drafted", ⚠ "needs review",
  ○ "not started"). Run progress is announced through `aria-live="polite"`. Errors use
  `role="alert"`.
- **Dialogs:** the modals and the Evidence drawer trap focus, close on Esc, and return focus
  to the trigger. The Budget figure menu follows the WAI-ARIA menu button pattern.
- **Preview:** placeholder spans have `aria-label="Budget figure: total request, $185,000"`.
  Finding marks have `aria-label="Needs review: 450"`.
- **Contrast and motion:** every card and input has a 1 px border with at least 3:1
  contrast, and text has at least 4.5:1. With `prefers-reduced-motion`, there is no pulse on
  "Show" and spinners become static icons.

## 11. Fixture data

`api/proposal/fixture.ts` (framework `7b0f3c2a-5d1e-4b8a-9c3f-2e6d1a4b5c70`, opportunity
"Youth STEM Mentoring Demonstration Grants", due 44 days after `FIXED_NOW`) provides these cases:

1. `drafted`: six sections. Five are `drafted` with no findings. `outcomes` is `needs_review`
   with an `untraced_number` "450". `budget_narrative` has three placeholders and `rendered_md`
   values. `ready: false`, workflow `Drafting`.
2. `notStarted`: six sections at `version: 0`, `budget_ready: true`.
3. `noBudget`: `budget_ready: false`, nothing drafted, and every placeholder renders
   `[budget pending]`.
4. `running`: a run with `completed_section_ids` growing by one on each `GET` (2 → 6), ending
   `succeeded`.
5. `partial`, `budgetExceeded` (4 of 6), and `failed` with each `error_code`
   (`provider_error`, `timeout`, `internal`).
6. `ready`: all sections clean, `ready: true`, and a variant in workflow state `AwaitingExecApproval`.
7. `locked`: workflow `Packaging`, `locked: true`.
8. `overLimit`: `project_summary` at 268/250 words with `over_word_limit`.
9. Edits:
   - `PUT` success (version + 1, `source: "human"`);
   - `PUT` returning `stale_artifact` when `base_hash` ≠ the fixture's current hash;
   - `unknown_placeholder` for `{{budget.salary}}`;
   - `validation_failed` for an empty body;
   - `draft_in_progress` while case 4 is running.
10. `POST /draft`: `budget_missing` (case 3), `draft_in_progress` (case 4), `draft_locked` (case 7).
11. Sessions: one with roles `["program_director"]` (can edit) and one with
    `["finance_director"]` (view only).

## 12. Analytics and success measures

Events:
- `draft_viewed {framework_id, drafted, needs_review, ready}`
- `draft_run_started {framework_id, scope: all|section, has_guidance}`
- `draft_run_finished {status, sections, tokens_used, cost_usd, duration_s}`
- `draft_section_saved {section_id, source_before, word_count, findings}`
- `draft_finding_shown {code}`
- `draft_budget_figure_inserted {key}`
- `draft_full_preview_opened`

Success:
- the time from "Draft with AI" to `ready: true` has a median under 30 minutes;
- at least 80% of runs end `succeeded`;
- the average cost per full draft stays under $0.10;
- zero `literal_money` findings survive into a saved, approved draft.

## 13. Acceptance criteria

- [ ] AC1 The header, status bar, rail and editor render from one `GET`, with the exact progress copy, workflow badge and due-date urgency.
- [ ] AC2 The first `needs_review` section is selected by default; `?section` and `?view` are restored from the URL and kept in sync.
- [ ] AC3 "Draft with AI" posts `{}`, polls every 2 s, fills sections in as they complete, and stops polling on a terminal status; it asks for confirmation before overwriting human-edited sections.
- [ ] AC4 Redraft one section posts `section_ids` and `guidance`; the 500-character limit is enforced with the exact message.
- [ ] AC5 Each run outcome (`succeeded`, `partial`, `budget_exceeded`, each `failed` `error_code`) shows its exact copy.
- [ ] AC6 Save sends `body_md` and `base_hash`; success shows "Saved · version n" and updates the findings; `stale_artifact` opens the conflict modal and keeps the user's text; `unknown_placeholder`, `validation_failed`, `draft_in_progress` and network errors show their exact copy.
- [ ] AC7 Unsaved text is kept in `localStorage` and offered for restore on reload; leaving with unsaved changes asks for confirmation.
- [ ] AC8 Preview resolves placeholders as labelled chips and marks finding tokens; "Show" scrolls to or selects the token.
- [ ] AC9 The Budget figure menu inserts `{{budget.<key>}}` at the cursor, and is disabled with the tooltip when `budget_ready` is false.
- [ ] AC10 The word meter matches the server's rule, and shows amber at ≥ 90% and red over the limit with "Over by n words".
- [ ] AC11 View-only roles and locked drafts show no editing controls and the exact copy.
- [ ] AC12 The no-budget, not-started, not-found, error, offline and polling-error states render their exact copy.
- [ ] AC13 Full preview shows every section in order, and "Copy all" copies the rendered markdown.
- [ ] AC14 The keyboard shortcuts in Interactions 11 work, and focus returns correctly after modals and the drawer close.
- [ ] AC15 The mobile layout (≤ 640 px) has a section select, a collapsed requirement card, an evidence sheet and a sticky Save bar.
- [ ] AC16 axe finds no violations in the drafted, running, preview, conflict-modal and mobile states.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `features/proposal/DraftWorkspace.test.tsx::renders header status rail and editor` |
| AC2 | `DraftWorkspace.test.tsx::selects first needs review and syncs url` |
| AC3 | `DraftWorkspace.test.tsx::draft all polls and confirms overwrite` (fake timers, `running` fixture) |
| AC4 | `features/proposal/RedraftModal.test.tsx::redraft section with guidance limit` |
| AC5 | `DraftWorkspace.test.tsx::run outcome copy` (one case per status / error_code) |
| AC6 | `features/proposal/SectionEditor.test.tsx::save success and error codes` |
| AC7 | `SectionEditor.test.tsx::local draft restore and leave guard` |
| AC8 | `features/proposal/Preview.test.tsx::placeholder chips and finding marks` |
| AC9 | `SectionEditor.test.tsx::budget figure menu` |
| AC10 | `features/proposal/wordCount.test.ts::matches server rule` + `SectionEditor.test.tsx::word meter thresholds` |
| AC11 | `DraftWorkspace.test.tsx::view only and locked` |
| AC12 | `DraftWorkspace.test.tsx::empty and error states` |
| AC13 | `Preview.test.tsx::full preview and copy all` |
| AC14 | `DraftWorkspace.test.tsx::keyboard shortcuts and focus return` |
| AC15 | `DraftWorkspace.test.tsx::mobile layout` (matchMedia mock) |
| AC16 | `features/proposal/DraftWorkspace.a11y.test.tsx` (vitest-axe) |

## 15. Open questions

- **Version history per section.** Should users be able to view and restore older versions?
  Recommended default: not in the MVP. Versions are stored (append-only), and a later spec
  adds `GET .../narratives/{section_id}/versions`.
- **Autosave to the server.** Recommended default: no. Explicit Save plus a local copy every
  second, because each server save creates a version and changes the HITL-4 hash.
- **Markdown renderer.** Recommended default: `react-markdown` with `skipHtml` in the feature
  folder until M0 provides `MarkdownView`. No raw HTML is ever rendered from model output.
- **A `Popover` primitive** for the run-cost popover. Recommended default: a local
  implementation now, promoted to `components/ui` after the hackathon.
- **Showing cost to users.** Recommended default: show it, in the popover only, during the
  hackathon. Hide it behind `admin` after.
