# SC27: Application brief

| | |
|---|---|
| Route | `/grants/[grantId]/brief` (query: `print=1` opens the print dialog on load) |
| Feature folder | `apps/web/src/features/brief/` |
| Built by | H4 |
| Primary users | Executive director or development lead of a small nonprofit, often a first-time applicant; opens it once to understand the grant, then returns daily to tick off documents |
| Can act | Every signed-in user (no roles in the hackathon): generate/regenerate, tick documents, print, go to the proposal |
| Status | Draft |

## 1. Purpose and user goals

The brief answers "how do I actually apply for this?" in plain English, with proof. Users arrive from the
grant overview (SC26, "Get the application brief"), from the shortlist (SC25), or from the proposal screen
(SC28, "Back to brief").

Within 5 seconds the screen must answer:
1. Can we apply? (eligibility summary: met / not met / unknown)
2. When is it due, and how much time is left? (the nearest key date)
3. Where and how do we apply? (portal and link)

**Primary action:** "Draft proposal" (to SC28), once the brief is ready.
**Secondary actions:** generate / regenerate, tick documents, open a citation, open a source, print.

## 2. Information hierarchy

1. **Header with the at-a-glance strip:** eligibility tally, nearest deadline with urgency, portal link.
   These are the three go/no-go facts.
2. **Overview:** two sentences on what the grant is, so the rest makes sense.
3. **Am I eligible?** Before the how-to, because a "no" makes everything else moot.
4. **How to apply, Steps, Documents, Questions, Key dates**, in the order a user works through them.
5. **Sources panel** on the right: proof and freshness, always visible on desktop but secondary.

Hidden behind a click: each citation's quote (popover), failed or truncated source details, the
"Unverified" explanation (tooltip).

## 3. Wireframe

