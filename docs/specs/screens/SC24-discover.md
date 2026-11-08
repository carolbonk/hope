# SC24: Discover grants

| | |
|---|---|
| Route | `/hope/discover` (`/` redirects here). No query parameters |
| Page | `apps/web/app/hope/discover/page.tsx` (built by PR #34: swipe deck, filters, match reasons, Save / Pass / Undo) |
| Built by | H2 adds the "Find new grants" run panel (`components/hope/discovery/`) and the live catalog (`lib/hope/sync/opportunities.ts`) |
| Primary users | Executive director or development lead of a small nonprofit, once after onboarding and then weekly |
| Can act | Anyone in this browser (offline demo); any signed-in user when `NEXT_PUBLIC_HOPE_API_URL` is set (no roles) |
| Status | Deck built; run panel and live catalog to build |

## 1. Purpose and user goals

Discover is where the nonprofit meets funding. One card at a time, it shows an opportunity, why it fits the
profile, and whether the known requirements are met. Then the user saves it (which opens the application
workspace, H4) or passes. With the backend on, Hope can also **find new real grants** from the web and
put them in the same deck.

Within 5 seconds the screen must answer:
1. **Is this a good fit for us?** Card: amount, deadline, "Why it fits", eligibility chip.
2. **Is it real?** Demo cards say "Fictional opportunity · Demo data"; found grants show their source URL
   and "Verified {date}".
3. **Can Hope find more?** The run panel: "Find new grants", or the live progress of the current run.

**Primary action:** Save (♥ / →). **Secondary:** Pass, Undo, Details, filters, Edit profile, Find new grants.

## 2. Information hierarchy

1. The card on top of the deck (the only decision on the page)
2. The Save / Pass / Undo / Details buttons under it
3. The aside: org summary (desktop), Edit profile, **run panel**, filters
4. The "How the match works" note (≥ 1280 px)

The run panel is secondary: compact when idle, and during a run it shows one status line, a bar and three
counters. The step log is collapsed. Raw pages, prompts and per-page LLM output are never shown.

## 3. Wireframe

Desktop (≥ 1024 px). Everything exists except the run panel:

```text
┌ aside 13.5rem ──────────┬ main ─────────────────────────────────────────────────────────────┐
│ YOUR ORGANIZATION        │ PageIntro (eyebrow, heading, sub)                      [DemoTag]  │
│ Tidepath Family Alliance │ [profile incomplete notice | pending-items note]                 │
│ Miami-Dade · Mentoring…  │ (toast, aria-live, 5 s)                                             │
│ [ Edit profile ↗ ]       │ ┌ card (glass-control) ─────────────────┐  HOW THE MATCH WORKS   │
│ ┌ Find real grants ────┐ │ │ art band · purpose     [Fictional · Demo]│  1 … 2 … 3 …          │
│ │ Hope searches the web │ │ │ FUNDER                                │                        │
│ │ with your profile.    │ │ │ Name                                  │                        │
│ │ ▸ Refine (optional)   │ │ │ $25,000–$50,000 · USD   21 days · Due │                        │
│ │ [ Find new grants ]   │ │ │ Where / Type / Focus / Purpose        │                        │
│ │ Last search: 2 days   │ │ │ ↗ Why it fits … [Needs review]        │                        │
│ │ ago · 3 grants (2 new)│ │ │ Source: … · Verified 2026-11-07       │                        │
│ └───────────────────────┘ │ └───────────────────────────────────────┘                        │
│ Geography [Any ▾]        │        ↶ Undo   ✕ Pass   i Details   ♥ Save                       │
│ Funding amount [Any ▾]   │        7 left · Keyboard: ← pass · → save · ↑ details · U undo    │
│ … 6 filters, Clear       │                                                                   │
└──────────────────────────┴───────────────────────────────────────────────────────────────────┘
```

Run panel while running (same slot):

```text
┌ Finding grants ─────────────── ● Running 0:44 ┐
│ Scoring fit: Rural Oral Health Access Grant…  │  <- current step (aria-live, throttled)
│ ▓▓▓▓▓▓▓▓▓▓▓░░░░░░░ 48%                        │  <- role="progressbar"
│ Searches 6/6 · Pages 7/21 · Grants 1          │
│ ▸ What Hope searched for (6)                  │  <- <details>, queries with result counts
│ ▸ Activity (5 steps)                          │  <- <details>, steps
└───────────────────────────────────────────────┘
```

Run panel when done:

```text
┌ ✓ Search complete ────────────────────────────┐
│ Found 3 grants · 2 new · took 2 min 41 s      │
│ [ Show the new grants ]   [ Search again ]    │
│ 1 found grant needs a check (no amount or     │
│ deadline on the page): Mobile Health Equip… ↗ │
└───────────────────────────────────────────────┘
```

Mobile (< 1024 px): the aside stacks above the deck (as today). The panel collapses to one line
("Find new grants" button, or "● Finding grants… 48%" with a "Details" toggle) so the card stays above the
fold; filters stay in their `<details>`.

## 4. Content inventory

| Element | Source | Rule |
|---|---|---|
| Card fields | `Opportunity` from `useOpportunities()` | Unchanged from PR #34 (`money()`, `daysUntil()`, `h.discover.*`) |
| Demo chip, `DemoTag` | `opp.source.kind === "demo"` | Only on demo cards. Found grants have `source.kind = "verified"` |
| Source line | `opp.source.url`, `opp.source.verifiedAt` | Found grants: link + "Verified {YYYY-MM-DD}" (the day Hope read the page) |
| Why it fits | `matchReasons(opp, profile)` | Deterministic; unchanged |
| AI fit (found grants only) | `opp.fit` | Inside the "Why it could fit" box, after the reasons: "Hope's read of the funder page (AI suggestion, check the source)", "AI fit score {score}/100", the reasons, "Concerns" + the concerns; " (unverified)" after items with `unverified: true`. Never shown on demo cards; never changes the eligibility chip or the order |
| Eligibility chip | `eligibility(opp, profile, app)` | Found grants always carry the `funder_eligibility` requirement, so they show "Needs review" until evidence is recorded in the workspace |
| Panel heading | state | "Find real grants" / "Finding grants" / "✓ Search complete" / "The search didn't finish" |
| Panel intro | — | "Hope searches the web with your profile and adds open grants to this deck." |
| Refine: focus keywords | local input → `focus_keywords` | One text field, comma-separated; code trims, drops < 2 or > 40 chars, dedupes case-insensitively; > 5 shows "Up to 5 keywords." |
| Refine: location | local input → `location` | Prefilled from `profile.serviceArea`; 2-80 chars or empty (sent as `null`). Placeholder "City, county or state (optional)" |
| Last search | `GET /v1/discovery/jobs?limit=1` → `items[0]` | "Last search: {relative} · {candidates_found} grants ({candidates_new} new)"; failed: "Last search didn't finish"; none: hidden |
| Status + elapsed | `job.status`, `elapsed_s` + client tick | "● Running m:ss", "◌ Starting"; icon + text |
| Current step | `job.progress.current_step` | One line, ellipsis at 60 chars |
| Progress | derived | 5% after planning, `+25% × queries_done/queries_total`, `+70% × pages_read / min(counts.urls_found, limits.max_pages)`; never goes down; 100% only at `done`; indeterminate until `queries_total > 0` |
| Counters | `progress.queries_done/queries_total`, `pages_read`/`min(urls_found, max_pages)`, `candidates_found` | "Searches 6/6 · Pages 7/21 · Grants 1" |
| Queries | `job.queries[]` + `steps[kind=query].result_count` | "✓ {query} ({n})", "⚠ failed" when a warning names it |
| Activity | `steps[]` | "hh:mm:ss · {text}"; `skip` ⊘ muted, `warning` ⚠, `error` ✕; rows with `url` link out (new tab, `rel="noopener noreferrer"`) |
| Done summary | `counts` | "Found {found} grants · {new} new · {skipped_expired} skipped because the deadline passed · took {duration}"; zero parts are left out |
| Needs a check | `candidates[]` where `needsCheck(c)` is set (shared helper from `lib/hope/sync/opportunities.ts`) | "{n} found grant(s) need a check (no amount or deadline on the page):" + title links to `url` |

## 5. Components

- **Unchanged:** `Deck`, `SwipeCard`, `RoundButton`, `Details`, `Select`, `EmptyState` in `page.tsx`, and
  `PageIntro`, `DemoTag`, `ClientOnly` from `components/hope/ui.tsx`.
- **`CardBody`** only gains the AI fit block (section 4) inside its existing "Why it could fit" box, using the
  same `ul` classes as the `matchReasons` list.
- **New:** `components/hope/discovery/DiscoveryPanel.tsx`, a `glass-panel` box (`rounded-xl glass-panel p-4`,
  like the mobile filters `<details>`). It uses `eyebrow`, `btnPrimary`, `btnSecondary`, `input`, `focusRing`
  from `components/hope/ui.tsx`. The bar is a `div` with `role="progressbar"` in `bg-teal-ink` on a
  `glass-control` track. "Refine", "What Hope searched for" and "Activity" are `<details>`.
- No new CSS, no `neu-*`, no change to `app/globals.css` or `components/ui/**`. Copy comes from
  `useHopeT().h.discovery` (new keys in `lib/hope/i18n.ts`, EN + ES).

## 6. Interactions

1. **Mount.** Deck as today. `useOpportunities()` shows found grants when `fetchOpportunities()` returns a
   non-empty list, otherwise the demo deck. With sync off the panel shows the offline state and makes no request.
   With sync on it calls `GET /v1/discovery/jobs?limit=1`; if `running_job_id` is set it resumes polling that job.
2. **Find new grants.** `POST /v1/discovery/jobs` with `{focus_keywords, location}`. The button reads
   "Starting…" and is disabled while pending.
   - 202: show the running state and start polling.
   - 409 `job_running`: toast "A search is already running. Showing it now." Poll `job_id` from the body.
   - 422 `profile_incomplete`: "Hope needs your mission and at least one program first." + "Complete profile" → `/hope/profile`.
   - 422 `validation_error`: the field message under Refine (opened).
   - 429 `daily_limit`: "You've run {limit} searches today. You can search again {resets_at, relative}."
   - 401: H0's `RequireSession` handles it (`hope:unauthorized`).
   - `network_error` / 5xx: "We couldn't start the search. Try again."
3. **Polling.** While `queued` / `running`: `GET /v1/discovery/jobs/{job_id}?since_seq={last_seq}` every 1.5 s
   (5 s when `document.hidden`). Append `steps`; replace `job`, `counts`, `candidates`, `last_seq`. Stop at
   `done` / `failed`. After 3 `network_error`s in a row stop and show "Lost connection to the search. It's
   still running on the server." + "Reconnect". A 404 shows "That search no longer exists." + "Find new grants".
4. **Done.** "Show the new grants" (only when `counts.candidates_new > 0`) calls `window.location.reload()`
   so `useOpportunities()` fetches again. "Search again" returns to idle with the last keywords and location.
5. **Failed.** The server's `job.error` text + "Try again" (same body).
6. **Deck.** Save / Pass / Undo, keyboard (← → ↑ U), filters and Details behave exactly as today, for demo and
   found cards alike. Keyboard shortcuts are ignored while focus is in a panel input (existing rule).
7. Leaving the page doesn't stop the run; coming back resumes it from `running_job_id`.

## 7. States and exact copy (panel)

| State | What shows |
|---|---|
| Offline (sync off) | "Live search needs Hope's server. These are demo cards." No button |
| Idle | Intro, "▸ Refine (optional)", "Find new grants", last-search line |
| Idle, never searched | Intro + "Your first search usually takes 1-3 minutes." |
| Starting | "◌ Starting the search…", indeterminate bar |
| Running | Section 3 "running" wireframe; step text from the server |
| Running, no grants yet | Counters show "Grants 0"; the deck is unchanged |
| Done, new grants | "✓ Search complete" + summary + "Show the new grants" + "Search again" |
| Done, nothing new | "✓ Search complete. Found {found} grants, all already in your deck." + "Search again" |
| Done, 0 found | "Hope didn't find open grants this time. Try a focus keyword or a broader location." + "Search again" |
| Done, stopped early | Banner + "Stopped early to keep the search quick. Read {pages_read} of {urls_found} pages." |
| Done, needs a check | The "needs a check" list under the summary |
| Failed | "The search didn't finish." + `job.error` + "Try again" |
| Lost connection | "Lost connection to the search. It's still running on the server." + "Reconnect" |
| Errors on start | Section 6 step 2 copy |

Deck states (no change): the profile-incomplete notice, the pending-items note, "No opportunities match these
filters." + "Clear filters", the end-of-deck state with "See saved opportunities".

## 8. Data and endpoints

| Trigger | Call | Fields used | Refetch |
|---|---|---|---|
| Mount (sync on) | `GET /v1/grants` ×3 (`status=new|saved|passed`, `include_past=true`, `limit=100`) inside `fetchOpportunities()` | `GrantCard` fields in H2's mapping table | Once per mount (H0's wiring) |
| Mount (sync on) | `GET /v1/discovery/jobs?limit=1` | `items[0]`, `running_job_id` | After a run ends |
| Find new grants | `POST /v1/discovery/jobs` | whole `DiscoveryJobView` | — |
| Poll | `GET /v1/discovery/jobs/{job_id}?since_seq={last_seq}` | `job.*`, `counts.*`, `steps[]`, `last_seq`, `candidates[]` (`title`, `url`, `amount_max`, `deadline`), `elapsed_s`, `limits` | 1.5 s / 5 s hidden, until `done` / `failed` |

