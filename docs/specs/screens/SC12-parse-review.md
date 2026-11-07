# SC12: Parse review

| | |
|---|---|
| Route | `/parse-review` (query: `status`, `reason`, `source`, `q`, `sort`, `cursor`) and `/parse-review/[reviewId]` |
| Feature folder | `apps/web/src/features/parse-review/` |
| Built by | S10 |
| Primary users | Grant writer / development director (a few times a week, in short sessions when a review is waiting); program director (occasionally) |
| Can act | Resolve and Discard: `grant_writer`, `development_director`, `program_director`, `executive_director` (`PARSE_REVIEW_ROLES` in S10). View: any signed-in user |
| Status | Draft |

## 1. Purpose and user goals

Hope reads every RFP itself, but some documents have conflicting or missing values, or
something suspicious. Those land here. The reviewer's job is to **give Hope the one correct
value for each blocked field**, with the document open next to them, so that the
opportunity can be scored. People arrive from:
- the nav item "Parse review" (with a count badge, see open questions)
- the dashboard
- an SC04 banner ("This opportunity needs a parse review")
- a notification (S12)

Within 5 seconds the queue must answer:
1. How many documents are waiting, and which is most urgent? (the one with the nearest deadline)
2. Why is each one blocked? (conflict, missing deadline, unreadable scan, suspected injection)
3. Is someone already on it? (`resolving` status)

On the detail page the same three questions are: what exactly is blocked, what the
document says about it (evidence), and what to do.

**Primary action:** Resolve (pick or enter a value for every blocked field, then submit).
**Secondary actions:** Discard (not a real RFP, a duplicate, expired, or unreadable), open
the source document, filter and search the queue.

## 2. Information hierarchy

Queue:
1. **Reason badges and the deadline.** The reason says what kind of work this is, and the
   deadline says how urgent it is. The default sort is by deadline, soonest first, with
   undated items on top, because a missing deadline is the most dangerous case.
2. **Title and funder.** Which grant this is.
3. **Source and age.** Grants.gov or an upload, and how long it has waited.

Detail:
1. **The blocked fields.** Each one gets its own card with the decision controls, in a
   fixed order: deadline, then money, then everything else, then acknowledgements. This is
   the work.
2. **Evidence.** The quotes, with page numbers, sit right next to each candidate, so the
   reviewer can decide without opening the PDF most of the time.
3. **Context.** The rest of the extracted opportunity (title, funder, amounts, warnings,
   questions to funder) is collapsed into a side panel. It's useful for a sanity check but
   isn't the task.

Deliberately hidden:
- The raw `GrantOpportunity` JSON, because it isn't useful to a reviewer.
- Resolved and superseded reviews, which sit behind the status tabs.
- Injection signal codes beyond a plain-language list, so the reviewer isn't scared off by
  jargon.

## 3. Wireframe

Queue, desktop (>= 1024 px):