Desktop (>= 1024 px), brief ready:

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ‹ Youth Mentoring Fund                                                                               │
│ Application brief                                     [↻ Regenerate]  [⎙ Print]  [ Draft proposal ▶ ]│  <- PageHeader
│ Buckeye Community Foundation · Generated 12 min ago from 5 pages · 12 of 14 items verified          │
├──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ✓ 3 of 4 requirements met · ? 1 unknown   │ ⏱ LOI due Jan 15 · 69 days   │ ↗ Apply on apply.buckeyecf.org│  <- glance strip (Card raised, 3 cells)
├────────────────────────────────────────────────────────────────────┬─────────────────────────────────┤
│ On this page: Overview · Eligible? · How to apply · Steps ·        │ SOURCES (5 read, 1 failed)      │
│ Documents · Questions · Key dates                                  │ s1 Youth Mentoring Fund    HTML │
│                                                                    │    buckeyecf.org · 8:41 PM · 3 │
│ Overview                                                           │ s2 How to Apply            HTML │
│  The Youth Mentoring Fund gives one-year grants to Ohio nonprofits │    buckeyecf.org · 8:41 PM · 4 │
│  that run mentoring programs for ages 10-18. [c1] Grants range     │ s4 YMF Guidelines 2027      PDF │
│  from $10,000 to $50,000. [c2]                                     │    first part read · 5         │
│                                                                    │ s6 FAQ                  ✕ failed│
│ Am I eligible?                     3 met · 0 not met · 1 unknown   │    "Page took longer than 15 s" │
│  ✓ Be a 501(c)(3) nonprofit                         [c8] [c9]      │                                 │
│    Your profile lists 501(c)(3) tax status.                         │ Pages are read live and not    │
│  ? Serve youth in Ohio                              [c10]          │ stored. Regenerate to re-read. │
│    Hope couldn't confirm this from your profile. [Update profile →] │                                 │
│                                                                    │                                 │
│ How to apply                                                       │                                 │
│  Apply online through the foundation's grant portal. [c3]          │                                 │
│  [ Open the portal ↗ ]  apply.buckeyecf.org/youth-mentoring         │                                 │
│                                                                    │                                 │
│ Steps                                                              │                                 │
│  1. Create an account in the grant portal. [c3]                    │                                 │
│  2. Submit a letter of inquiry by January 15. [c4]                 │                                 │
│  3. If invited, submit the full application.  ⚠ Unverified         │                                 │
│                                                                    │                                 │
│ Documents you need                              2 of 6 ready ▇▇░░░ │                                 │
│  [✓] IRS determination letter  Showing 501(c)(3) status [c5]       │                                 │
│  [ ] Most recent audited financial statements [c5]                 │                                 │
│                                                                    │                                 │
│ Questions you'll answer                                            │                                 │
│  1. Describe the young people your program serves.  ≤ 500 words [c6]                                 │
│                                                                    │                                 │
│ Key dates                                                          │                                 │
│  ⏱ Jan 15, 2027  Letter of inquiry due          69 days left [c4]  │                                 │
│  ·  "by March 1" Full application due           date as written [c7]                                 │
├────────────────────────────────────────────────────────────────────┴─────────────────────────────────┤
│ Ready to write? Hope drafts answers to these 3 questions from your profile.   [ Draft proposal ▶ ]  │  <- sticky CTA bar
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Desktop, first generation in progress (no brief yet):

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ ‹ Youth Mentoring Fund                                                       │
│ Application brief                                                            │
├──────────────────────────────────────────────────────────────────────────────┤
│  Hope is reading the funder's pages                                          │
│  ▇▇▇▇▇▇▇▇▇▇▇░░░░░░░░░  Reading page 3 of 6: How to Apply                     │  <- Progress
│  ✓ Opened the grant page   ● Reading linked pages   ○ Checking quotes   ○ Save│
│  This takes about a minute. You can leave this page; the brief will be here. │
└──────────────────────────────────────────────────────────────────────────────┘
```

Mobile (<= 640 px): single column. The glance strip stacks into 3 rows. "On this page" becomes a horizontal
scroll of chips. The Sources panel moves into a `Drawer` opened by a "Sources (5)" button in the header. The
CTA bar is sticky at the bottom, full width. Regenerate and Print move into a "⋯" menu.

## 4. Content inventory

| Element | Source (endpoint + JSON field) | Format and example | Rules |
|---|---|---|---|
| Back link + title | `GET …/brief` -> `grant.title` (also on 404 `no_brief`) | "‹ Youth Mentoring Fund" | Links to `/grants/{grantId}` (SC26) |
| Funder | `grant.funder` | "Buckeye Community Foundation" | |
| Generated | `brief.generated_at`, `sources[]` (`status = ok` count), `stats.verified`, `stats.items` | "Generated 12 min ago from 5 pages · 12 of 14 items verified" | Relative time (live); amber "Generated 9 days ago. Funder pages may have changed." when > 7 days |
| Eligibility tally | `brief.eligibility[].meets` | "✓ 3 of 4 requirements met · ? 1 unknown" or "✕ 1 requirement not met" | Any `no` -> red cell with ✕ and "1 requirement not met"; else any `unknown` -> grey ?; else green ✓ "Meets all {n} requirements". No requirements -> "Eligibility not stated" |
| Nearest deadline | `key_dates[]` (smallest future `date`) + matching `brief.deadlines[]` `text` | "⏱ LOI due Jan 15 · 69 days" | Urgency: <= 7 days red "!", <= 21 days amber, otherwise neutral; all past -> "All listed dates have passed" red; none parseable -> "See key dates" |
| Portal | `brief.how_to_apply.detail` | "↗ Apply on apply.buckeyecf.org" | Shows the host only; opens in a new tab (`rel="noopener noreferrer"`) |
| Overview | `brief.overview` | Paragraph with `[cN]` markers rendered as `CitationChip` | Markers parsed by `features/brief/markers.ts` until `MarkdownView` supports them |
| Eligibility row | `eligibility[]`: `requirement`, `meets`, `why`, `citation_ids` | "✓ Be a 501(c)(3) nonprofit" + `why` below | Order: `no`, `unknown`, `yes`. Icons + words: ✓ "Meets", ✕ "Doesn't meet", ? "Unknown". Unknown rows whose `why` mentions the profile show "Update profile →" to `/profile` |
| How to apply | `how_to_apply.text`, `.detail`, `.citation_ids` | Text + "Open the portal ↗" `Button` | Button label "Open the funder's page ↗" when `detail` equals `grant.url` |
| Steps | `steps[]` | Numbered list, `text` then `detail` in secondary text | Order as returned |
| Documents | `required_documents[]` + `checklist[item_id].done` | Checkbox + `text` + `detail` | Progress "2 of 6 ready" with `Progress`; checked items show "✓ by Dana · Nov 7" |
| Questions | `questions[]`: `text`, `word_limit` | Numbered; "≤ 500 words" chip | `word_limit` null and no detail -> no chip |
| Key dates | `deadlines[]` + `key_dates[]` by `item_id` | "Jan 15, 2027 · Letter of inquiry due · 69 days left" | Sorted by date (unparsed last). Unparsed: show the first cited quote in quotation marks + "date as written". Past dates: grey, struck through, "Passed" |
| Citation chips | `citation_ids[]` -> `brief.citations[]` | `[c4]` | `CitationChip`/`CitationPopover` (H0): quote, page title, domain, retrieved time, "Open source"; profile citations show "From your profile: legal.tax_status" + "Open profile" |
| Unverified badge | item with `citation_ids = []` | "⚠ Unverified" | Amber `Badge` with tooltip "Hope couldn't find this on the funder's pages. Check it before relying on it." |
| Sources list | `sources[]` | "s4 YMF Guidelines 2027 · PDF · buckeyecf.org · 8:41 PM · 5 citations" | `status = failed` shows ✕ and `reason`; `truncated` shows "First part read". Title falls back to the URL path. Each opens the URL in a new tab |
| Sources footnote | static | "Pages are read live and not stored. Regenerate to re-read them." | |
| Job progress | `job.progress` (`step`, `pages_done`, `pages_total`, `current`) | `Progress` bar + 4-step list + `current` text | Bar value: fetching 10%, reading 10 + 70 × pages_done/pages_total, checking 85%, saving 95% |
| Failure message | `job.error` | see section 7 | |
| CTA | `brief.questions.length` | "Ready to write? Hope drafts answers to these 3 questions from your profile." | With 0 questions: "Hope drafts a proposal from your profile and these pages." |

## 5. Components

- Header: `PageHeader` with actions: `Button` neutral "Regenerate" (icon ↻), `Button` neutral "Print", `Button` primary "Draft proposal" (as a `Link`).
- Glance strip: `Card` (`glass-panel`) with three cells, each `Badge`-style icon + text.
- Section nav: anchor links in a `Well` (`glass-inset`); on mobile, horizontally scrolling chips.
- Sections: one `Card` per section with an `h2`; lists are `<ol>`/`<ul>`.
- Citations: `CitationChip` + `CitationPopover` (H0).
- Documents: native `<input type="checkbox">` styled `glass-inset` (checked `glass-active`), plus `Progress`.
- Sources: `Card` sticky on desktop (top 1.5 rem); `Drawer` on mobile.
- Generation: `Progress` (H0) inside a `Card`; `Toast` for checklist errors and "Brief updated".
- Regenerate confirmation: `Modal`.
- No new shared primitives.

## 6. Interactions

1. **Load.** `GET /v1/grants/{grantId}/brief`.
   - 200 -> render the brief. If `job.status` is `queued`/`running` (a regenerate), show a slim progress
     banner above the sections and poll.
   - 404 `no_brief` with no job, or with a failed job -> the empty state with "Create brief".
   - 404 `no_brief` with a running job -> the progress card, and poll.
   - 404 `grant_not_found` -> not-found state.
2. **Generate.** "Create brief" -> `POST /v1/grants/{grantId}/brief`. The button shows a spinner and is
   disabled; on 202, show the progress card and start polling. On `409 brief_in_progress`, start polling the
   returned job (no error shown).
3. **Poll.** `GET …/brief` every 2 s while the job is `queued` or `running`; every 5 s when the tab is
   hidden; stop when it is `done` or `failed`. On `done`: render the brief, toast "Brief updated" for a
   regenerate, and move focus to the "Application brief" heading for a first generation.
4. **Regenerate.** Opens a `Modal`: "Re-read the funder's pages and rebuild this brief? Your document
   checkmarks are kept." Confirm -> `POST` as in 2; the current brief stays visible under the progress banner.
5. **Tick a document.** `PUT /v1/grants/{grantId}/brief/checklist/{item_id}` `{"done": true|false}`.
   Optimistic: the box and the "n of m ready" count update immediately. On error, roll back and toast
   "Couldn't save that checkmark. Try again." (`404 item_not_found` -> reload the brief and toast "This
   brief changed. We reloaded it.").
6. **Open a citation.** Click/Enter on `[c4]` opens the popover; "Open source" opens the URL in a new tab.
   Profile citations link to `/profile`.
7. **Sources.** Click a source to open it in a new tab. On mobile, "Sources (5)" opens the drawer.
8. **Draft proposal.** Navigates to `/grants/{grantId}/proposal` (H5). Disabled (with tooltip "Create the
   brief first") when there is no brief.
9. **Print.** "Print" calls `window.print()`. `?print=1` does the same once the brief has loaded. The print
   view (Tailwind `print:` variants): hides nav, buttons, chips' popovers and the sources sticky panel; shows
   the brief in one column; shows checkboxes as ☐/☑; turns each citation chip into a superscript number and
   adds a "Sources" endnote list: `[c4] "Letters of inquiry are due January 15, 2027…" How to Apply,
   buckeyecf.org/…/how-to-apply, retrieved Nov 7, 2026 8:41 PM`.
10. **Deep links.** Section anchors `#eligibility`, `#how-to-apply`, `#steps`, `#documents`, `#questions`,
    `#key-dates`; the "On this page" links update the hash.
