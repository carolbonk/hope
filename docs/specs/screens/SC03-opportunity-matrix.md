# SC03: Opportunity matrix

| | |
|---|---|
| Route | `/matrix` (query: `rec`, `elig`, `due`, `q`, `sort`, `selected`) |
| Feature folder | `apps/web/src/features/matrix/` |
| Built by | M2 (Watch/Skip, explanation) and M4 (Pursue); extends today's `MatrixScreen.tsx`, `OpportunityDrawer.tsx`, `filter.ts`) |
| Primary users | Development director / grant writer (daily), executive director (weekly) |
| Can act | Pursue: `development_director`, `executive_director`. Watch / Skip: any signed-in user |
| Status | Ready |

## 1. Purpose and user goals

The matrix is Hope's home base for deciding **which grants are worth the agency's limited
time**. Users arrive from the nav, from the dashboard's "Top recommendations" card, or from
a "new matches" notification.

Within 5 seconds the screen must answer:
1. What should we apply for next? (the top-ranked rows recommended "Pursue")
2. What's due soon? (deadline urgency)
3. Why is Hope recommending this? (score drivers, at a glance)

**Primary action:** Pursue an opportunity, which starts a workflow at the HITL-1 go/no-go gate.
**Secondary actions:** open the details drawer, Watch, Skip, filter and sort.

## 2. Information hierarchy

1. **Recommendation and fit.** Each row leads with its recommendation badge and composite
   score, because that is the decision Hope is helping with.
2. **Title, funder and amount.** What the grant is and whether it's worth it.
3. **Deadline urgency.** Shown as days remaining, which is easier to scan than a date.
4. **Score drivers.** Five compact bars, so a user can see *why* without opening anything.
5. **Capacity and risk flags.** Shown only when they matter (tight or conflicting capacity, risks).

The full evidence (which sentences in the RFP and profile drove each score), the
eligibility rules, and the effort estimate live in the drawer. They're needed to justify a
decision, not to triage.

Rows that are ineligible are hidden by default (filter "Eligibility: Eligible + Needs review"),
because the matrix is for decisions. A counter shows how many are hidden, with a link to show them.

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ Opportunity matrix                                       Updated 12 min ago  [↻ Refresh]  │
│ 42 open opportunities · 9 recommended to pursue · 3 due in 14 days                        │  <- summary strip (Card raised)
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ [🔍 Search title or funder        ]  Recommendation: (All|Pursue|Consider|Watch|Skip)      │  <- filter bar (Card inset)
│ Eligibility: (Eligible+Review ▾)  Due: (Any|14d|30d|60d)  Sort: (Rank ▾)   [Clear filters] │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ #  │ Recommendation │ Opportunity                         │ Award      │ Due     │ Drivers   │ Fit │   │
│ 1  │ ● Pursue  87   │ Youth Mentoring Expansion           │ $250,000   │ 12 days │ ▇▇▇▇▅     │ ✓   │[…]│
│    │                │ DOJ · OJJDP · O-OJJDP-2026-0042     │ up to      │ Mar 3   │           │     │   │
│ 2  │ ◐ Consider 72  │ Community Food Access               │ $100,000   │ 41 days │ ▇▇▅▃▇     │ ⚠   │[…]│
│    │                │ USDA · NIFA                          │            │         │           │tight│   │
│ …  │                │                                      │            │         │           │     │   │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ 6 ineligible opportunities hidden · Show them                              Page 1 of 3  ‹ › │
└───────────────────────────────────────────────────────────────────────────────────────────┘
                                  Drawer (opens on the right, 480 px):
                                  ┌──────────────────────────────────────┐
                                  │ Youth Mentoring Expansion        [×] │
                                  │ ● Pursue · 87/100 · Eligible ✓       │
                                  │ Why Hope recommends this             │
                                  │  "Strong match with your Mentor      │
                                  │   Futures program; award fits your   │
                                  │   budget band; 12 days is feasible." │
                                  │ Score breakdown            (tabs)    │
                                  │  Mission alignment   ▇▇▇▇▇ 91  [ev]  │
                                  │  Funding fit         ▇▇▇▇  80  [ev]  │
                                  │  Effort to funding   ▇▇▇▇  78        │
                                  │  Win probability     ▇▇▇   34%       │
                                  │  Deadline feasible   ▇▇▇▇  70        │
                                  │ Eligibility checks (6 passed, 0 open)│
                                  │ Effort: ~60 h · Expected value $85k  │
                                  │ Capacity: fits current pipeline      │
                                  │ Risks: requires 20% cost share       │
                                  │ Matched programs: Mentor Futures     │
                                  │ [View full opportunity →]            │
                                  │ [ Skip ] [ Watch ]   [ Pursue  ▶ ]   │
                                  └──────────────────────────────────────┘