```text
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ Parse review                                                                             │  <- PageHeader
│ Documents Hope couldn't finish reading. Fix the flagged fields so they can be scored.    │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ [ Open 4 ] [ Resolving 0 ] [ Resolved 12 ] [ Discarded 2 ]                               │  <- status tabs (Segmented)
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ [🔍 Search title          ]  Reason: (All ▾)  Source: (All ▾)  Sort: (Deadline ▾) [Clear] │  <- filter bar (Card inset)
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ Why                    │ Opportunity                                   │ Due        │ Waiting │
│ ✕ Missing deadline     │ Riverbend Youth Arts Fund 2027                │ —  No date │ 2 days  │
│                        │ Riverbend Community Foundation · Upload       │            │         │
│ ⇄ Conflict             │ OJJDP FY 2026 Mentoring for Youth Impacted…   │ 31 days    │ 3 h     │
│                        │ OJJDP · Grants.gov · O-OJJDP-2026-172743      │ Dec 8      │         │
│ ⚠ Possible injection   │ Community Wellness Microgrants                │ 12 days    │ 1 day   │
│                        │ Lakeside Health Trust · Upload                │ Nov 19     │         │
│ ▣ Unreadable scan      │ County Seniors Transit Grant                  │ 45 days    │ 5 days  │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ 4 documents                                                       [ Load more ]          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

Detail, desktop:

```text
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ ‹ Parse review                                                                            │
│ OJJDP FY 2026 Mentoring for Youth Impacted by Opioids          ● Open  · waiting 3 h      │  <- PageHeader + status Badge
│ OJJDP · Grants.gov · O-OJJDP-2026-172743 · [Open on Grants.gov ↗]                         │
├──────────────────────────────────────────────────────┬───────────────────────────────────┤
│ 1 of 1 fields to fix                                  │ Documents                         │  <- progress (live region)
│ ┌──────────────────────────────────────────────────┐ │  ▤ O-OJJDP-2026-172743.pdf (24 p) │
│ │ Award ceiling                      ⇄ Conflict    │ │     [Open ↗]                      │
│ │ The document gives two different values. Pick    │ │ What Hope extracted               │
│ │ the one that applies to this application.        │ │  Deadline   Dec 8, 2026 11:59 PM  │
│ │ ( ) $500,000                                     │ │             ET (time assumed)     │
│ │     "Award Ceiling: $500,000"  — p. 3  [Open ↗]  │ │  Internal   Dec 5 (72 h buffer)   │
│ │ ( ) $750,000                                     │ │  Ceiling    — (blocked)           │
│ │     "awards of up to $750,000 each" — p. 9 [↗]   │ │  Indirect   Not allowed (assumed) │
│ │ ( ) Enter a different value                      │ │ Questions to ask the funder       │
│ │     [$ ________ ]  Page [__] Quote [__________]  │ │  • What indirect cost rate…       │
│ └──────────────────────────────────────────────────┘ │ Warnings                          │
│ Comment (optional)                                   │  • Indirect cost policy assumed   │
│ [______________________________________________]     │                                   │
│                                                      │                                   │
│ [ Discard… ]                    [ Resolve and score ▶ ] (disabled until every field set) │  <- sticky action bar
└──────────────────────────────────────────────────────┴───────────────────────────────────┘
```

The other field cards on the detail page:

```text
┌ Application deadline                         ✕ Missing ┐   ┌ Possible prompt injection          ⚠ ┐
│ Hope couldn't find a deadline. Enter it from the       │   │ This document contains text that     │
│ document.                                              │   │ tries to instruct an AI:             │
│ Date [2027-01-15]  Time [17:00]  [☐ No time stated]    │   │  • "Ignore previous instructions"    │
│ Time zone [America/New_York ▾]                         │   │  • Hidden text                       │
│ Page [ 2 ]  Quote [Applications are due January 15…]   │   │ Hope ignored it. Check the document, │
│ With "No time stated", Hope uses 11:59 PM and sets an  │   │ then confirm it's a genuine RFP.     │
│ internal deadline 3 days earlier.                      │   │ [☐ I checked the document; it's a    │
└────────────────────────────────────────────────────────┘   │    genuine RFP]                      │
                                                             └──────────────────────────────────────┘