11. **Keyboard.** `r` regenerate (opens the modal), `p` print, `d` draft proposal, when focus isn't in an input.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading (first fetch) | Header skeleton, glance strip with 3 grey cells, 4 section skeletons, sources skeleton (4 rows) |
| Empty: no brief yet | Card: "No brief yet. Hope will read {funder}'s pages and explain how to apply, with a source for every point." + primary "Create brief" + secondary "Open the funder's page ↗" |
| Generating (first time) | Progress card (section 3): title "Hope is reading the funder's pages", `current` text, step list, footnote "This takes about a minute. You can leave this page; the brief will be here." |
| Regenerating | Slim banner above the brief: "Updating the brief: {current}" + `Progress`; Regenerate disabled |
| Failed `source_unreachable` | "We couldn't open the funder's page. It may be down or have moved." + "Try again" + "Open the funder's page ↗" |
| Failed `blocked_by_robots` | "This funder's site doesn't allow automated reading, so Hope can't build a brief. Open the page to read it yourself." + "Open the funder's page ↗" |
| Failed `nothing_found` | "Hope read {n} pages but didn't find application instructions. The funder may publish them later." + "Try again" |
| Failed `timeout` / `budget_exceeded` / `model_error` / `interrupted` | "Something went wrong while building the brief." + "Try again" |
| Failed while a previous brief exists | The old brief stays; amber banner "We couldn't update the brief ({short reason}). Showing the version from {time}." + "Try again" |
| Section empty | Eligibility: "The funder's pages don't list eligibility requirements." Steps: "No steps found. Follow the portal's instructions." Documents: "No required documents listed." Questions: "No application questions found." Key dates: "No dates found. Check the funder's page." |
| All items verified | Generated line ends "· every item verified" |
| Grant not found | "We couldn't find this grant. It may have been removed from your list." + "Back to grants" -> `/grants` |
| Error (network / 5xx) | `ErrorNotice` "Could not load the brief" / "Check your connection, then reload." + Reload |
| Not signed in | H0's `RequireSession` redirects to `/login` |
| Offline | Amber banner "You're offline. Checkmarks will fail until you reconnect." |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount, poll | `GET /v1/grants/{grantId}/brief` | `grant`, `brief.*`, `sources`, `checklist`, `key_dates`, `stats`, `job` (also from the 404 body) | Poll 2 s while a job runs (5 s hidden); refetch on focus when the job is running |
| Create / Regenerate | `POST /v1/grants/{grantId}/brief` | `job_id` | Starts polling |
| Tick | `PUT /v1/grants/{grantId}/brief/checklist/{item_id}` `{done}` | `done`, `updated_by`, `updated_at` | Optimistic |

