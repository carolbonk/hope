# SC24: Discover grants

| | |
|---|---|
| Route | `/discover` (query: `job` = the run being shown; defaults to the running or latest run) |
| Feature folder | `apps/web/src/features/discover/` |
| Built by | H2 |
| Primary users | Executive director or development lead of a small nonprofit. They come once during onboarding, then weekly or whenever they want fresh grants |
| Can act | Any signed-in user (the hackathon has no roles) |
| Status | Draft |

## 1. Purpose and user goals

This is where Hope goes looking for money. People arrive from:
- the end of onboarding (SC11: "Find grants for us")
- the nav item "Discover"
- the empty state of `/grants` ("No grants yet. Let Hope find some.")

The job: start a search based on what Hope knows about the nonprofit, optionally steer it,
and then **trust what's happening** while it runs. A run takes 1-3 minutes, so the screen
has to show real work (queries, pages, grants found) rather than a spinner.

Within 5 seconds the screen must answer:
1. **What will Hope search for?** A summary of the profile it uses, plus the optional focus and location.
2. **Is it working, and how far along is it?** The current step text, the counts and a progress bar.
3. **What has it found so far?** Grant cards that appear as they're saved.

**Primary action:** "Find grants" (start a run). When the run finishes, "Review N new grants" (go to `/grants`).
**Secondary actions:** add focus keywords and a location, edit the profile, open a found
grant, see the activity log, open a past run.

## 2. Information hierarchy

Before a run (idle):
1. **The start card.** "Hope will search the web using your profile" with a short profile
   summary, then the two optional inputs and the big button. This is the only decision on
   the page.
2. **Past runs**, below. Useful context ("we already searched yesterday"), but not the focus.

During a run:
1. **The live status line and progress bar.** One sentence that changes, for example
   "Reading: Riverbend Community Foundation", plus three counters (searches, pages read,
   grants found).
2. **The grants found so far,** as cards that stream in. This is the payoff, and it keeps the
   user engaged.
3. **The search plan** (the queries, each with a ✓ and a result count), so the user sees
   *what* Hope looked for.
4. **The activity log** is collapsed by default. It's for people who want proof of every
   step, including what was skipped and why.

After a run: a summary banner with one primary button, "Review N new grants". The cards stay.

Deliberately hidden:
- the raw pages (Hope never stores them)
- per-page LLM details
- the skipped pages, which are only in the log, with reasons

## 3. Wireframe

Desktop (>= 1024 px), idle:

```text
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ Discover grants                                                                           │  <- PageHeader
│ Hope searches the web for open grants that fit Riverbend Youth Alliance.                  │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌ Start a search ──────────────────────────────────────────────────────────────────────┐ │  <- start card (Card raised)
│ │ Hope will search using your profile                                  [Edit profile ›] │ │
│ │  Mission  "We pair young people in Cuyahoga County with trained mentors…"             │ │
│ │  Programs ( Mentor Futures ) ( After-School Studio ) ( Summer Bridge )                 │ │
│ │  Serves   Youth 10-18 · Cuyahoga County, OH                                            │ │
│ │                                                                                        │ │
│ │ Focus keywords (optional)  [ mentoring × ] [ arts × ] [ add a keyword…      ]  2 of 5   │ │
│ │ Location (optional)        [ Cuyahoga County, OH                              ]        │ │
│ │                                                                                        │ │
│ │ Takes 1-3 minutes. You can leave this page; the search keeps going.  [ 🔍 Find grants ] │ │
│ └────────────────────────────────────────────────────────────────────────────────────────┘ │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ Past searches                                                                              │  <- past runs (Card inset, Table)
│ When            Focus / location                  Result               Duration           │
│ 2 days ago      mentoring · Cuyahoga County, OH   ✓ 5 grants (2 new)   2 min 41 s  [View] │
│ Nov 6, 9:10 AM  profile only                      ✕ Search failed      20 s        [View] │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

Desktop, running:

```text
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ Discover grants                                              Started 0:44 ago · ● Running  │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌ Progress ─────────────────────────────────────────────────────────────────────────────┐ │
│ │ ◌ Scoring fit: Youth Arts Fund 2027                                                    │ │  <- live step (aria-live)
│ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░  48%                                                      │ │  <- Progress
│ │ Searches 6 of 6   ·   Pages read 7 of 21   ·   Grants found 3                          │ │
│ └────────────────────────────────────────────────────────────────────────────────────────┘ │
├───────────────────────────────────────────────┬───────────────────────────────────────────┤
│ Found so far (3)                               │ What Hope searched for                    │
│ ┌──────────────────────────────────────────┐  │ ✓ youth mentoring grants Ohio 2026    (8) │
│ │ 84 Strong fit                     NEW    │  │ ✓ after-school program grants Cuyahoga (7)│
│ │ Youth Arts Fund 2027                     │  │ ✓ community foundation grants Clevel… (8) │
│ │ Riverbend Community Foundation           │  │ ✓ mentoring nonprofit funding oppor…  (6) │
│ │ Up to $25,000 · Due Jan 15, 2027         │  │ ✓ Ohio arts education grants for non… (5) │
│ │ Supports arts programs for young people… │  │ ✓ corporate giving youth programs NE… (4) │
│ └──────────────────────────────────────────┘  │                                           │
│ ┌──────────────────────────────────────────┐  │ Activity ▸ (17 steps)                     │
│ │ 78 Good fit · Mentoring Matters Grant …  │  │                                           │
│ └──────────────────────────────────────────┘  │                                           │
└───────────────────────────────────────────────┴───────────────────────────────────────────┘
```

Desktop, done (the banner replaces the progress card):

```text
┌ ✓ Search complete ─────────────────────────────────────────────────────────────────────────┐
│ Found 5 grants · 2 new · 1 skipped because its deadline passed · took 2 min 41 s           │
│                                         [ Search again ]   [ Review 2 new grants ▶ ]       │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