```

Mobile (<= 640 px):
- Queue rows become cards: reason badge and due on line 1, title on line 2, funder and
  source on line 3.
- Tabs scroll horizontally. Filters move into a "Filters (n)" button that opens a bottom
  sheet.
- On the detail page, the side panel becomes a "Details" accordion under the header,
  collapsed by default. Field cards stack, and the action bar stays sticky at the bottom.

## 4. Content inventory

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Status tab counts | `GET /v1/parse-reviews` -> `counts` | "Open 4" | Always shown, including 0. The `resolving` tab is hidden when its count is 0 and it isn't selected |
| Reason badge | `items[].reasons[]` | ✕ "Missing deadline" / "Missing value", ⇄ "Conflict", ▣ "Unreadable", ⛔ "Corrupt file", ⚠ "Possible injection", ⏱ "Too long to read" (`budget_exceeded`) | Icon + text. `missing` reads "Missing deadline" when `blocking_fields` includes `deadlines.application_due`, otherwise "Missing value". If there is more than one reason, show the first by priority (injection > missing > conflict > corrupt > unreadable > budget) plus "+n" |
| Title | `items[].title` | One line, ellipsis at 70 characters, full title in a tooltip | "Untitled opportunity …" titles (from the pipeline) show in italics |
| Funder line | `items[].funder_name`, `source_system`, `source_id` | "OJJDP · Grants.gov · O-OJJDP-2026-172743" | Source labels: `grants_gov` -> "Grants.gov", `upload` -> "Upload", `funder_site` -> "Funder site", `state_portal` -> "State portal", `candid` -> "Candid", `email` -> "Email". `source_id` is hidden for uploads |
| Due | `items[].application_due` | "31 days" with "Dec 8" below; "— No date" | `countdown()` from `lib/time.ts`: red with "!" at <= 7 days, amber at <= 14. "No date" in red text with the ✕ icon. Past dates show "Passed" |
| Waiting | `items[].created_at` | "3 h", "2 days" | Amber after 2 days, red after 5 days (with an icon) |
| Status badge (detail) | `status` | ● "Open", ◌ "Resolving…", ✓ "Resolved", ⊘ "Discarded", ↻ "Superseded" | Icon + text |
| Field card title | `blocking[].field` | Label map: `deadlines.application_due` "Application deadline", `deadlines.loi_due` "Letter of intent deadline", `deadlines.questions_due` "Questions deadline", `funding.award_ceiling` "Award ceiling", `funding.award_floor` "Award floor", `funding.total_program_funding` "Total program funding", `funding.indirect_cost_policy` "Indirect cost policy", `funding.cost_share` "Cost share", `title` "Title", `funder.name` "Funder", `source.artifacts` "Document couldn't be read", `parse_quality.injection_suspected` "Possible prompt injection", `parse_quality.model_budget_exceeded` "Document too long for automatic reading" | An unknown field shows the raw path and "This field can't be fixed here", and Resolve is disabled |
| Field explanation | `blocking[].reason` + `kind` | conflict: "The document gives different values. Pick the one that applies to this application." missing: "Hope couldn't find this. Enter it from the document." corrupt: "This file is damaged or password-protected, so Hope couldn't open it." unreadable: "This looks like a scan Hope couldn't read." | Exact copy |
| Candidates | `blocking[].candidates[].value` | "$500,000", "December 8, 2026 5:00 PM ET" | Radio label = `value` exactly as the document states it (code parsed it; the LLM did not write it) |
| Evidence quote | `candidates[].evidence[].quote`, `page`, `artifact_id` | "Award Ceiling: $500,000" — p. 3 | Quote in quotation marks, max 200 characters, then "…". Up to 2 per candidate, "+n more" expands. "Open ↗" -> `GET /v1/artifacts/{sha256}/download` (sha from `artifacts[]` matching `artifact_id`), opened in a new tab at `#page=3` |
| Enter value: deadline | form -> `ResolvedField.deadline` | Date (`input type=date`), Time (`type=time`, default empty), "No time stated" checkbox (disables Time), Time zone `SelectField` | Time zone defaults to `opportunity.deadlines.application_due.timezone`, then "America/New_York". The list shows US zones first (ET, CT, MT, MST/Phoenix, PT, AKT, HST), then "Other…" for any IANA name |
| Enter value: money | form -> `ResolvedField.money` | `$ [ 250,000 ]` | `parseMajorToMinor()` from `lib/money.ts`. Must be > 0. Shown back as `formatMoney` |
| Enter value: indirect | form -> `indirect_cost_policy` | "Allowed?" Segmented (Yes / No), "Cap %" number (0-100, step 0.01 -> bps), Base select (MTDC / TDC / Salaries and wages / Not stated) | Cap and Base are hidden when "No" |
| Enter value: cost share | form -> `cost_share` | "Required?" Yes / No, "Match %" (-> `ratio_bps`), "In-kind allowed?" Yes / No / Not stated | |
| Enter value: text | form -> `text` | `TextField`, max 500 | Required, trimmed |
| Evidence for entered values | form -> `ResolvedField.evidence` | Document select (if more than one artifact), Page (1..`artifacts[].pages`), Quote (optional, max 500) | Page is required: every value Hope stores must point at its source |
| Injection signals | `injection_signals[]` | Plain-language list: `pattern:ignore_instructions` "Text telling an AI to ignore its instructions", `pattern:role_override` "Text trying to change an AI's role", `pattern:prompt_exfiltration` "Text asking an AI to reveal its instructions", `pattern:role_tags` "Hidden chat-format tags", `pattern:verdict_steering` "Text telling an AI to approve or rank this application", `zero_width_chars` "Invisible characters", `bidi_override` "Text-direction tricks", `hidden_text` "Hidden text (for example, white on white)" | Unknown codes show as-is |
| Acknowledge checkbox | -> `action: "acknowledge"` | injection: "I checked the document; it's a genuine RFP." artifacts: "I'll enter the details by hand from the source." budget: "I'll enter the details by hand." | Required to resolve |
| Progress | derived | "1 of 3 fields to fix" -> "All fields ready" | `aria-live="polite"` |
| Side panel: extracted | `opportunity.deadlines.application_due` (+ `time_assumed`, `internal_due`), `funding.award_ceiling`, `funding.indirect_cost_policy`, `funder.name` | "Dec 8, 2026 11:59 PM ET (time assumed)" / "Internal Dec 5 (72 h buffer)" | A blocked field shows "— (needs your input)" |
| Questions to funder | `questions_to_funder[]` | Bullets | Read-only. Copy button "Copy questions" |
| Warnings | `warnings[]` | Plain-language map: `funding.indirect_cost_policy_assumed` "Indirect cost policy assumed (not allowed)", `deadline.time_assumed` "Deadline time assumed (11:59 PM)", `deadline.timezone_assumed` "Time zone assumed", `funding.award_ceiling_missing:blocks_budgeting` "Award ceiling missing; budgeting is blocked", `near_duplicate_of:{id}:{score}` "Looks like a copy of another opportunity" (links to SC04) | Unknown warnings are hidden; their count shows as "+n technical notes" |
| Resolved summary (read-only) | `resolution`, `resolved_by`, `resolved_at`, `resolved_version` | "Resolved by j.alvarez on Nov 7, 2:10 PM · Award ceiling: $500,000 (picked, p. 3)" | Shown instead of the form when status is `resolved` or `discarded` |
| Error note | `error` | "Hope couldn't apply this resolution: {error}. Please review again." | Shown when status is back to `open` with `error` set |