The panel makes no other calls; the page's profile comes from `useHope()` (browser state, H1 syncs it). All
shapes are in `contracts/mocks/w3/` and `contracts/mocks/w4/grants.list/`; money arrives as `amount_minor`
and only `lib/hope/sync/opportunities.ts` converts it (`/ 100`).

## 9. Responsive behaviour

- ≥ 1280 px: aside | card | "How the match works" (as today); panel in the aside.
- 1024-1279 px: aside | card.
- < 1024 px: aside stacked above the deck; the panel is one line until expanded; the progress line stays
  one line while running.

## 10. Accessibility

- The step text sits in an `aria-live="polite"` region, announced at most once every 5 s plus milestones
  (plan ready, each grant saved, done, failed). It is separate from the deck's toast region.
- The bar: `role="progressbar"`, `aria-valuemin=0`, `aria-valuemax=100`, `aria-valuenow`, `aria-valuetext`
  "48 percent, 1 grant found"; indeterminate omits `aria-valuenow`.
- Status, skip, warning and error rows use icon + text. Links in the activity log name their target.
- Focus never moves on its own while running. On done or failed, focus moves to the panel heading only if
  focus was inside the panel.
- Contrast AA on `glass-panel`; with `prefers-reduced-transparency` / no `backdrop-filter`, the existing
  `globals.css` fallbacks make the panel solid. With `prefers-reduced-motion` the bar doesn't animate and the
  elapsed time updates every 5 s.