Mobile (<= 640 px):
- The start card fields stack, and "Find grants" is full width.
- While running, the progress card is sticky at the top in a compact form: the step text on
  one line with a thin bar under it.
- The cards come next as a single column. "What Hope searched for" and "Activity" become
  accordions under the cards.
- Past searches become a list of cards.
- When done, "Review N new grants" is a sticky bottom button.

## 4. Content inventory

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Org name in the subtitle | `GET /v1/me` -> agency, via the profile (`GET /v1/agencies/{agency_id}/profile` from H1) -> `legal.legal_name` | "…that fit Riverbend Youth Alliance." | Falls back to "…that fit your organization." |
| Profile summary: mission | profile `mission.mission_statement` | Quote, first 160 characters + "…" | Hidden if empty (then the start is blocked; see section 7) |
| Profile summary: programs | profile `programs[].name` | Chips, at most 4, then "+2 more" | |
| Profile summary: serves | `programs[].target_demographics[].population` (first), `service_area[]` | "Youth 10-18 · Cuyahoga County, OH" | Parts that are missing are left out |
| Focus keywords | local input -> `focus_keywords` | Chips with × | 0-5 chips, 2-40 characters each. Enter or comma adds one, and duplicates are ignored (case-insensitive). Counter "2 of 5" |
| Location | local input, prefilled from `service_area[0]` -> `location` | Free text | 2-80 characters or empty. Placeholder "City, county or state (optional)" |
| Status chip | `job.status` | "● Running", "✓ Done", "✕ Failed", "◌ Starting" | Icon + text |
| Elapsed | `elapsed_s` (server) + a client tick | "Started 0:44 ago" | mm:ss, ticking every second while running. Under reduced motion it updates every 5 s |
| Current step | `job.progress.current_step` | "Reading: Riverbend Community Foundation" | One line, ellipsis at 90 characters |
| Progress bar | derived: `5%` after planning, then `+25% × queries_done/queries_total`, then `+70% × pages_read / min(counts.urls_found, limits.max_pages)` | "48%" | Never goes down. 100% only at `done`. Indeterminate until `queries_total > 0` |
| Counters | `progress.queries_done/queries_total`, `pages_read` / `min(urls_found, max_pages)`, `candidates_found` | "Searches 6 of 6 · Pages read 7 of 21 · Grants found 3" | |
| Query list | `job.queries[]` + `steps[kind=query]` (`result_count`) | "✓ youth mentoring grants Ohio 2026 (8)" | ◌ while it's being searched, ✓ when done, ⚠ "failed" when a `warning` mentions it. Truncated at 40 characters with a tooltip |
| Candidate card: score | `candidates[].fit_score` | "84 Strong fit" | 80+ "Strong fit" (icon ▲, good tone), 50-79 "Possible fit" (◆, info), below 50 "Weak fit" (▽, neutral). Icon + text |
| Card: NEW chip | `candidates[].is_new` | "NEW" | Shown only when `is_new`. A re-found grant shows "Updated" |
| Card: status | `candidates[].status` | "Saved" ★ / "Passed" ⊘ chip | Only when it isn't `new` (the user may curate in H3 while the run continues) |
| Card: title, funder | `title`, `funder` | Two lines | The title ellipsises at 2 lines |
| Card: amount | `amount_max` or else `amount_text` | "Up to $25,000", or the quoted text "Varies by project" | `formatMoney()` (`lib/money.ts`) when `amount_max` is set, otherwise the quote in quotation marks. "Amount not stated" when both are null |
| Card: deadline | `deadline`, `deadline_text` | "Due Jan 15, 2027" / "Rolling" / "Deadline: see funder page" | Red with "!" when 14 days or less away |
| Card: summary | `summary` | 2 lines, with ellipsis | |
| Card link | `grant_id` | -> `/grants/{grant_id}` (H3, SC26) | Opens in the same tab. The run continues |
| Activity log | `steps[]` | "14:00:44 · Saved: Youth Arts Fund 2027 (fit 84)" | Newest at the bottom. `skip` rows in muted text with ⊘, `warning` ⚠ amber, `error` ✕ red. Rows with a URL link to it (new tab, `rel="noopener noreferrer"`) |
| Done summary | `counts` | "Found 5 grants · 2 new · 1 skipped because its deadline passed · took 2 min 41 s" | Zero parts are left out. "Found 0 grants" has its own copy (section 7) |
| Review button | `counts.candidates_new` | "Review 2 new grants" | -> `/grants?status=new`. With 0 new: "See all grants" -> `/grants` |
| Past runs | `GET /v1/discovery/jobs?limit=10` -> `items[]` | When (relative under 7 days, otherwise a date), focus / location ("profile only" when empty), result ("✓ 5 grants (2 new)" / "✕ Search failed"), duration | "View" -> `/discover?job={job_id}` |