## 5. Components

- Page header: `PageHeader`. The status uses `Badge` (tone by status: open = warn, resolving = info, resolved = good, discarded or superseded = neutral).
- Status tabs: `Segmented` (active = `glass-active`).
- Filter bar: `Card` (`glass-inset`) with `TextField` (search, debounced 300 ms) and `SelectField` × 3.
- Queue table: `Table` / `Th` / `Tr` / `Td`, with the caption "Documents needing a parse review". The whole row is a link (`<a>` in the title cell, and the row is clickable).
- Field cards: `Card` (`glass-panel`), one per blocking issue, as a `<fieldset>` with a `<legend>`. Candidates are radio inputs styled as `Well` options (`glass-inset`, `glass-active` when checked).
- Inputs: `TextField`, `SelectField`, `Segmented`. Errors use each field's `error` prop.
- Side panel: `Card` (`glass-inset`). On mobile it's an accordion (`<details>`).
- Action bar: sticky `Card` with `Button` (primary "Resolve and score", neutral "Discard…").
- Discard confirmation: `Modal` (dialog) containing `SelectField` (reason) and `TextArea` (note).
- Notices: `SuccessNotice`, `ErrorNotice`, `EmptyState` and `Loading` from `components/ui/States.tsx`.
- New shared primitives, requested under Shared contract additions in S10 / C2:
  - `RadioCard` (a radio rendered as a liquid-glass option card)
  - `Toast` (also needed by SC03)

  Until they exist, use a styled `<label>` + `<input type=radio>` inside the feature, and `SuccessNotice`.

## 6. Interactions

1. **Filter, search, sort, tabs.** Each one updates the URL
   (`/parse-review?status=open&reason=conflict&source=grants_gov&q=youth&sort=due`) and
   calls `GET /v1/parse-reviews?status=&reason=&source_system=&q=&sort=&limit=25`. Previous
   rows stay visible, dimmed (`aria-busy="true"`), while loading. Changing a filter clears
   `cursor`.
2. **Load more.** `GET /v1/parse-reviews?...&cursor={next_cursor}` appends rows. The button
   is hidden when `next_cursor` is null.