`api/brief/` exports `getBrief(grantId)` (returns `{kind: "ready", …} | {kind: "none", grant, job}`),
`createBrief(grantId)`, `setChecklist(grantId, itemId, done)`, with `types.ts`, `http.ts`, `fixture.ts`.

## 9. Responsive behaviour

- >= 1280 px: content 2/3, sources 1/3 (sticky).
- 1024-1279 px: sources 30% width; glance strip cells wrap to two lines.
- 641-1023 px: single column; sources become a collapsible card after Key dates.
- <= 640 px: as in section 3 (drawer for sources, sticky CTA, "⋯" menu).
- Print: single column, A4/Letter margins, endnotes.

## 10. Accessibility

- One `h1` ("Application brief"), an `h2` per section; "On this page" is a `nav` with `aria-label="Brief sections"`.
- Eligibility, urgency and verification use icon + word, never colour alone.
- Citation chips are buttons with `aria-label="Source c4: How to Apply"`; the popover is a dialog with focus trap and Esc to close, returning focus to the chip.
- Checkboxes have labels from the document text; the "n of m ready" count is in an `aria-live="polite"` region.
- Progress: `role="progressbar"` with `aria-valuenow`, and the `current` text in a polite live region (announced at most every 5 s).
- External links say "(opens in a new tab)" to screen readers.
- `prefers-reduced-motion`: no progress animation; static spinner icons.
- Contrast AA; 1 px borders on cards besides the liquid-glass shadows.

## 11. Fixture data