## 5. Components

The surfaces use the liquid-glass tokens from README "Design system: liquid glass". The page
sits on `glass-backdrop`, and **no text sits directly on it**. Every heading, line of copy and
count below lives on a `glass-panel` or stronger.

- **Page header:** `PageHeader` inside a `glass-panel` strip, so the title and subtitle never
  sit on the backdrop. The status chip is a `Badge` (icon + text). The app's sidebar and top
  bar are `glass-chrome` (H0).
- **Start card:** `Card` as a `glass-panel`.
  - Keyword chip input: built inside the feature from `TextField` (`glass-inset`) + `Badge`
    chips, with a remove `Button` (ghost). See open questions.
  - Location: `TextField` (`glass-inset`).
  - Primary `Button`, which uses `glass-active` while pressed.
  - The first-time hint ("You haven't searched yet…") is a line inside this panel.
- **Progress card:** `Card` (`glass-panel`) with `Progress` (H0) and the step text in an
  `aria-live` region.
- **Candidate cards:** `Card` (`glass-panel`), each one a link. Hover or focus shows a brighter
  tint; pressing uses `glass-active`. The empty line "Grants will appear here…" sits in a
  `glass-inset` well inside the results panel.
- **Query list and activity log:** a `glass-panel` containing a `glass-inset` well. The log uses
  `<details>`, or H0's `Tabs` (active tab `glass-active`) on mobile.
- **Done banner and error notice:** `SuccessNotice` / `ErrorNotice` as a `glass-panel` with a
  1 px status border and an icon. The two buttons follow the same `Button` rules.
- **Past runs:** `Table` inside a `glass-panel` on desktop, and a list of `glass-panel` cards
  on mobile.
- **Toasts:** `Toast` (H0) on `glass-overlay`.
- **Mobile sticky elements:** the compact progress bar and the sticky "Review" bar use
  `glass-chrome`.
- No `neu-*` classes anywhere.

## 6. Interactions

1. **Mount.** Call `GET /v1/discovery/jobs?limit=10`, then:
   - if `running_job_id` is set, or the URL has `?job=`, call `GET /v1/discovery/jobs/{id}?since_seq=0`
     and show the running or done view
   - otherwise show the idle view
   - the profile summary loads in parallel from `GET /v1/agencies/{agency_id}/profile` (H1)
2. **Add a keyword.** Typing, then Enter or comma, adds a chip. Backspace in an empty input
   removes the last chip. A 6th keyword shows the inline hint "Up to 5 keywords." and isn't
   added.