```

Mobile (<= 640 px): the table becomes a stack of cards (recommendation + score, title,
funder, amount, days left, a single combined driver bar). Filters collapse into a "Filters (2)"
button that opens a bottom sheet. The drawer becomes a full-screen sheet with a sticky
action bar.

## 4. Content inventory

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Updated time | `OpportunityMatrix.generated_at` | "Updated 12 min ago"; tooltip with the full local time | Turns amber with "Scores may be out of date" if older than 24 h |
| Summary counts | derived from `rows` (after the eligibility filter) | "42 open · 9 recommended to pursue · 3 due in 14 days" | Each count is a link that applies that filter |
| Rank | `MatrixRow.rank` | "1" | Rank is Hope's order; it doesn't change when the user re-sorts, so it stays a stable reference |
| Recommendation | `MatrixRow.recommendation` | Badge "Pursue" / "Consider" / "Watch" / "Skip" | Icon + text + colour: Pursue ● green, Consider ◐ blue, Watch ○ amber, Skip – grey. Never colour alone |
| Composite score | `MatrixRow.composite_score` | "87" (integer, 0-100) | Rounded half-up. Shown next to the badge |
| Title | `GrantOpportunity.title` (`GET /v1/opportunities/{id}`, batch-loaded) | "Youth Mentoring Expansion" | One line, ellipsis at 60 characters; full title in tooltip |
| Funder line | `funder.agency_name`, `funder.sub_agency`, `source.external_id` | "DOJ · OJJDP · O-OJJDP-2026-0042" | Secondary text style |
| Award | `funding.award_ceiling` (or `award_floor`-`award_ceiling`) | "$250,000" with "up to"; "$50k-$100k" for a range | `Money` in minor units, formatted with `lib/money.ts`. "Not stated" if missing |
| Due | `deadlines.application_due` and `estimates.days_to_internal_deadline` | "12 days" with "Mar 3" below | Red with "!" icon if <= 7 days; amber if <= 14; "Rolling" if no deadline; "Passed" rows are never shown |
| Drivers | `scores.mission_alignment`, `funding_fit`, `effort_to_funding`, `win_probability` (×100), `deadline_feasibility` | Five mini-bars, fixed order, with hover labels | Each bar has an `aria-label` like "Mission alignment 91 of 100" |
| Capacity fit | `MatrixRow.capacity_fit` | ✓ fits, ⚠ tight, ✕ conflicts | Only "tight" and "conflicts" show text; "fits" shows only the check icon |
| Eligibility | `MatrixRow.eligibility` | In the drawer: "Eligible ✓", "Needs review ?", "Ineligible ✕" | In the table, a "?" chip appears next to the title when the row needs review |
| Explanation | `MatrixRow.explanation` | 1-3 sentences | Generated only from the row's numbers. Show "No explanation yet" if null |
| Dimension evidence | `GET .../matrix/{opp}/explanation` -> `dimensions[].evidence[]` | Quoted snippet + source ("RFP p. 4" / "Profile: Programs") | `[ev]` opens a popover with up to 3 snippets; "More" goes to SC04 |
| Eligibility checks | `.../explanation` -> `eligibility.rules[]` | "Applicant type: 501(c)(3) ✓" | Failing or needs-review rules listed first |
| Effort and value | `estimates.expected_hours`, `estimates.expected_value` | "~60 h · Expected value $85k" | "~" because it's an estimate. Hidden if both are null |
| Risks | `MatrixRow.risks[]` | Bulleted, max 3, "+2 more" | Amber icon |
| Matched programs | `MatrixRow.top_matched_programs[]` | Chips | Each links to that program in SC09 |
| Disposition | `.../disposition` (S05) | Row shows "Watching" or "Skipped" chip | Skipped rows are hidden unless the "Skip" filter is on |

## 5. Components

- Summary strip: `Card` (`neu-raised`), with `Badge`-style count links.
- Filter bar: `Card` (`neu-inset`) with `Input` (search), segmented control (`Button` group, active = `neu-pressed`), `Select`.
- Table: `Table` primitive, sticky header, row hover = slight raise; the whole row is clickable and opens the drawer (as well as the `[…]` button).
- Score bars: existing `ScoreBar` (compact variant in the table, full variant in the drawer).
- Drawer: **new shared primitive `Drawer`** (side sheet on desktop, full-screen sheet on mobile, focus trap, Esc closes). Request it under the wave's contracts spec. Until then, use `Modal`.
- Pursue confirmation: `Modal`.

## 6. Interactions

1. **Filter / search / sort.** Updates the URL query (`?rec=pursue&due=14&q=youth&sort=due`), then refetches
   `GET /v1/agencies/{agency_id}/matrix?recommendation=&eligibility=&due_within_days=&q=&sort=&page=`.
   The previous rows stay visible, dimmed, while loading. Search is debounced by 300 ms.
2. **Open details.** Click a row, or press Enter on a focused row. Sets `?selected={opportunity_id}`,
   opens the drawer, and fetches `GET .../matrix/{opportunity_id}/explanation`. The drawer shows the row's
   own data immediately and a skeleton for the evidence.
3. **Pursue.** Opens a confirmation modal: "Start a pursuit for *Youth Mentoring Expansion*? This creates a
   workflow and asks {go/no-go approver role} for a go/no-go decision (HITL-1)." Confirm ->
   `POST /v1/opportunities/{opportunity_id}/pursue` `{ "agency_id": "…" }`.
   - 201 -> toast "Pursuit started" with a link "Open workflow" (`/workflows/{workflow_id}`). The row shows a "Pursuing" chip.
   - 409 `already_pursuing` -> "A pursuit already exists" with a link to the existing workflow.
   - 403 `forbidden` -> the Pursue button is hidden for users without the role; if it's still hit, show "You don't have permission to start a pursuit."
   - 422 `ineligible` -> "This opportunity is ineligible. Review the eligibility checks before pursuing."
4. **Watch / Skip.** `PUT .../matrix/{opportunity_id}/disposition` `{ "disposition": "watch" | "skip", "reason": "optional text" }`.
   Optimistic: the chip updates immediately, with an "Undo" toast for 8 s (undo sends `"disposition": "none"`).
   Skip asks for an optional reason (select: "Not a mission fit", "Too much effort", "Deadline too soon", "Other").
5. **Evidence popover.** `[ev]` opens the snippets; "View in document" opens SC04 at that evidence span.
6. **Refresh.** Refetches the matrix. While a re-score is in progress, the header shows "Re-scoring…" with a spinner (reduced-motion: a static icon).
7. **Keyboard.** `/` focuses search, ↑/↓ moves between rows, Enter opens the drawer, Esc closes it, `p` pursues from the drawer (after the confirmation modal).

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading (first load) | Summary strip skeleton + 8 skeleton rows |
| Empty: no opportunities yet | "No opportunities yet. Hope checks Grants.gov every morning; new matches will appear here." + button "Check sources" (link to SC17 schedules, admins only) |
| Empty: profile incomplete | "Hope needs more about your agency to score opportunities." + "Complete your profile (63%)" -> SC09 |
| Filtered to empty | "No opportunities match these filters." + "Clear filters" |
| Error (network / 5xx) | Inline banner "We couldn't load the matrix. Try again." + Retry; keep showing the last rows if there are any |
| Stale scores (`generated_at` > 24 h) | Amber banner "Scores were last updated {time}. Refresh to re-score." |
| Drawer evidence error | "Evidence couldn't be loaded." + Retry, inside the drawer only |
| Permission (no Pursue role) | Pursue button not rendered; helper text "Ask a program director to start a pursuit." |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount, filter change, page change | `GET /v1/agencies/{agency_id}/matrix?…` | all `MatrixRow` fields, `generated_at`, `total`, `hidden_ineligible` | Keep previous page while loading; refetch on window focus if older than 5 min |
| Rows rendered | `GET /v1/opportunities?ids=…` (batch, S03) | title, funder, funding, deadlines | Cached per id for the session |
| Drawer open | `GET /v1/agencies/{agency_id}/matrix/{opportunity_id}/explanation` | `dimensions[]`, `eligibility.rules[]` | Cached per row until `generated_at` changes |
| Pursue | `POST /v1/opportunities/{opportunity_id}/pursue` | `workflow_id` | Invalidates the matrix row and the workflow list |
| Watch / Skip | `PUT /v1/agencies/{agency_id}/matrix/{opportunity_id}/disposition` | `disposition` | Optimistic, rolled back on error |
| App shell | `GET /v1/me` | `agency_id`, `roles` | Session |

`agency_id` always comes from `GET /v1/me` (single tenant, one agency).

## 9. Responsive behaviour

- >= 1280 px: all columns. The drawer overlays the right side, and the table stays visible.
- 1024-1279 px: the Drivers column shows one combined bar (the composite), with the five bars in the drawer.
- 641-1023 px: Award and Due merge into one column; Fit becomes an icon next to the title.
- <= 640 px: the card list described in section 3, with a bottom-sheet filter and a full-screen drawer.

## 10. Accessibility

- The table is a real `<table>` with `<th scope="col">`; each row is focusable (`tabindex=0`), with `aria-selected` while its drawer is open.
- Recommendation, eligibility, capacity and deadline urgency each use an icon and text, never colour alone.
- The drawer is `role="dialog"` with `aria-labelledby` set to the title; focus moves into it on open and returns to the row on close.
- Result counts and "Re-scoring…" are announced via an `aria-live="polite"` region.
- Neumorphic shadows aren't the only boundary cue: every card and input also has a 1 px border with at least 3:1 contrast.
- With `prefers-reduced-motion`, the drawer appears without sliding and spinners become static icons.

## 11. Fixture data

`api/matrix/fixture.ts` provides: 12 rows covering all four recommendations, all three
eligibility values, all capacity values, one deadline in 3 days (red), one in 10 days
(amber), one rolling, one row with no explanation, one with 5 risks; a "stale" matrix
(`generated_at` 2 days ago); an empty matrix; and an explanation fixture per row with 1-3
evidence snippets per dimension.

## 12. Analytics and success measures

Events: `matrix_viewed {count, filters}`, `matrix_row_opened {opportunity_id, rank}`,
`matrix_pursue_started {opportunity_id, rank, score}`, `matrix_disposition_set {disposition, reason}`.
Success: median time from first view to Pursue or Skip on a new top-5 row is under 2 days, and
over 70% of pursued opportunities come from the top 10 ranks.

## 13. Acceptance criteria

- [ ] AC1 Rows render in rank order with recommendation (icon + text), score, title, funder line, award, days left and five driver bars.
- [ ] AC2 Ineligible rows are hidden by default, and the footer shows the hidden count with a working "Show them" link.
- [ ] AC3 Filters, search and sort are reflected in the URL and restored on reload.
- [ ] AC4 Deadline urgency: <= 7 days shows the red "!" style, <= 14 days amber, no deadline shows "Rolling".
- [ ] AC5 Opening a row shows the drawer with the explanation, score breakdown, eligibility checks, effort/value, capacity, risks and programs; evidence loads from the explanation endpoint.
- [ ] AC6 Pursue shows the confirmation, calls the pursue endpoint, and on 201 shows the toast with a link to the workflow; 409 `already_pursuing` links to the existing workflow.
- [ ] AC7 Users without a pursue role don't see the Pursue button.
- [ ] AC8 Watch/Skip are optimistic, offer Undo for 8 s, and roll back on error.
- [ ] AC9 Every state in section 7 renders with the exact copy.
- [ ] AC10 Keyboard: `/`, ↑/↓, Enter and Esc work, and focus returns to the row when the drawer closes.
- [ ] AC11 The mobile layout (<= 640 px) shows cards, a filter sheet and a full-screen drawer.
- [ ] AC12 axe finds no violations in the default, drawer-open and empty states.

## 14. Test plan

| AC | Test |
|---|---|
| AC1, AC4 | `features/matrix/MatrixScreen.test.tsx::renders ranked rows with urgency` |
| AC2 | `MatrixScreen.test.tsx::hides ineligible by default` |
| AC3 | `MatrixScreen.test.tsx::syncs filters with url` |
| AC5 | `OpportunityDrawer.test.tsx::shows breakdown and evidence` |
| AC6 | `OpportunityDrawer.test.tsx::pursue success and already_pursuing` |
| AC7 | `OpportunityDrawer.test.tsx::hides pursue without role` |
| AC8 | `MatrixScreen.test.tsx::disposition optimistic with undo and rollback` |
| AC9 | `MatrixScreen.test.tsx::state copy` (one case per state) |
| AC10 | `MatrixScreen.test.tsx::keyboard navigation` |
| AC11 | `MatrixScreen.test.tsx::mobile layout` (matchMedia mock) |
| AC12 | `MatrixScreen.a11y.test.tsx` (vitest-axe) |

## 15. Open questions

- Should Skip require a reason? Recommended default: optional, but asked every time, because the reasons feed the win-probability model later (S23).
- Should rank be personal (re-ordered by the user's dispositions)? Recommended default: no for the MVP; rank is Hope's order.