`api/brief/fixture.ts` provides, by `grantId`:
1. `g-ready`: a full brief (the JSON in H4), 2 of 6 documents checked, one unverified step, one unknown and three met eligibility checks, one parsed and one unparsed date, 5 ok sources + 1 failed + 1 truncated.
2. `g-not-eligible`: one `no` check (red tally) and dates all in the past.
3. `g-none`: 404 `no_brief` with no job; `createBrief` switches it to `g-generating`.
4. `g-generating`: 404 with a running job whose progress advances on each call (fetching -> reading 1..4 of 4 -> checking -> saving -> done, then returns the `g-ready` brief).
5. `g-regenerating`: a brief plus a running job.
6. `g-failed-*`: one per failure code, with and without a previous brief.
7. `g-empty-sections`: a brief with empty eligibility, questions and dates.
8. `g-missing`: 404 `grant_not_found`.
`setChecklist` fails for item `doc-fail` to exercise rollback.

## 12. Analytics and success measures

No analytics pipeline in the hackathon; events named for later: `brief_viewed {grant_id, verified_ratio}`,
`brief_generated {grant_id, pages, seconds, outcome}`, `brief_citation_opened {kind}`,
`brief_document_checked {done}`, `brief_draft_clicked`, `brief_printed`.
Success: in rehearsal, a first-time viewer can say whether they're eligible, the next deadline and where to
apply within 10 seconds, and at least 90% of items are verified on the recorded grants.

## 13. Acceptance criteria

- [ ] AC1 The brief renders the sections in this order: Overview, Am I eligible?, How to apply, Steps, Documents you need, Questions you'll answer, Key dates; with the glance strip and sources panel.
- [ ] AC2 Every item shows its citation chips; items with no citations show the "Unverified" badge and tooltip; the popover shows quote, title, domain, time and "Open source", or the profile field.
- [ ] AC3 The eligibility tally and row order follow the rules (`no` first, then `unknown`, then `yes`), with icon + word per verdict and "Update profile →" on profile-unknown rows.
- [ ] AC4 Key dates sort by date with urgency (<= 7 days red, <= 21 amber, past struck through); unparsed dates show the quote and "date as written"; the glance strip shows the nearest future date.
- [ ] AC5 Document checkboxes persist via PUT, update the count optimistically, and roll back with the toast on error; `item_not_found` reloads.
- [ ] AC6 With no brief, "Create brief" posts, shows the progress card with the step list and `current` text, polls every 2 s, and renders the brief when done (focus moves to the heading).
- [ ] AC7 Regenerate asks for confirmation, keeps the old brief under a progress banner, and toasts "Brief updated"; `409 brief_in_progress` just resumes polling.
- [ ] AC8 Each failure code shows its exact copy; with a previous brief, the amber banner shows instead.
- [ ] AC9 The Sources panel lists every page with status, type, time, citation count, failed reason and "First part read"; on mobile it's in a drawer.
- [ ] AC10 "Draft proposal" links to `/grants/{grantId}/proposal` and is disabled without a brief.
- [ ] AC11 Print view hides controls and shows numbered endnotes with quote, title, URL and time; `?print=1` triggers print after load.
- [ ] AC12 Every state in section 7 renders with the exact copy.
- [ ] AC13 axe finds no violations in the ready, generating, failed and empty states.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `apps/web/src/features/brief/BriefScreen.test.tsx::renders sections in order` |
| AC2 | `BriefScreen.test.tsx::citations and unverified badge` |
| AC3 | `BriefScreen.test.tsx::eligibility tally and order` |
| AC4 | `features/brief/dates.test.ts::urgency and unparsed`, `BriefScreen.test.tsx::glance strip deadline` |
| AC5 | `BriefScreen.test.tsx::checklist optimistic with rollback` |
| AC6 | `BriefScreen.test.tsx::create brief with progress` (fake timers, `g-generating`) |
| AC7 | `BriefScreen.test.tsx::regenerate keeps brief and resumes on 409` |
| AC8 | `BriefScreen.test.tsx::failure copy` (`it.each` over codes) |
| AC9 | `SourcesPanel.test.tsx::lists sources with status`, `::mobile drawer` |
| AC10 | `BriefScreen.test.tsx::draft proposal cta` |
| AC11 | `BriefPrint.test.tsx::print endnotes and auto print` (`window.print` mocked) |
| AC12 | `BriefScreen.test.tsx::state copy` |
| AC13 | `BriefScreen.a11y.test.tsx` (vitest-axe) |

## 15. Open questions

- Should the checklist also cover steps? Recommended: no, documents only (the assignment's scope); steps are a numbered guide.
- Should "Draft proposal" warn when an eligibility check is `no`? Recommended: yes, a confirm modal "This grant lists a requirement you don't meet: {requirement}. Draft anyway?".
- Should a stale brief (> 7 days) regenerate automatically? Recommended: no; show the amber note and let the user choose.