3. **Find grants.** Sends `POST /v1/discovery/jobs` with `{focus_keywords, location}` (an
   empty location is sent as `null`). While it's pending the button reads "Starting…".
   - **202:** set `?job={job_id}` (`router.replace`), switch to the running view, and start polling.
   - **409 `job_running`:** Toast "A search is already running. Showing it now." Load that `job_id`.
   - **422 `profile_incomplete`:** an inline error in the start card: "Hope needs a bit more
     about you first: {missing as words}." plus "Complete your profile" (-> `/profile`).
     `missing` maps `mission.mission_statement` to "your mission" and `programs` to "at least
     one program".
   - **422 `validation_error`:** inline errors on the field.
   - **429 `daily_limit`:** "You've run {limit} searches today. You can search again {resets_at as relative time}."
   - **401:** H0's `RequireSession` sends the user to `/login`.
   - **5xx / network:** "We couldn't start the search. Try again."
4. **Polling.**
   - While the status is `queued` or `running`: `GET /v1/discovery/jobs/{id}?since_seq={last_seq}`
     every 1.5 s. New steps are appended, `candidates` is replaced (new cards animate in),
     and job/progress/counts are replaced.
   - Polling backs off to 5 s when the tab is hidden.
   - On 3 network errors in a row it stops and shows "Lost connection to the search. It's
     still running on the server." plus "Reconnect".
   - It stops at `done` or `failed`.
5. **Open a card.** Navigates to `/grants/{grant_id}`. When the user comes back, the run
   view reloads from `?job=`.
6. **Expand the activity log.** Shows every step, and auto-scrolls to the bottom only if the
   user hasn't scrolled up ("Jump to latest" appears when they have).
7. **Done.**
   - "Review N new grants" goes to `/grants?status=new`.
   - "Search again" returns to the idle view with the last run's keywords and location
     filled in.
8. **Failed.** The banner gives the error text from the server, plus "Try again" (the same as
   Find grants with the same inputs) and "See activity".
9. **Past run "View".** Sets `?job=`, loads that job, shows its final state, and doesn't
   poll if it has finished.
10. **Keyboard.** In the keyword input, Enter adds a chip. `Ctrl+Enter` anywhere in the
    start card submits it. Cards are links in tab order. `l` toggles the activity log when
    focus isn't in an input.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading (first load) | Start card skeleton and 3 past-run row skeletons, `role="status"` "Loading…" |
| Idle, first time (no past runs) | The start card, and under it "You haven't searched yet. Your first search usually finds 5-15 grants." |
| Idle, profile incomplete | The start card with the button disabled and the notice "Add your mission and at least one program so Hope knows what to look for." + "Complete your profile" |
| Starting (`queued`) | Progress card with an indeterminate bar and "Starting the search…" |
| Running | Section 3 wireframe. The step text comes from the server |
| Running, no grants yet | In the cards area: "Grants will appear here as Hope finds them." |
| Done, with new grants | "✓ Search complete" banner with the summary + "Review {n} new grants" |
| Done, nothing new | "✓ Search complete. Found {found} grants, all of them already in your list." + "See all grants" |
| Done, 0 found | "Hope didn't find open grants this time. Try adding focus keywords, a broader location, or more detail about your programs." + "Search again" + "Edit profile" |
| Done, stopped early | The banner plus a warning line "Stopped early after {elapsed} to keep the search quick. Read {n} of {m} pages." |
| Failed | `ErrorNotice` "The search didn't finish." + the server's `error` text + "Try again" |
| Lost connection | "Lost connection to the search. It's still running on the server." + "Reconnect" |
| Daily limit | "You've run {limit} searches today. You can search again {in 6 hours}." |
| Job not found (`?job=` is wrong) | "That search doesn't exist." + "Start a new search" |
| Offline | Banner "You're offline." "Find grants" is disabled. Polling pauses and resumes on reconnect |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount | `GET /v1/discovery/jobs?limit=10` | `items[]` (all fields), `running_job_id` | Refetched when a run finishes |
| Mount | `GET /v1/agencies/{agency_id}/profile` (H1) | `legal.legal_name`, `mission.mission_statement`, `programs[].name`, `programs[].target_demographics[].population`, `service_area` | Session cache |
| Mount | `GET /v1/me` (H0) | `agency_id` | Session |
| Find grants | `POST /v1/discovery/jobs` | the whole `DiscoveryJobView` | — |
| Poll | `GET /v1/discovery/jobs/{id}?since_seq={last_seq}` | `job.status`, `job.queries`, `job.progress.*`, `job.error`, `counts.*`, `steps[]`, `last_seq`, `candidates[]` (`grant_id`, `title`, `funder`, `fit_score`, `amount_text`, `amount_max`, `deadline_text`, `deadline`, `summary`, `is_new`, `status`), `elapsed_s`, `limits` | Every 1.5 s while running (5 s when the tab is hidden) |