3. **Open a review.** Clicking a row, or pressing Enter on it, navigates to
   `/parse-review/{review_id}`. The detail page calls `GET /v1/parse-reviews/{review_id}`.
   The queue's scroll position and filters are restored on Back (they're in the URL).
4. **Pick a candidate.** Local state only. Picking "Enter a different value" reveals the
   input group and focuses its first input.
5. **Enter a value.** Validation runs on blur and on submit:
   - empty date: "Enter the date."
   - bad time: "Enter a time like 5:00 PM, or tick No time stated."
   - empty page: "Enter the page where this appears."
   - page out of range: "This document has {pages} pages."
   - money <= 0 or unparseable: "Enter an amount in dollars, like 250,000."
   - percentage outside 0-100: "Enter a percentage between 0 and 100."
6. **Resolve.** The button is enabled only when every card is complete. Clicking it sends
   `POST /v1/parse-reviews/{review_id}/resolve` with:
   - `version_hash` from the detail response
   - `fields[]`, one per card:
     - `pick`: `{field, action:"pick", candidate_index}`
     - `enter`: `{field, action:"enter", <kind value>, evidence:{artifact_id, page, quote?}}`
     - `acknowledge`: `{field, action:"acknowledge"}`
   - `comment`

   Pending: the button shows "Resolving…" and is disabled, and the form is read-only.
   - **202:** status badge "Resolving…", plus the notice "Thanks. Hope is applying your
     fixes and will re-score this opportunity." The page polls
     `GET /v1/parse-reviews/{id}` every 3 s (stops after 30 s or when the status changes).
     - `resolved`: the notice becomes "Resolved. The opportunity is back in scoring."
       with links "Back to queue" and "Open opportunity" (`/opportunities/{opportunity_id}`).
     - Back to `open` with `error`: show the error note and re-enable the form.
     - Still `resolving` after 30 s: "Still applying… You can leave this page; it will
       finish in the background."
   - **409 `stale_artifact`:** `ErrorNotice` "This document changed since you opened it (a
     newer version arrived). Reload to review the latest version." plus Reload. Reload
     refetches; if the review is now `superseded`, the page shows that state.
   - **409 `review_closed`:** "Someone else already {resolved | discarded} this review." plus
     "Back to queue". The form is replaced by the read-only summary after a refetch.
   - **422 `unresolved_fields`:** each listed card gets the error "This field still needs a
     value." Focus moves to the first one.
   - **422 `invalid_value` / `invalid_candidate`:** the card for `field` shows `detail` (or
     "This value isn't valid. Check it and try again."), and focus moves there.
   - **403 `forbidden`:** "You don't have permission to resolve parse reviews. Ask a grant
     writer or development director." The form becomes read-only.
   - **Network or 5xx:** "We couldn't send your fixes. Your answers are still here. Try
     again." plus Retry. The form stays filled.
7. **Discard.** "Discard…" opens a modal titled "Discard this document?" with the body
   "It won't be scored or shown in search. You can't undo this." A Reason select is
   required: "Not an RFP", "Duplicate of another opportunity", "Deadline has passed",
   "Can't be read", "Other". The Note field is required for "Other". Confirm sends
   `POST /v1/parse-reviews/{id}/discard {version_hash, reason, note}`.
   - 200: back to the queue with the notice "Discarded “{title}”."
   - 409 and 403: handled as in step 6.
8. **Open document.** "Open ↗" requests `GET /v1/artifacts/{sha256}/download` (S03),
   then opens the returned URL plus `#page={page}` in a new tab. If that call fails:
   "The document link expired or couldn't be created. Try again."
9. **Copy questions.** Copies `questions_to_funder` as a bulleted list and announces
   "Copied" in the live region.
10. **Keyboard.**
    - Queue: `/` focuses search, ↑/↓ moves between rows, Enter opens a row.
    - Detail: radio groups use arrow keys. `Ctrl+Enter` submits Resolve when it's enabled,
      and Esc closes the discard modal.
11. **Deep links.** `/parse-review/{review_id}` works directly (from notifications and
    SC04). `?field=funding.award_ceiling` scrolls to and focuses that card.

## 7. States and exact copy