## 11. Fixture data

- `components/hope/discovery/fixture.ts` exports `FixtureDiscoveryApi`, built from the W3 mocks
  (`contracts/mocks/w3/*`): `listJobs` → `discovery.list/ok`; `startJob` → `discovery.start/queued`, then
  `getJob` advances queued → `discovery.get/running` → `discovery.get/done` (one frame per call or per 1.5 s
  of fake timers).
- Switches: `focus_keywords: ["fail"]` → `discovery.get/failed`; `["none"]` → done with 0 grants; `["stop"]`
  → done with the stopped-early warning; `["check"]` → done with one candidate whose `deadline` is null.
- Errors: `startJob` while a run is active → `discovery.start/job_running`; `{ profileIncomplete: true }` →
  `profile_incomplete`; `{ dailyLimit: true }` → `daily_limit`; `getJob("missing")` → `discovery.get/not_found`.
- The deck itself uses `lib/hope/demo.ts` and the `DEMO_PROFILE` in `lib/hope/store.ts`.

## 12. Acceptance criteria

- [ ] AC1 With sync off the page is exactly PR #34's deck plus the offline panel line, and no `/v1` request is made.
- [ ] AC2 Found grants appear in the deck with their source link and "Verified {date}", without the demo chip or `DemoTag`; demo cards keep both.
- [ ] AC3 Save / Pass / Undo, keyboard shortcuts and filters work the same on found and demo cards; saving a found grant creates `app:org-local-1:<grant_id>`.
- [ ] AC4 "Find new grants" sends the documented body (trimmed, deduped, ≤ 5 keywords; empty location → `null`) and switches to running; 409 resumes the running job with the toast.
- [ ] AC5 Each start error code shows its exact copy.
- [ ] AC6 While running, the step text, bar (monotonic, indeterminate until queries exist), counters, queries and activity update from polling with `since_seq`; polling stops at done/failed and slows to 5 s when hidden.
- [ ] AC7 Done shows the summary variants, the "needs a check" list and "Show the new grants" (reload); failed shows the server error with "Try again"; 3 network errors show "Lost connection" with "Reconnect".
- [ ] AC8 On mount with `running_job_id` set, the panel resumes that run.
- [ ] AC9 The live region is throttled and the progressbar exposes `aria-valuenow` / `aria-valuetext`.
- [ ] AC10 EN and ES copy both render (header toggle).
- [ ] AC11 No change to `app/globals.css`, `components/ui/**` or the deck components beyond mounting the panel and the AI fit block.
- [ ] AC12 Found cards show the AI fit block with its label, score, reasons, concerns and "(unverified)" marks; demo cards show none, and the block never changes the eligibility chip or the deck order.