Every field above is returned by H2's endpoints or by H0 and H1's profile endpoint. The
screen makes no other calls.

## 9. Responsive behaviour

- >= 1280 px: while running, two columns (cards 3/5, then the queries and activity 2/5). Cards are a 2-column grid inside the left column.
- 1024-1279 px: the same, with cards in 1 column.
- 641-1023 px: one column (progress, cards in a 2-column grid, queries, activity).
- <= 640 px: the sticky compact progress bar, cards in 1 column, queries and activity as accordions, past runs as cards, and the sticky "Review" button when done.

## 10. Accessibility

- The step text is in an `aria-live="polite"` region, **throttled**: it announces at most
  once every 5 s, plus milestones (search plan ready, each grant found, done or failed), so
  a screen reader isn't flooded.
- The `Progress` bar has `role="progressbar"` with `aria-valuenow`, `aria-valuemin=0`,
  `aria-valuemax=100`, and `aria-valuetext` such as "48 percent, 3 grants found".
- New cards are added without moving focus. Each card is a link whose accessible name is
  "{title}, {funder}, {fit label} {score}, {amount}, {deadline}, new".
- The keyword chips form a list. Each chip's remove button has `aria-label="Remove keyword {kw}"`.
- Status (running, done, failed), fit labels, NEW and skip and warning rows all use icon + text.
- On failure, focus moves to the error heading. When a run finishes, focus moves to the
  done banner's heading, but only if focus was in the progress card (never pulled from
  elsewhere).
- With `prefers-reduced-motion`: cards appear without the slide or fade, the bar doesn't
  animate between values, and the elapsed timer updates every 5 s.
- Contrast is AA (4.5:1 for body text), checked against the **worst-case backdrop colour**
  behind each `glass-panel`. Every card and input has a 1 px border at 3:1 or better. No
  text, count or icon sits directly on `glass-backdrop`.
- **Reduced transparency:** under `@media (prefers-reduced-transparency: reduce)`, and in
  browsers without `backdrop-filter`, every `glass-*` surface becomes a solid panel with the
  same layout, borders and contrast. The streaming cards, progress card and sticky bars stay
  readable with no blur at all. A test checks that the screen renders in this mode.
- With `prefers-reduced-motion`, the backdrop gradient and the highlight shimmer stop
  moving (as well as the motion rules above).

## 11. Fixture data

`apps/web/src/api/discover/fixture.ts` exports `FixtureDiscoverApi`, with times relative
to `FIXED_NOW`.

**Past runs** (`listJobs`):
1. done, 2 days ago, "mentoring · Cuyahoga County, OH", 5 grants (2 new), 2 min 41 s
2. failed, Nov 6, "profile only", with the error "Web search is unavailable right now. Try again in a few minutes."