| State | What shows |
|---|---|
| Queue loading (first load) | Tabs skeleton + 6 skeleton rows (two grey lines each), `role="status"` "Loading reviews…" |
| Empty: nothing open (and discovery has run) | "Nothing to review. Hope finished reading every document it found." + a secondary link "See resolved reviews" (`?status=resolved`) |
| Empty: discovery never ran (`counts` all 0) | "No documents yet. When Hope starts checking sources, anything it can't finish reading will show up here." + link "Set up sources" (to `/settings/team`, shown only to `SOURCE_ADMIN_ROLES`) |
| Filtered to empty | "No reviews match these filters." + "Clear filters" |
| Queue error | `ErrorNotice` "We couldn't load the review queue." + Reload. Rows from the last load stay visible if there are any |
| Detail loading | Header skeleton + 2 card skeletons + side panel skeleton, "Loading review…" |
| Detail not found (404) | "This review doesn't exist or was removed." + "Back to queue" |
| Detail error | "We couldn't load this review." + Reload |
| Resolving | Status "Resolving…" + "Thanks. Hope is applying your fixes and will re-score this opportunity." |
| Resolved | Read-only summary + "Resolved. The opportunity is back in scoring." + "Open opportunity" |
| Discarded | Read-only summary "Discarded by {user} on {date}: {reason label}. {note}" |
| Superseded | "A newer version of this document arrived, so this review was closed." + "Open current review" (if `opportunity_parse_status` shows an open one, via the queue filtered by title) or "Open opportunity" |
| Error after resolving (`status=open`, `error` set) | `ErrorNotice` "Hope couldn't apply this resolution: {error}. Please review again." |
| Permission (no resolve role) | The form is read-only. Info notice: "You can view this review. Resolving needs the grant writer, development director, program director or executive director role." Buttons hidden |
| Stale artifact | See interaction 6 (409 `stale_artifact`) |
| Offline (`navigator.onLine === false`) | Banner "You're offline. Changes will be sent when you reconnect." Resolve is disabled with the tooltip "You're offline" |
| Unknown field in `blocking` | The card "{field}: This field can't be fixed here. Discard, or ask an admin." Resolve stays disabled |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Queue mount / filter / tab / sort | `GET /v1/parse-reviews?status=&reason=&source_system=&q=&sort=&limit=25` | `items[]` (all summary fields), `next_cursor`, `total`, `counts` | Keep the previous page while loading; refetch on window focus if older than 2 min |
| Load more | `GET /v1/parse-reviews?…&cursor=` | same | Appends |
| Detail mount | `GET /v1/parse-reviews/{review_id}` | `status`, `version_hash`, `opportunity` (title, funder, deadlines, funding), `blocking[]` (`field`, `reason`, `kind`, `allowed_actions`, `candidates[]`), `injection_signals`, `questions_to_funder`, `warnings`, `artifacts[]` (`artifact_id`, `sha256`, `filename`, `pages`), `resolution`, `resolved_*`, `error`, `source_url` | No cache; refetch after any 409 |
| Poll after 202 | `GET /v1/parse-reviews/{review_id}` | `status`, `error`, `resolved_version` | Every 3 s, max 10 times |
| Resolve | `POST /v1/parse-reviews/{review_id}/resolve` | summary | Invalidates the queue |
| Discard | `POST /v1/parse-reviews/{review_id}/discard` | summary | Invalidates the queue |
| Open document | `GET /v1/artifacts/{sha256}/download` (S03) | `url`, `expires_at` | Never cached (the URL is short-lived) |
| App shell | `GET /v1/me` | `roles` (decides whether the form is editable), `user_id` | Session |

Every field above is returned by S10's endpoints, except `GET /v1/artifacts/{sha256}/download`,
which S03 owns. Its expected response is `{url, expires_at}`; see the catalog changes in the report.

## 9. Responsive behaviour

- >= 1280 px: queue columns Why / Opportunity / Due / Waiting. Detail is two columns
  (fields 2/3, side panel 1/3 and sticky).
- 1024-1279 px: same, with the side panel narrower (320 px).
- 641-1023 px: the queue drops the Waiting column (it moves under the title). The detail
  side panel moves above the field cards as a collapsed accordion.
- <= 640 px: queue cards, bottom-sheet filters, horizontal tabs. Detail fields stack, and
  the inline evidence group in the money/deadline form becomes a vertical stack. The action
  bar is sticky with full-width buttons (Resolve on top).

