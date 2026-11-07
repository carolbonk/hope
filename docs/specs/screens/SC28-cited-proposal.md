# SC28: Cited proposal

| | |
|---|---|
| Route | `/grants/[grantId]/proposal` (query: `section`, `edit`) and the print view `/grants/[grantId]/proposal/print` |
| Feature folder | `apps/web/src/features/proposal/` |
| Built by | H5 |
| Primary users | The nonprofit's grant writer or executive director (one to three sessions per application, 20-60 min each) |
| Can act | Any signed-in user (the hackathon has no roles) |
| Status | Draft |

## 1. Purpose and user goals

This is the last step before applying: Hope's draft answers to the grant's questions, every
claim backed by a citation the user can check in one click. Users arrive:
- from the brief (SC27) via "Draft my answers";
- from the grant overview (SC26) via "Proposal";
- from the "Draft ready" toast after generation.

Within 5 seconds the screen must answer:
1. Is the draft done, and how much of it can I trust? (sections drafted, unverified claims, over-limit sections)
2. What does this answer say, and where did each fact come from? (inline `[c1]` chips plus the Sources pane)
3. What do I need to fix before exporting? (highlighted Unverified sentences with a Fix action)

**Primary action:** review and fix each section, then **Export** (Markdown, DOCX or Copy all)
or **Print the final brief**.
**Secondary actions:** edit a section, regenerate a section, regenerate all.

## 2. Information hierarchy

1. **The status strip.** "5 answers · ⚠ 1 unverified claim · 1 over the word limit" tells
   the user how close they are to done.
2. **The answers themselves**, as a readable document in question order, with citation
   chips inline. Reading flow matters more than controls.
3. **Unverified sentences**, highlighted in the text where they are (amber with an icon and
   the word "Unverified"), because fixing them is the job.
4. **Sources for the focused section** (right pane): the quotes behind this section's chips,
   so checking a claim never means leaving the page.
5. **Export and print** in the header, always reachable.

Hidden behind a click:
- **the full quote and link** for a chip (popover);
- **the regenerate guidance** (modal);
- **edit mode** (per section): reading is the default, editing is deliberate;
- **sources not cited** by the focused section (the collapsed "Other sources in this proposal").

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│ Grants › Community Youth Mentoring Fund › Proposal                                            │
│ Community Youth Mentoring Fund                          [🖨 Print final brief] [Export ▾]      │  <- PageHeader
│ Buckeye Community Foundation · Due Dec 15, 2026 (36 days) · Drafted Nov 9, 2:00 PM            │
├───────────────────────────────────────────────────────────────────────────────────────────────┤
│ ✓ 5 answers  ·  ⚠ 1 unverified claim [Next ↓]  ·  ✕ 1 over word limit      [↻ Regenerate all]  │  <- status strip (glass-panel)
├────────────────────────────────────────────────────────────┬──────────────────────────────────┤
│ ┌ 1. Describe the need your program addresses. ─────[⋯]─┐ │ Sources for answer 1        (3)  │
│ │ 41 / 250 words                          [✎ Edit]       │ │ ┌ [c1] Profile · Mission ──────┐ │
│ │ Riverbend Youth Alliance mentors young people in       │ │ │ "Mentoring and STEM education│ │
│ │ Cleveland. [c1][c2]                                     │ │ │  for under-served youth in   │ │
│ │                                                         │ │ │  Ohio."   Edit in profile →  │ │
│ │ The foundation prioritizes youth in Cuyahoga County.[c4]│ │ └──────────────────────────────┘ │
│ │                                                         │ │ ┌ [c4] buckeyefoundation.org ──┐ │
│ │ ░⚠ Unverified░ Our program has served over 1,000 youth │ │ │ Youth Mentoring Fund | Buck… │ │
│ │ ░since 2012.░                         [Fix ▾]           │ │ │ "Priority is given to progra…"│ │
│ └─────────────────────────────────────────────────────────┘ │ │ Retrieved Nov 9 · Open ↗    │ │
│ ┌ 2. Describe your program. ──────────────────────[⋯]──┐   │ └──────────────────────────────┘ │
│ │ 212 / 300 words                         [✎ Edit]       │ │ ▸ Other sources in this         │
│ │ …                                                       │ │   proposal (6)                  │
│ └─────────────────────────────────────────────────────────┘ │                                  │
│ ┌ 3. Budget narrative ─── ✕ 342 / 300 words ──────[⋯]──┐   │                                  │
│ │ …                                                       │ │                                  │
└────────────────────────────────────────────────────────────┴──────────────────────────────────┘