**`startJob(body)`** returns a scripted run that advances one frame per `getJob` call (or
per 1.5 s of fake timers):
- **frames:**
  1. queued
  2. "Reading your profile"
  3. "Planning searches"
  4. 6 queries arrive
  5. "Searching: …" ×6, with result counts
  6. "Found 21 unique links from 6 searches"
  7. pages being read, with 1 `skip` (expired), 2 `skip` (not a grant), 1 `warning` (couldn't read)
  8. 5 `candidate` events, matching the H2 demo seed (scores 84, 78, 71, 55, 38; one `is_new: false`)
  9. done
- **switches:**
  - `{focus_keywords: ["fail"]}` ends `failed`
  - `{focus_keywords: ["none"]}` ends done with 0 grants
  - `{focus_keywords: ["stop"]}` ends done with the "Stopped early" warning
- **errors:**
  - `startJob` while a scripted run is active returns 409 `job_running`
  - `new FixtureDiscoverApi({ profileIncomplete: true })` returns 422 `profile_incomplete` with `missing: ["programs"]`
  - `{ dailyLimit: true }` returns 429
  - `getJob("missing")` returns 404

**Profile fixture:** Riverbend Youth Alliance, with 3 programs and the service area "Cuyahoga County, OH".

## 12. Analytics and success measures

Events:
- `discover_viewed {has_running, past_runs}`
- `discover_started {keywords_count, has_location}`
- `discover_start_failed {code}`
- `discover_completed {found, new, duration_s, stopped_early}`
- `discover_failed {error}`
- `discover_card_opened {grant_id, score, while_running}`
- `discover_review_clicked {new}`

Success:
- 90% of runs finish `done` in under 3 minutes
- the median run finds 5 or more grants with a fit of 50 or more
- over 60% of finished runs lead to "Review" within 10 minutes
- 0 runs fail in the demo rehearsal

## 13. Acceptance criteria

- [ ] AC1 The idle view shows the profile summary (mission, programs, who is served), the keyword chip input (max 5, deduped) and the location prefilled from `service_area[0]`.
- [ ] AC2 "Find grants" sends the documented body, sets `?job=`, and switches to the running view. 409 `job_running` loads the running job with a toast.
- [ ] AC3 422 `profile_incomplete`, 422 `validation_error`, 429 `daily_limit` and network errors show their exact copy. An incomplete profile disables the button up front.
- [ ] AC4 While running, the step text, progress bar (monotonic, indeterminate until queries exist), counters, query list with result counts, and activity log update from polling with `since_seq`.
- [ ] AC5 Candidate cards stream in as they appear, with score label (icon + text), NEW/Updated, status chip, title, funder, amount (parsed or quoted) and deadline. Each card links to `/grants/{grant_id}`.
- [ ] AC6 Done shows the summary and "Review N new grants" -> `/grants?status=new`. The nothing-new, 0-found and stopped-early variants show their copy.
- [ ] AC7 Failed shows the server error with "Try again". Three poll failures show "Lost connection" with "Reconnect".
- [ ] AC8 Past searches list the runs, and "View" loads a finished run without polling. A wrong `?job=` shows the not-found copy.
- [ ] AC9 Polling stops on done or failed and slows to 5 s when the tab is hidden.
- [ ] AC10 Live-region announcements are throttled (at most once every 5 s plus milestones), and the progress bar exposes `aria-valuenow` and `aria-valuetext`.
- [ ] AC11 The mobile layout (<= 640 px) shows the sticky compact progress, single-column cards, accordions and the sticky Review button.
- [ ] AC12 axe finds no violations in the idle, running, done and failed states.
- [ ] AC13 With `prefers-reduced-transparency: reduce` (and without `backdrop-filter` support), every surface renders solid with the same layout, and no text element is a direct child of the `glass-backdrop` layer.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `features/discover/DiscoverScreen.test.tsx::idle shows profile summary and inputs` |
| AC2 | `DiscoverScreen.test.tsx::start sends body and switches to running`, `::job_running loads existing` |
| AC3 | `DiscoverScreen.test.tsx::start errors copy` (one case per code), `::incomplete profile disables start` |
| AC4 | `features/discover/RunProgress.test.tsx::updates step progress counters queries and log` (fake timers) |
| AC5 | `features/discover/CandidateCard.test.tsx::renders score amount deadline chips and link`, `RunProgress.test.tsx::cards stream in` |
| AC6 | `RunProgress.test.tsx::done variants` |
| AC7 | `RunProgress.test.tsx::failed and lost connection` |
| AC8 | `features/discover/PastRuns.test.tsx::lists runs and views finished run`, `DiscoverScreen.test.tsx::unknown job` |
| AC9 | `RunProgress.test.tsx::polling stops and backs off when hidden` |
| AC10 | `RunProgress.test.tsx::throttled announcements and progressbar aria` |
| AC11 | `DiscoverScreen.test.tsx::mobile layout` (matchMedia mock) |
| AC12 | `features/discover/Discover.a11y.test.tsx` (vitest-axe) |
| AC13 | `Discover.a11y.test.tsx::reduced transparency renders solid panels and no text on backdrop` (matchMedia mock + DOM check) |
| contract | `apps/web/src/api/discover/http.test.ts::matches openapi snapshot` |

## 15. Open questions

- **Should there be a "Stop search" button?** Recommended default: no for the hackathon. Runs
  are capped at 5 minutes and have no side effects. A cancel endpoint can come later.
- **Should the chip input be a shared primitive?** Recommended default: build it inside
  `features/discover`. If H1 or H3 need one too, ask H0 to promote it to `components/ui`.
- **Should `/grants` filter to this run's grants?** Recommended default: link to
  `/grants?status=new`. If H3 adds `?job=`, switch the link to it.
- **Should keywords be remembered between runs?** Recommended default: yes, but only through
  "Search again" (prefilled from the last run). There are no saved searches.