## 10. Accessibility

- Tab order on the detail page:
  1. Back link
  2. "Open on Grants.gov"
  3. each field card (radios, then the inputs for "Enter a different value")
  4. comment
  5. Discard
  6. Resolve
  7. side panel
- The queue is a real `<table>` with `<th scope="col">` and a caption. Each title is a
  link, so the queue works with a screen reader's link list.
- Each field card is a `<fieldset>` whose `<legend>` holds the field label and reason text.
  Each candidate's `aria-describedby` points at its evidence quote.
- Reason, status, due urgency and waiting age always use an icon and text, never colour alone.
- Validation errors use `aria-invalid` and `aria-describedby` on the input. A failed submit
  moves focus to the first error and announces "{n} fields need attention" in an
  `aria-live="assertive"` region.
- Progress ("1 of 3 fields to fix"), "Copied" and the polling status changes are
  announced politely.
- The discard modal traps focus, starts on the Reason select, and returns focus to
  "Discard…" on close.
- Every card and input has a 1 px border with at least 3:1 contrast in addition to the
  liquid-glass shadow.
- With `prefers-reduced-motion`: no skeleton shimmer, no smooth scroll to `?field=`, and
  the spinner becomes a static icon.

## 11. Fixture data

`apps/web/src/api/parse-review/fixture.ts` exports `FixtureParseReviewApi` with these
reviews (dates relative to `FIXED_NOW`):

1. `rv-conflict` (open): OJJDP mentoring, Grants.gov.
   - `funding.award_ceiling` conflict with two candidates ($500,000, p. 3; $750,000, p. 9)
   - due in 31 days, `time_assumed=true`
   - questions: indirect
   - warnings: `funding.indirect_cost_policy_assumed`
2. `rv-missing-deadline` (open): Riverbend Youth Arts Fund, upload.
   - `deadlines.application_due` missing
   - one DOCX artifact (6 pages)
   - no due date
3. `rv-injection` (open): Community Wellness Microgrants, upload.
   - `parse_quality.injection_suspected` with signals `pattern:ignore_instructions` and `hidden_text`
   - application due present (12 days)
4. `rv-scan` (open): County Seniors Transit, state portal.
   - `source.artifacts` unreadable plus `deadlines.application_due` missing
   - waiting 5 days (red)
5. `rv-resolving` (resolving): flips to `resolved` on the second poll.
6. `rv-resolved` (resolved), with a `resolution` picking candidate 0.
7. `rv-discarded` (discarded): reason `not_an_rfp`, with a note.
8. `rv-superseded` (superseded).
9. `rv-error` (open, `error: "candidate_unparseable"`).
10. `rv-unknown-field` (open), with a blocking field `requirements.page_limit`, which isn't in `RESOLVABLE_FIELDS`.

Behaviour switches, set by the review id used in a test:
- Resolve on `rv-conflict` returns 202 and the review goes to `resolving`, then `resolved`.
- Resolve with `version_hash: "sha256:stale"` returns 409 `stale_artifact`.
- Resolve on `rv-resolved` returns 409 `review_closed`.
- Resolve on `rv-missing-deadline` with no deadline returns 422 `unresolved_fields`.
- Resolve with a bad timezone returns 422 `invalid_value`.
- A session without a `PARSE_REVIEW_ROLES` role gets 403.
- `listReviews({status:"open", reason:["corrupt"]})` returns empty (the filtered-empty state).
- `new FixtureParseReviewApi({ empty: true })` returns all counts 0.

## 12. Analytics and success measures

Events:
- `parse_review_queue_viewed {status, reason[], count}`
- `parse_review_opened {review_id, reasons[], age_hours}`
- `parse_review_document_opened {review_id, field, page}`
- `parse_review_resolved {review_id, fields:[{field, action}], seconds_on_page}`
- `parse_review_discarded {review_id, reason}`
- `parse_review_error {review_id, code}`

Success:
- the median open-review age is under 24 h
- 95% of reviews with a deadline in 14 days or less are resolved within 4 h of opening
- under 5% of resolves end in `stale_artifact` or an error state
- the share of `pick` among conflict resolutions (high means the evidence is good enough)