Edit mode (section 1):
┌ 1. Describe the need your program addresses. ───────────────────────────────┐
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ Riverbend Youth Alliance mentors young people in Cleveland. [c1][c2]     │ │  <- TextArea (glass-inset)
│ │ …                                                                         │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ 44 / 250 words ▇▇░░░░░░   Cite with [c1]-[c9]   [＋ Add source ▾]          │
│                                          [Cancel]  [Save ⌘S]                │
└─────────────────────────────────────────────────────────────────────────────┘

Fix menu on an unverified sentence:
┌───────────────────────────────┐
│ Add a source…                 │  -> list of the proposal's sources; inserts [cN]
│ Edit this sentence            │  -> edit mode, sentence selected
│ Remove this sentence          │  -> confirm, then save
│ Regenerate this answer…       │
└───────────────────────────────┘

Generating (no draft yet, or Regenerate all):
│ Drafting answer 2 of 5: Describe your program…   ▇▇▇▇▇▇░░░░░░░░  about 40 s left              │
  Finished answers render as they arrive; pending ones show a 4-line skeleton titled with the question.
```

Mobile (<= 640 px):
- The Sources pane becomes a bottom sheet. It opens by tapping a chip (scrolled to that
  source) or the "Sources (3)" button pinned to each section.
- The status strip wraps to two lines.
- The header actions collapse into an overflow menu (⋯): Export Markdown, Export DOCX,
  Copy all, Print final brief, Regenerate all.
- Edit mode is full-width, with a sticky bottom bar (`glass-chrome`: word count, Cancel, Save).

Print view (`/grants/[grantId]/proposal/print`), US Letter / A4, black on white:

```text
Community Youth Mentoring Fund: Application brief            Prepared Nov 9, 2026 by Hope
Buckeye Community Foundation · Due December 15, 2026 · https://buckeyefoundation.org/…
1. Summary            overview (2 sentences) · how to apply (portal + link)
2. Deadlines          table: what · date · source [n]
3. Eligibility        ✓ / ✕ / ? requirement — why [n]
4. Checklist          ☐ steps (numbered) · ☐ required documents
5. Answers            ## question · answer text with [n] · (word count / limit)
6. Sources            [n] title or profile field — "quote" — url — retrieved date
7. Check before you submit (only if unverified claims exist)
```

## 4. Content inventory

| Element | Source (`GET /v1/grants/{grantId}/proposal`) | Format and example | Rules |
|---|---|---|---|
| Breadcrumb | `grant.title` | "Grants › Community Youth Mentoring Fund › Proposal" | Links to `/grants` and `/grants/{id}` |
| Title | `grant.title` | "Community Youth Mentoring Fund" | One line, ellipsis at 80 chars, full title in a tooltip |
| Funder and deadline | `grant.funder`, `grant.deadline`, `grant.deadline_text` | "Buckeye Community Foundation · Due Dec 15, 2026 (36 days)" | `deadline` null → show `deadline_text` ("Rolling") as quoted. ≤ 7 days red with "!", ≤ 14 amber. Passed → "Deadline passed Dec 15" in red |
| Drafted time | `draft.generated_at` | "Drafted Nov 9, 2:00 PM" | Relative under 1 h ("Drafted 12 min ago") |
| Answer count | `draft.sections.length` | "✓ 5 answers" | |
| Unverified count | Σ `sections[].unverified_claims.length` | "⚠ 1 unverified claim" / "✓ All claims cited" | "Next ↓" scrolls to the next one in document order and focuses its Fix button |
| Over limit | `sections_meta[].over_limit` (client recount while editing) | "✕ 1 over word limit" | Hidden when 0 |
| Section number and title | the index in `sections`, `sections[].title` | "1. Describe the need your program addresses." | The full question text is in `sections_meta[id].question` (a tooltip if the title is truncated) |
| Standard-section note | `sections_meta[id].kind == "standard"` | "Common question. This grant didn't list its questions." | Shown once, above the first section |
| Word count | `sections_meta[id].word_count`, `word_limit` | "41 / 250 words"; no limit → "212 words" | ≥ 90% amber "Close to the limit"; over → red ✕ "342 / 300 words · 42 over" |
| Edited badge | `sections[].edited_by_user` | `Badge` "Edited by you" | "Regenerate all" keeps these unless the user ticks "Also replace my edits" |
| Answer body | `sections[].body_md` | Markdown, through `MarkdownView` | Each `[cN]` becomes `CitationChip` (`c1`). An unknown id renders as the plain text "[c9?]" in red (shouldn't happen) |
| Unverified highlight | `sections[].unverified_claims[]` (exact sentence text) | Amber background, ⚠ icon and a visually shown "Unverified" label before the sentence | Matched by exact substring in the rendered text; if it isn't found (the user edited it), it is listed under the section as "Unverified: “…”" |
| Citation popover | `draft.citations[id]` | web: title, domain, "quote", "Retrieved Nov 9", "Open source ↗"; profile: "From your profile · Mission statement", "quote", "Edit in profile →" | Provided by H0's `CitationPopover`. The profile path label comes from `features/proposal/labels.ts` (`mission.mission_statement` → "Mission statement") |
| Sources pane | `draft.citations` filtered by the focused section's `citation_ids`, in first-mention order | Cards: the chip id, kind label (domain or "Profile · {field}"), quote (clamped to 4 lines, "Show more"), retrieved date, link | "Other sources in this proposal (n)" lists the rest, collapsed |
| Progress | `job.progress.sections_done`, `sections_total`, `current_step`, `job.status` | "Drafting answer 2 of 5: Describe your program…" + `Progress` | ETA after the first section = the average per section × the remaining count |
| Job outcome | `job.status`, `job.error`, `job.result.partial`, `job.result.reason` | see section 7 | |

## 5. Components

- **Surfaces:**
  - The page sits on `glass-backdrop`. The app's top bar and sidebar are H0's `glass-chrome`.
  - All text on this screen sits on `glass-panel` or stronger, never directly on the
    backdrop. That includes the header: `PageHeader` renders inside a `glass-panel` strip.
- **Page header:** `PageHeader` with a breadcrumb.
  - `Button` secondary "Print final brief" opens `/grants/{id}/proposal/print` in a new tab.
  - `Button` primary "Export ▾" opens a local `Menu` (`role="menu"`) with Markdown, Word
    (.docx) and Copy all.
- **Status strip:** `Card` (`glass-panel`) with `Badge`s (icon + text) and a link button
  "Next ↓". "Regenerate all" is a secondary `Button`. While a job runs, H0's `Progress` is
  shown in the strip.
- **Section card:** `Card` (`glass-panel`); the focused section adds `glass-active` (accent edge).
  - Header: number + title (`h2`), the word-count `Badge`, the "Edited by you" `Badge`, an
    "Edit" `Button`, and a `⋯` `Menu` (Regenerate this answer…, Copy answer).
- **Answer text:** `MarkdownView`, with `CitationChip` injected for markers and a local
  `UnverifiedMark` span for highlights.
- **Popovers:** `CitationPopover` (H0, `glass-overlay`).
- **Edit mode:** `TextArea` (`glass-inset`, auto-grow to 60 vh), the live word meter, and
  "Add source ▾" (a `Menu` of `c` ids with a short label). Save/Cancel use `Button`.
- **Sources pane:**
  - Desktop: H0's `Drawer`, docked as a sticky right column (`variant="panel"`, `glass-panel`).
  - Mobile: a bottom sheet (`glass-overlay` with the dimmed backdrop).
  - Each source card inside is a nested `glass-inset` well.
- **Modals:** `Modal` (`glass-overlay`) for Regenerate (guidance `TextArea`), the stale conflict, Remove
  sentence, and the export warning.
- **Notices:** H0's `Toast` for saves, copies, exports and job results.

## 6. Interactions

1. **Open.** `GET /v1/grants/{grantId}/proposal`. Focus `?section` or else the first section
   with an unverified claim. `?edit={section_id}` opens that section in edit mode.
2. **Generate the first draft.** When `draft` is null and `brief` exists, the empty state
   lists "Hope will answer:" followed by the planned questions: `brief.questions[].text`, or
   the five standard titles.
   - "✨ Draft my answers" → `POST /v1/grants/{id}/proposal` with `{}`.
   - `202` → generating state. Poll the `GET` every 1.5 s while `job.status` is `queued` or
     `running`, at most 4 min. Answers render as they arrive.
   - `409 brief_missing` → "Hope needs the application brief first, to know the grant's
     questions and rules." with "Create the brief" (`/grants/{id}/brief`).
   - `409 drafting_in_progress` → polling starts silently.
3. **Regenerate all.** Confirm: "Write new answers for all {n} questions?" with a
   checkbox, unticked by default: "Also replace the {m} answers I edited". Then
   `POST …/proposal` with `{"replace_edited": <checkbox>}`, and behave as in step 2.
4. **Focus a section.** Clicking a card, or scrolling a card into the central 40% of the
   viewport (IntersectionObserver), focuses it. The Sources pane updates (no animation with
   reduced motion) and `?section` is updated with `replaceState`.
5. **Open a citation.** Click or Enter on a `[c1]` chip opens `CitationPopover`, and
   highlights that source card in the pane. "Open source ↗" opens the URL in a new tab with
   `rel="noopener noreferrer"`. "Edit in profile →" goes to `/profile`.
6. **Fix an unverified claim.** "Fix ▾" next to the highlighted sentence offers four actions:
   - **Add a source…** lists the proposal's citations (label + first 80 chars of the quote).
     Choosing `cN` inserts ` [cN]` after the sentence's final punctuation and saves (step 8).
     - If the claim is cleared → toast "Claim cited."
     - If it is still unverified (the number isn't in that quote) → toast "Still unverified:
       “1,000” isn't in that source. Try another source or edit the sentence."
   - **Edit this sentence** opens edit mode with the sentence selected in the textarea.
   - **Remove this sentence**: confirm "Remove this sentence from answer 1?", then remove it
     from `body_md` and save.
   - **Regenerate this answer…** opens step 9's modal.
7. **Edit a section.** "Edit" (or `e` on the focused section) swaps the rendered text for a
   textarea with the raw `body_md`, markers included.
   - The live word count uses the server rule: whitespace tokens with markers removed.
   - "Add source ▾" inserts `[cN]` at the cursor.
   - Unsaved text is stored in `localStorage` under `hope:proposal:{grantId}:{sectionId}:{content_hash}`
     every second.
   - Cancel asks "Discard your changes to answer 1?" if the text changed.
8. **Save** (Save button or ⌘/Ctrl+S) → `PUT /v1/grants/{id}/proposal/sections/{sectionId}`
   with `{"body_md": "…", "expected_hash": "<draft.content_hash>"}`.
   - Pending UI: a spinner in Save; the textarea stays editable.
   - `200` → leave edit mode and toast "Saved." The new `content_hash`, unverified
     highlights and word count update from the response. Any claims the save made
     unverified are announced: "Saved · 1 claim needs a source."
   - `409 stale_artifact` → modal "This proposal changed since you opened it. Hope may have
     regenerated an answer, or you saved from another tab." with two options:
     - "Reload and keep my text" (primary): refetch, stay in edit mode with the user's
       text, use the new `content_hash`, and show the line "Reloaded. Review, then save
       again."
     - "Discard my edits".
   - `409 drafting_in_progress` → "Hope is writing right now. Save again when it's done."
     The text is kept.
   - `422 unknown_citation` → inline: "[c9] isn't one of this proposal's sources. Use “Add
     source” to pick one."
   - `422 validation_failed` → "An answer can't be empty." / "Answers are limited to 20,000
     characters."
   - Network error → "Couldn't save. Your text is kept on this device." with "Try again".
9. **Regenerate one answer.** `⋯` → "Regenerate this answer…" opens a modal: "Guidance for
   Hope (optional)", up to 500 chars, with the placeholder "e.g. Mention our summer
   program". If the answer was edited, it also warns "This replaces your edits to this
   answer."
   - Call: `POST …/sections/{sectionId}/regenerate` with `{"guidance": "…"}`.
   - `202` → that card shows a skeleton titled "Rewriting…" and polling runs as in step 2.
   - `422` → "Guidance must be 500 characters or fewer."
10. **Export.** If any claim is unverified or any section is over its limit, a modal shows
    first: "{u} claims are still unverified and {o} answers are over the word limit. The
    export lists the claims at the end so you can check them." with "Export anyway" and
    "Review first".
    - Markdown / Word → navigate to `/v1/grants/{id}/proposal/export?format=md|docx` (cookie
      auth; the browser downloads it), then toast "Downloaded {filename}".
    - Export is disabled while `draft.status != "ready"`. A `409 draft_not_ready` (a race) →
      "The draft is still being written. Export when it's ready."
11. **Copy all.** `fetch` the export with `format=md`, write it to the clipboard, then toast
    "Copied 5 answers and 9 sources." If the clipboard is denied: "Your browser blocked
    copying. Use Export → Markdown instead."
12. **Print the final brief.** This opens the print view in a new tab. That page loads the
    same `GET`, renders the print layout from section 3, then calls `window.print()`. A
    screen-only toolbar has "Print" and "Close", hidden by `@media print`.
13. **Keyboard.**
    - `j` / `k` moves to the next / previous section.
    - `u` jumps to the next unverified claim.
    - `e` edits the focused section.
    - `s` toggles the Sources sheet on mobile.
    - ⌘/Ctrl+S saves.
    - Esc closes a popover or modal, or cancels edit (with confirm).
    - These shortcuts are off while typing in the textarea, except ⌘S and Esc.
14. **Leave with unsaved edits.** An in-app confirm "You have unsaved changes in answer 1.
    Leave without saving?" plus `beforeunload`.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading | Header skeleton (title + 1 line), a status-strip skeleton, 3 section skeletons (title bar + 5 lines) and a Sources pane skeleton (2 cards) |
| Grant not found (`404 grant_not_found`) | "We couldn't find this grant. It may have been removed from your list." with "Back to grants" |
| No brief (`brief` null, `draft` null) | "Start with the application brief. Hope reads the grant's pages to find its questions and rules, then drafts answers from them." with "Create the brief" |
| Ready to draft (`brief` set, `draft` null) | "Hope will answer {n} questions from your profile and the grant's own pages. Every claim gets a source you can check." + the question list + "✨ Draft my answers" |
| Generating | Strip: "Drafting answer {done+1} of {total}: {question}…" + progress bar. Pending answers show skeletons; finished ones render normally. Editing is disabled with the tooltip "Available when Hope finishes" |
| Done (job finished within 10 min) | Toast "Your draft is ready: {n} answers, {u} claims to check." (with u = 0: "Your draft is ready: {n} answers, all claims cited.") |
| Partial: `token_budget` | Amber notice: "Hope stopped early to stay within this draft's AI budget. {k} answers still need writing. Regenerate them one at a time." |
| Partial: `time_limit` | Amber notice: "Hope ran out of time on {k} answers. Regenerate them one at a time." |
| Failed | Red notice: "The AI service didn't respond, so nothing changed. Try again in a minute." with "Try again" |
| Interrupted (`job.error` = "Interrupted by restart") | Red notice: "Drafting was interrupted. Start it again." with "Draft my answers" |
| All verified | Strip shows "✓ All claims cited" (green check + text) |
| Stale artifact | The modal in Interactions 8 |
| Error loading | `ErrorNotice` "We couldn't load the proposal." with "Try again" |
| Polling error | Strip: "Lost connection. Retrying…" (backoff 1.5 → 30 s) |
| Offline | Top banner "You're offline. You can keep editing; saving works when you reconnect." Save is disabled |
| Not signed in (401) | H0's `RequireSession` redirects to `/login` |
| Print view, no draft | "There's no draft to print yet." with "Back to the proposal" |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| App shell | `GET /v1/me` | `display_name` | Session (H0) |
| Mount, print view, after any job | `GET /v1/grants/{id}/proposal` | `grant`, `brief`, `draft`, `sections_meta`, `job` | Refetch on window focus if older than 60 s, unless a section is being edited |
| Job running | `GET /v1/grants/{id}/proposal` | `job.*`, `draft.sections` | Every 1.5 s, at most 4 min, backoff on errors |
| Draft / Regenerate all | `POST /v1/grants/{id}/proposal` | `job` | Starts polling |
| Regenerate one | `POST /v1/grants/{id}/proposal/sections/{sid}/regenerate` | `job` | Starts polling |
| Save, fix | `PUT /v1/grants/{id}/proposal/sections/{sid}` | `draft`, `sections_meta` | Replaces local state; no refetch |
| Export, Copy all | `GET /v1/grants/{id}/proposal/export?format=md\|docx` | the file / text | Never cached |

The screen needs no other endpoint: the grant summary and the brief come in the proposal
`GET`, so it works even if H3's and H4's screens change.

## 9. Responsive behaviour

- ≥ 1280 px: two panes, with sections flexible and Sources at 360 px (sticky, scrolls
  independently).
- 1024-1279 px: Sources at 300 px. Quotes clamp to 3 lines.
- 641-1023 px: one column. Sources becomes a right drawer opened from each section's
  "Sources (n)" button or a chip.
- ≤ 640 px: the mobile layout in section 3 (bottom sheet, overflow menu, sticky edit bar).
- Print: one column, 11 pt serif body, chips printed as `[n]`, links printed in full. Glass
  effects are removed (no blur, tint, shadows or backdrop: white page, black text), and page breaks avoided inside answers (`break-inside: avoid` on short ones).

## 10. Accessibility

- **Structure:**
  - The answers are an `<article>` with one `<section aria-labelledby>` per answer (an `h2`
    with the number and question).
  - The Sources pane is `<aside aria-label="Sources for answer {n}">`.
- **Chips:** `CitationChip` is a `button` with
  `aria-label="Source 1: Mission statement, from your profile"` (web:
  `"Source 4: buckeyefoundation.org"`). Its popover is `role="dialog"` with focus
  management and returns focus to the chip.
- **Unverified highlight:** the "Unverified" label is visible text plus an icon, never
  colour alone, and is linked with `aria-describedby` to the Fix button
  (`aria-label="Fix unverified claim: Our program has served over 1,000 youth since 2012"`).
- **Live regions:**
  - Job progress ("Answer 2 of 5 written"), save results and word-limit warnings go to
    `aria-live="polite"` (the word count is throttled to once per 2 s).
  - Errors use `role="alert"`.
- **Tab order:** header actions → status strip → each section (header controls → text and
  chips → Fix buttons) → Sources pane.
- **Edit and dialogs:** the edit textarea is labelled "Answer {n}: {question}". Modals trap
  focus and return it to their trigger.
- **Contrast and motion:** the amber highlight keeps text at ≥ 4.5:1 contrast, and every
  card and input has a 1 px border at ≥ 3:1. Contrast is checked against the worst-case
  `glass-backdrop` colour behind each glass layer. Text never sits directly on the backdrop.
- **Reduced transparency:** with `@media (prefers-reduced-transparency: reduce)`, or in
  browsers without `backdrop-filter`, every `glass-*` surface becomes solid. That covers the
  panels, the Sources pane, popovers, modals, the mobile sheet and the sticky edit bar. The
  layout and borders stay the same, and the amber Unverified highlight stays at ≥ 4.5:1 on
  the solid panel.
- **Reduced motion:** with `prefers-reduced-motion`, the backdrop gradient and the glass
  highlight shimmer stop. There is no smooth scroll and no pulsing on "Next ↓", and spinners
  become static icons.
- **Print view:** real headings, a `<table>` for deadlines, and checkboxes rendered as "☐"
  characters so screen readers and printers both get them.

## 11. Fixture data

`api/proposal/fixture.ts` (grant "Community Youth Mentoring Fund", Buckeye Community
Foundation, due 36 days after `FIXED_NOW`, profile Riverbend Youth Alliance) provides these cases:

1. `ready`: 5 sections from brief questions q1-q5 with word limits 250/300/250/200/300 and
   9 citations (5 profile, 4 web).
   - q1 has one unverified claim ("Our program has served over 1,000 youth since 2012.").
   - q5 is over its limit (342/300).
   - q2 is `edited_by_user`.
2. `standardSections`: a brief with no questions → the 5 standard sections, all `kind: "standard"`.
3. `noBrief`: `brief: null`, `draft: null`.
4. `readyToDraft`: a brief with 4 questions, `draft: null`.
5. `generating`: a job whose `sections_done` grows on each `GET` (0 → 5), with sections
   appearing one by one, ending `done`.
6. Job outcomes: `partialBudget`, `partialTime`, `failed`, `interrupted`.
7. `allVerified`: no unverified claims and no over-limit sections.
8. `PUT` results:
   - success;
   - success that adds an unverified claim (the new sentence has "45%" with no marker);
   - `stale_artifact` when `expected_hash` ≠ the fixture's current hash;
   - `unknown_citation` for `[c42]`;
   - `validation_failed` for an empty body;
   - `drafting_in_progress` during `generating`.
9. Fix "Add a source": choosing `c1` for the q1 claim keeps it unverified ("1,000" isn't in
   the quote); choosing a fixture citation whose quote contains "1,000" clears it.
10. Export: a Markdown string matching the H5 export format; a DOCX blob (a small zip);
    `draft_not_ready` while generating.
11. `grantNotFound` (404) and a passed deadline.

## 12. Analytics and success measures

Events:
- `proposal_viewed {grant_id, sections, unverified, over_limit}`
- `proposal_generate_started {grant_id, scope: all|section, replace_edited, has_guidance}`
- `proposal_generate_finished {status, sections, unverified, duration_s, partial_reason}`
- `proposal_citation_opened {kind: web|profile}`
- `proposal_fix_used {action: add_source|edit|remove|regenerate, cleared: bool}`
- `proposal_section_saved {section_id, words, over_limit, unverified_after}`
- `proposal_exported {format: md|docx|copy, unverified}`
- `proposal_print_opened`

Success:
- at least 90% of exported proposals have 0 unverified claims;
- the median time from "Draft my answers" to the first export is under 30 minutes;
- at least 30% of viewers open at least one citation (a sign of trust-checking).

## 13. Acceptance criteria

- [ ] AC1 The header, status strip (counts with icons and text), and the sections in order with titles, word counts and edited badges render from one `GET`.
- [ ] AC2 `[cN]` markers render as `CitationChip`s; the popover shows the web or profile citation; the Sources pane lists the focused section's citations in first-mention order, plus the collapsed "Other sources".
- [ ] AC3 Focus follows click and scroll, updates the Sources pane, and syncs `?section`; `?edit` opens edit mode.
- [ ] AC4 Unverified sentences are highlighted with the icon and label; "Next ↓" and `u` cycle through them; a claim that can't be matched is listed under its section.
- [ ] AC5 Fix → Add a source inserts the marker and saves; the toast reflects whether the claim cleared. Edit selects the sentence. Remove confirms and saves.
- [ ] AC6 Edit mode shows the raw markdown, a live word count matching the server rule with amber/red thresholds, "Add source", local draft persistence, and a cancel confirm.
- [ ] AC7 Save sends `body_md` + `expected_hash`; success updates the hash and highlights; `stale_artifact` shows the modal, and "Reload and keep my text" keeps the text with the new hash; `drafting_in_progress`, `unknown_citation`, `validation_failed` and network errors show their exact copy.
- [ ] AC8 Draft my answers, Regenerate all (with the replace-edits checkbox) and Regenerate one (with guidance ≤ 500) post the right bodies, poll every 1.5 s, render answers as they arrive, and stop on terminal states.
- [ ] AC9 Every state in section 7 renders with the exact copy, including no brief, ready to draft, partial, failed and interrupted.
- [ ] AC10 Export warns when there are unverified or over-limit sections, then downloads Markdown or DOCX; Copy all copies the Markdown export; `draft_not_ready` and clipboard-denied show their copy.
- [ ] AC11 The print view renders the summary, deadlines, eligibility, checklist, answers, sources and the check-before-you-submit list, hides the toolbar in print media, and calls `window.print()` once loaded.
- [ ] AC12 The keyboard shortcuts work and are suppressed while typing (except ⌘S/Esc); focus returns after popovers and modals.
- [ ] AC13 The mobile layout uses the Sources bottom sheet, the overflow menu and the sticky edit bar.
- [ ] AC14 axe finds no violations in the ready, generating, edit, popover-open, mobile and print states, and with reduced transparency emulated (solid surfaces, same contrast).

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `features/proposal/ProposalScreen.test.tsx::renders header strip and sections` |
| AC2 | `features/proposal/SourcesPane.test.tsx::chips popover and pane order` |
| AC3 | `ProposalScreen.test.tsx::focus follows click scroll and url` (IntersectionObserver mock) |
| AC4 | `features/proposal/Unverified.test.tsx::highlights and next navigation` |
| AC5 | `Unverified.test.tsx::fix add source edit remove` |
| AC6 | `features/proposal/SectionEditor.test.tsx::edit mode word count add source local draft` + `features/proposal/wordCount.test.ts::matches server rule` |
| AC7 | `SectionEditor.test.tsx::save success stale and errors` |
| AC8 | `ProposalScreen.test.tsx::generate regenerate all and one with polling` (fake timers, `generating` fixture) |
| AC9 | `ProposalScreen.test.tsx::state copy` (one case per state) |
| AC10 | `features/proposal/ExportMenu.test.tsx::warn download copy and errors` (clipboard mock) |
| AC11 | `features/proposal/PrintView.test.tsx::renders brief checklist answers and prints` (`window.print` spy) |
| AC12 | `ProposalScreen.test.tsx::keyboard shortcuts` |
| AC13 | `ProposalScreen.test.tsx::mobile layout` (matchMedia mock) |
| AC14 | `features/proposal/ProposalScreen.a11y.test.tsx` (vitest-axe; includes a `prefers-reduced-transparency: reduce` matchMedia case), `PrintView.a11y.test.tsx` |

## 15. Open questions

- **Should the fix menu let users cite a profile field that isn't in the proposal yet?**
  Recommended default: not in the hackathon; only the proposal's existing sources. Later,
  `GET` could return the full evidence list and `PUT` could accept new evidence ids.
- **A "Mark as checked" for unverified claims** the user verified offline. Recommended
  default: no. The fix is to add a source or edit the sentence, so nothing unverified looks
  verified.
- **Autosave to the server.** Recommended default: no. Explicit Save plus a local copy every
  second, because each save changes the draft hash.
- **Version history.** Recommended default: not shown in the hackathon. H0 keeps
  `proposal_section_versions` for later.
- **Server-side PDF.** Recommended default: no. The print view plus the browser's "Save as
  PDF" is reliable and needs no new dependency.
