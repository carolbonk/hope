# SC25: Grants (curate: New / Shortlist / Passed)

| | |
|---|---|
| Route | `/grants` (query: `tab=new\|saved\|passed`, `mode=cards\|list`, `sort`, `q`, `due`, `past=1`) |
| Feature folder | `apps/web/src/features/grants/` |
| Built by | H3 |
| Primary users | Executive director or development lead of a small nonprofit. Daily right after a discovery run, then weekly |
| Can act | Any signed-in user: Save, Pass, Undo, Reset (no roles in the hackathon) |
| Status | Draft |

## 1. Purpose and user goals

Users land here after discovery finishes (SC24's "Review 23 grants" button), from the nav, or
from `/`, which redirects here. The job is to sort a pile of grants into "worth applying for"
and "not for us", quickly and with confidence.

Within 5 seconds the screen must answer:
1. Is this grant a good fit, and why? (fit score and top reasons, each with a source)
2. Is it worth the effort? (amount and deadline urgency)
3. What could stop us? (concerns)

**Primary action:** Save or Pass the current card.
**Secondary actions:** Undo, open the grant overview (SC26), switch to list mode, sort, search and filter, and move between tabs.

## 2. Information hierarchy

1. **The fit score and band**, top left of the card: it's the decision Hope is helping with.
2. **Title and funder**, then **amount and deadline urgency** on one line.
3. **A one-line summary.**
4. **The top 3 reasons** (green check icons) and **top 3 concerns** (amber triangles), each with a `[cN]` chip. These are why the user can trust the score.

The eligibility summary, all citations and the full text are behind "Details" (SC26). The
card shows only what's needed to decide.

In card mode only one card has focus. The next two peek behind it, so the user knows more are
coming without being distracted. List mode trades the focus for density, for users who want to scan.

## 3. Wireframe

Desktop (>= 1024 px), card mode:

```text
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ Grants                                              [▦ Cards | ☰ List]   [Find more grants]│  <- header
│ [ New (23) ][ Shortlist (4) ][ Passed (6) ]                                                │  <- Tabs
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ [🔍 Search title, funder…   ]  Sort: (Best fit ▾)  Due: (Any|14d|30d|60d)                  │  <- filter bar (Card inset)
├───────────────────────────────────────────────────────────────────────────────────────────┤
│                 ┌───────────────────────────────────────────────┐┐┐                        │
│                 │ ● 86  Strong fit                     3 of 23  │││  <- card stack          │
│                 │ Youth Development Grants 2027                 │││     (Card raised)       │
│                 │ The Cleveland Foundation · clevelandfoundation.org                         │
│                 │ Up to $50,000/yr      ⏱ 116 days · Mar 3, 2027│││                        │
│                 │ Two-year grants for out-of-school programs…   │││                        │
│                 │ Why it fits                                   │││                        │
│                 │  ✓ Funds youth mentoring, matches Mentor… [c1][c4]                         │
│                 │  ✓ Serves Cuyahoga County, in your area  [c2] │││                        │
│                 │  ✓ Award size fits your budget  (Unverified)  │││                        │
│                 │ Watch out                                     │││                        │
│                 │  ▲ Requires a 2025 audited financial stmt [c3]│││                        │
│                 │                               [Details →]     │││                        │
│                 └───────────────────────────────────────────────┘┘┘                        │
│                 [ ✕ Pass  ← ]        [ ↶ Undo ]        [ ★ Save  → ]                        │  <- action bar
│                 Tip: ← pass · → save · Z undo · Enter details                              │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ 2 grants with passed deadlines hidden · Show them                                          │  <- footer
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

List mode (desktop):

```text
│ Fit │ Grant                                   │ Amount        │ Due            │ Status │          │
│ ●86 │ Youth Development Grants 2027           │ Up to $50,000 │ 116 days       │ New    │[✕][★][→] │
│     │ The Cleveland Foundation                │               │ Mar 3, 2027    │        │          │
│ ◐62 │ Community Impact Fund                   │ $10k–$25k     │ ! 6 days       │ New    │[✕][★][→] │
│ …   │                                         │               │                │        │          │
│ Showing 1–20 of 23                                                    ‹ Prev   Next ›          │
```

Mobile (<= 640 px): the card fills the width, and the action bar sticks to the bottom as three
48 px buttons. Swiping left passes and swiping right saves. The filter bar collapses into a
"Sort & filter" button that opens a bottom-sheet `Drawer`. Tabs scroll horizontally. List mode
becomes compact rows (fit, title, due), and each row has a "…" menu with Save / Pass / Details.

## 4. Content inventory

| Element | Source (`GET /v1/grants`) | Format and example | Rules |
|---|---|---|---|
| Tab counts | `counts.new`, `counts.saved`, `counts.passed` | "New (23)" | Updated after each action from the action response, plus a refetch |
| Fit score | `fit_score`, `fit_band` | "● 86 Strong fit" | Strong ≥ 75 ● green, Good ≥ 55 ◐ blue, Weak < 55 ○ grey. Always icon + number + word |
| Position | index in the stack, `total` | "3 of 23" | Card mode only |
| Title | `title` | "Youth Development Grants 2027" | 2 lines max with an ellipsis; full title in `title` attr |
| Funder line | `funder`, `domain` | "The Cleveland Foundation · clevelandfoundation.org" | Funder ellipsis at 40 chars |
| Amount | `amount_max`, else `amount_text` | "Up to $50,000/yr" (from `amount_text` when it has "per year") or "$50,000" | Money via `lib/money.ts`. If `amount_max` is null, show `amount_text` in quotes. If both are null, "Amount not stated" (muted) |
| Deadline | `days_left`, `deadline`, `urgency`, `deadline_text` | "⏱ 116 days · Mar 3, 2027" | `urgent` (≤ 7): red "!" + "6 days left". `soon` (≤ 21): amber. `rolling`: "Rolling". `unknown`: `deadline_text`, or "Deadline not stated". `past`: "Deadline passed" (Passed tab or `past=1`) |
| Summary | `summary` | 1 line on the card | Ellipsis at 1 line; full text on SC26. `[cN]` markers are rendered as chips |
| Reasons | `reasons[0..2]` | "✓ Funds youth mentoring… [c1][c4]" | Up to 3. Each chip opens `CitationPopover`. `unverified` shows an "Unverified" outline chip with the tooltip "Hope couldn't find a source for this" |
| Concerns | `concerns[0..2]` | "▲ Requires an audited financial statement [c3]" | Same chip rules. "No concerns found" (muted) when empty |
| Status (list) | `status` | "New" / "Saved" / "Passed" | Badge with an icon |
| Hidden past | `hidden_past` | "2 grants with passed deadlines hidden · Show them" | Only when > 0. The link sets `past=1` |

## 5. Components

- **Header:** `Tabs` (H0) with count badges, a mode toggle (a `Button` pair, active `neu-pressed`, `aria-pressed`), and a "Find more grants" `Button` linking to `/discover`.
- **Filter bar:** `Card` (`neu-inset`) with an `Input` search, a `SelectField` for sort ("Best fit", "Deadline soonest", "Largest amount", "Newest") and a `Segmented` control for due.
- **Card stack:** `GrantCard` (feature component) on `Card` `neu-raised`, with two offset "peek" cards behind it (decorative, `aria-hidden`). Swipe uses pointer events with a 96 px threshold; the card rotates up to 8° and tints ✕ red or ★ green while dragging.
- **Action bar:** three `Button`s (Pass `danger`, Undo `neutral`, Save `primary`).
- **Citations:** `CitationChip` + `CitationPopover` (H0).
- **List mode:** `Table` with row actions.
- **Pass reason:** a small `Drawer` (bottom sheet) offering an optional reason after a pass, with a "Skip" button. It never blocks the next card.
- **Feedback:** `Toast` with an Undo action. `Progress` for "3 of 23".

## 6. Interactions

1. **Save** (★ button, → key, or swipe right): `POST /v1/grants/{id}/save`.
   - Optimistic: the card flies right (with reduced motion: a 150 ms fade) and the next card takes focus. Shortlist +1, New −1.
   - Toast: "Saved to shortlist", with Undo for 8 s.
   - On error the card comes back, with the toast "Couldn't save. Try again." For 404 `grant_not_found`: "This grant was removed", and the card is dropped.
2. **Pass** (✕ button, ← key, or swipe left): `POST /v1/grants/{id}/pass` with `{}`.
   - Optimistic, the same as Save. Toast "Passed", with Undo for 8 s.
   - Then the reason sheet appears: "Why pass? (optional)" with chips "Not a fit", "Too small", "Deadline too soon", "Not eligible", "Other…". Choosing one sends `POST .../pass` again with `{reason}`, which is idempotent and records the reason.
   - The sheet closes on its own after 6 s, or on any key.
3. **Undo** (button, Z key, or the toast action): `POST /v1/grants/{id}/reset` for the last action. Undo goes back up to 5 actions in this session, kept as an in-memory stack. The card comes back in front of the stack and the counts revert. When there's nothing to undo, the Undo button is disabled.
4. **Details** (the "Details" link, Enter on the focused card, or a row click): navigates to `/grants/{id}`. Coming back restores the tab, mode, filters and stack position from the URL and session storage.
5. **Tabs:** `?tab=`. Shortlist and Passed default to list mode. Their row actions are "Remove from shortlist" (reset), "Pass" and "Restore" (reset).
6. **Search, sort and due:** update the URL. Search is debounced by 300 ms. The page refetches `GET /v1/grants?...&limit=20&offset=0` and resets the stack to the first card.
7. **Mode toggle:** `?mode=`. The choice is remembered in `localStorage` (`hope.grants.mode`).
8. **End of stack:** when the last card is decided, the screen shows the "All caught up" state (section 7). If `total` is more than the loaded count, the next 20 are fetched in the background when 3 cards remain.
9. **Keyboard:** ← / → / Z / Enter as above, `/` focuses search, `1` / `2` / `3` switch tabs. The keys are inactive while focus is in an input.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading | Tab skeletons + one card skeleton (title bar, 3 reason lines) + action bar disabled |
| Empty, never discovered (`counts` all 0) | "No grants yet. Let Hope search the web for grants that fit your nonprofit." + `Button` "Find grants" -> `/discover` |
| New tab empty, others not | "All caught up. You've reviewed every new grant." + "View shortlist (4)" + "Find more grants" |
| Shortlist empty | "Your shortlist is empty. Save grants from New to build it." + "Review new grants" |
| Passed empty | "Nothing passed yet." |
| Filtered to empty | "No grants match these filters." + "Clear filters" |
| Error loading | Banner "We couldn't load your grants. Try again." + Retry. Keep the last loaded cards |
| Action error | Toast "Couldn't save. Try again." or "Couldn't pass. Try again." The card returns |
| Not signed in (401) | H0 `RequireSession` redirects to `/login` |
| Offline | Banner "You're offline. Changes will fail until you reconnect." Action buttons disabled |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount, tab, filter, sort, search | `api.grants.list({status, sort, q, deadline_within_days, include_past, limit: 20, offset})` -> `GET /v1/grants` | all `GrantCard` fields, `total`, `counts`, `hidden_past` | Keep the previous data while loading. Refetch on window focus if older than 60 s |
| 3 cards left | the same call with `offset += 20` | `items` | Appended to the stack |
| Save / Pass / Undo | `api.grants.save(id)`, `api.grants.pass(id, body?)`, `api.grants.reset(id)` | `status`, `previous_status`, `changed` | Optimistic. Rolled back on error; counts refetched after |
| App shell | `GET /v1/me` (H0) | `display_name` | Session |

Client (`apps/web/src/api/grants/index.ts`): `list(query): Promise<GrantListPage>`,
`get(grantId): Promise<GrantDetail>`, `save(grantId)`, `pass(grantId, body?: PassBody)` and
`reset(grantId)`, which all return `Promise<StatusChange>`. They throw `ProblemError`. The
shapes are in `docs/specs/features/H3-curated-list.md`.

## 9. Responsive behaviour

- ≥ 1280 px: the card is 640 px wide and centred. In list mode all columns are shown.
- 1024-1279 px: the same layout; the card is 560 px.
- 641-1023 px: the card is full width minus 32 px. In list mode the Amount and Due columns merge.
- ≤ 640 px: as in section 3. Swipe is enabled; the buttons stay as the accessible path.

## 10. Accessibility

- The card stack is a `region` with `aria-label="Grant 3 of 23"`. The current card is an `article` with `aria-labelledby` set to its title, and gets focus after each decision.
- Swipe is never the only way: the buttons and keys do the same thing. The buttons have visible labels and shortcut hints (`aria-keyshortcuts`).
- Each decision is announced in `aria-live="polite"`: "Saved Youth Development Grants 2027. 22 left."
- Fit band, urgency, reason and concern icons always have text. Colour is never alone.
- Citation chips are buttons named "Source c1: Youth Development, The Cleveland Foundation". The popover returns focus to the chip on close.
- With `prefers-reduced-motion`, there's no fly-out or rotate, only a 150 ms fade.
- Contrast is AA. Cards and inputs have a 1 px border with at least 3:1 contrast.

## 11. Fixture data

`api/grants/fixture.ts` holds 8 candidates. The API tests use the same 8.

| # | Fit | Status | Amount | Deadline | Notes |
|---|---|---|---|---|---|
| 1 | 86 strong | new | `amount_max` $50,000 | 116 days | 3 cited reasons, 1 cited concern |
| 2 | 62 good | new | text only ("$10,000-$25,000") | 6 days (urgent) | |
| 3 | 48 weak | new | none ("Amount not stated") | rolling | |
| 4 | 77 strong | new | | 18 days (soon) | One unverified reason |
| 5 | 70 good | saved | | | |
| 6 | 55 good | saved | | unknown (`deadline_text` "Spring 2027") | |
| 7 | 40 weak | passed | | | |
| 8 | 80 | new | | past (−3 days) | Hidden by default |

There are also three extra fixture states: an empty fixture (everything 0), an error fixture
(`list` throws `ProblemError(500)`), and an action-error fixture (`save` throws once).

## 12. Analytics and success measures

Events (console logger `features/grants/analytics.ts`):
- `grants_viewed {tab, mode, total}`
- `grant_saved {grant_id, fit_score, position, input: "button|key|swipe"}`
- `grant_passed {grant_id, fit_score, reason?}`
- `grant_undo {action}`
- `grant_details_opened {grant_id, from: "card|list"}`

Success: a user decides on 20 cards in under 4 minutes, and Undo is used in under 10 % of
decisions. A high undo rate would mean accidental swipes.

## 13. Acceptance criteria

- [ ] AC1 Card mode shows the fit (icon + number + band), title, funder line, amount, deadline urgency, a 1-line summary, and up to 3 reasons and 3 concerns, each with a citation chip or an "Unverified" chip.
- [ ] AC2 Save and Pass work by button, by ←/→ keys and by swipe (simulated pointer events past 96 px). Each is optimistic, updates the counts, and announces the result.
- [ ] AC3 Undo (button, Z key or toast) resets the last action, up to 5 deep, and brings the card back to the front.
- [ ] AC4 After a pass, the optional reason sheet sends `pass` with the chosen reason, and never blocks the next card.
- [ ] AC5 An action error rolls the card back and shows the exact toast copy.
- [ ] AC6 Tabs, mode, sort, search and due are reflected in the URL and restored on reload. The mode is remembered.
- [ ] AC7 List mode shows the table with row actions and paging. Shortlist and Passed have Remove/Restore.
- [ ] AC8 The hidden-past footer shows `hidden_past` and "Show them" includes past grants.
- [ ] AC9 Every state in section 7 renders with the exact copy.
- [ ] AC10 Clicking a citation chip opens the popover with the quote and source, and focus returns to the chip.
- [ ] AC11 The mobile layout has a sticky action bar and a filter bottom sheet.
- [ ] AC12 axe finds no violations in card mode, list mode and the empty state.

## 14. Test plan

| AC | Test |
|---|---|
| AC1 | `features/grants/GrantCard.test.tsx::renders fit money deadline reasons and citations` |
| AC2 | `GrantsScreen.test.tsx::save and pass by button key and swipe` |
| AC3 | `GrantsScreen.test.tsx::undo stack` |
| AC4 | `GrantsScreen.test.tsx::pass reason sheet` |
| AC5 | `GrantsScreen.test.tsx::action error rolls back` |
| AC6 | `GrantsScreen.test.tsx::url state restored` |
| AC7 | `GrantsList.test.tsx::list mode actions and paging` |
| AC8 | `GrantsScreen.test.tsx::hidden past footer` |
| AC9 | `GrantsScreen.test.tsx::state copy` (one case per state) |
| AC10 | `GrantCard.test.tsx::citation popover focus` |
| AC11 | `GrantsScreen.test.tsx::mobile layout` (matchMedia mock) |
| AC12 | `GrantsScreen.a11y.test.tsx` (vitest-axe) |

## 15. Open questions

- **Should swipe be enabled on desktop with a mouse drag?** Recommended default: yes, but with the 96 px threshold and the visible buttons as the main path.
- **Should Pass ask for a reason every time?** Recommended default: offer it, optional, with a 6 s auto-close, so it never slows down triage.
- **Should saved grants leave the New tab immediately?** Recommended default: yes. Each tab is exactly one status.