## 13. Test plan (Vitest, offline)

| AC | Test (file::name) |
|---|---|
| AC1, AC11 | `app/hope/discover/page.test.tsx::sync off renders deck and offline panel without requests` |
| AC2 | `page.test.tsx::verified cards show source url and no demo chip` |
| AC3 | `page.test.tsx::save pass undo and keys on found cards` (seeded `fetchOpportunities` via `vi.mock("@/lib/hope/sync/opportunities")`) |
| AC4, AC5 | `components/hope/discovery/DiscoveryPanel.test.tsx::start body and running`, `::start errors copy` (one case per code) |
| AC6 | `DiscoveryPanel.test.tsx::polling since_seq progress counters and backoff` (fake timers) |
| AC7 | `DiscoveryPanel.test.tsx::done variants needs check and reload`, `::failed and lost connection` |
| AC8 | `DiscoveryPanel.test.tsx::resumes running job on mount` |
| AC9 | `DiscoveryPanel.test.tsx::throttled announcements and progressbar aria` |
| AC10 | `DiscoveryPanel.test.tsx::renders es copy` |
| AC12 | `page.test.tsx::ai fit block on found cards only` |
| contract | `components/hope/discovery/api.test.ts::parses every w3 mock` |

## 14. Open questions

- **Show grants with no amount or deadline as cards?** Not yet: it would make `amountMin` / `amountMax` /
  `deadline` optional, which Saved, Deadlines and H5 read as required. For now they are in the panel's
  "needs a check" list.
- **"Stop search" button?** No for the hackathon: runs are capped at 5 minutes and have no side effects.