## 13. Acceptance criteria

- [ ] AC1 The queue shows open reviews sorted by deadline (undated first), each with reason (icon + text), title, funder line, due countdown and waiting age, plus status tabs with counts.
- [ ] AC2 Tabs, reason, source, search and sort are reflected in the URL and restored on reload. "Load more" appends the next page and disappears when `next_cursor` is null.
- [ ] AC3 The detail page renders one card per blocking issue with the right label, explanation and controls for its `kind` (deadline, money, indirect, cost share, text, acknowledge), including candidate evidence with page links.
- [ ] AC4 Resolve is disabled until every card is complete. Entered values require a page. "No time stated" disables Time and shows the 11:59 PM / 3-days-earlier hint.
- [ ] AC5 Resolve sends exactly the documented body (`version_hash`, one `ResolvedField` per card, `comment`), then shows Resolving, polls, and shows Resolved with the "Open opportunity" link.
- [ ] AC6 409 `stale_artifact`, 409 `review_closed`, 422 `unresolved_fields`, 422 `invalid_value` and 403 each show their exact copy and focus behaviour.
- [ ] AC7 Discard requires a reason (and a note for "Other"), sends the documented body and returns to the queue with the notice.
- [ ] AC8 Users without a resolve role see a read-only form with the permission notice and no Resolve or Discard buttons.
- [ ] AC9 The injection card lists the signals in plain language, and Resolve needs the acknowledgement checkbox.
- [ ] AC10 Every state in section 7 renders with the exact copy.
- [ ] AC11 Keyboard: `/`, ↑/↓ and Enter work in the queue. `Ctrl+Enter` submits, Esc closes the modal, and focus returns to "Discard…".
- [ ] AC12 The mobile layout (<= 640 px) shows queue cards, a filter sheet, the Details accordion and a sticky action bar.
- [ ] AC13 axe finds no violations in the queue, detail-open, discard-modal and error states.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `features/parse-review/ReviewQueue.test.tsx::renders open reviews sorted by deadline with reasons` |
| AC2 | `ReviewQueue.test.tsx::syncs filters with url and loads more` |
| AC3 | `features/parse-review/ReviewDetail.test.tsx::renders a card per blocking kind with evidence` |
| AC4 | `ReviewDetail.test.tsx::resolve disabled until complete and page required` |
| AC5 | `ReviewDetail.test.tsx::resolve sends body then polls to resolved` |
| AC6 | `ReviewDetail.test.tsx::error codes` (one case per code) |
| AC7 | `features/parse-review/DiscardDialog.test.tsx::requires reason and sends discard` |
| AC8 | `ReviewDetail.test.tsx::read only without role` |
| AC9 | `ReviewDetail.test.tsx::injection needs acknowledgement` |
| AC10 | `ReviewQueue.test.tsx::state copy`, `ReviewDetail.test.tsx::state copy` |
| AC11 | `ReviewQueue.test.tsx::keyboard`, `ReviewDetail.test.tsx::keyboard and focus return` |
| AC12 | `ReviewQueue.test.tsx::mobile layout`, `ReviewDetail.test.tsx::mobile layout` (matchMedia mock) |
| AC13 | `features/parse-review/ParseReview.a11y.test.tsx` (vitest-axe) |
| contract | `apps/web/src/api/parse-review/http.test.ts::matches openapi snapshot` (against `services/pillar/tests/snapshots/openapi/parse_reviews.json`) |

## 15. Open questions

- **A count badge on the nav item?** Recommended default: yes, the open count from
  `counts.open`, shown only to `PARSE_REVIEW_ROLES`. `nav.ts` is shared, so S00/C2 adds a
  `badge` hook for it.
- **Should two people be able to work on the same review?** Recommended default: no lock
  for the MVP. `version_hash` and `review_closed` keep it safe, and the second person
  sees a clear message.
- **Inline PDF viewer instead of a new tab?** Recommended default: a new tab for the MVP.
  An inline viewer with highlighted spans is a later improvement, and would need a
  shared `DocumentViewer` primitive.
- **Should discarded opportunities be restorable?** Recommended default: no for the MVP.
  If a discard turns out to be wrong, a re-ingest from the source creates a new review.
