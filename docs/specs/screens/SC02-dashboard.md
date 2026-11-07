# SC02: Home dashboard

> **Out of scope for the hackathon. Don't build this.** This screen belongs to the earlier design. Hackathon agents build only the H0-H5 screens (SC00, SC01, SC09, SC11, SC24-SC28); see [`README.md`](../README.md).

| | |
|---|---|
| Route | `/` (no query parameters) |
| Feature folder | `apps/web/src/features/dashboard/` |
| Built by | M7 (replaces today's `app/page.tsx` redirect to `/matrix`) |
| Primary users | Development director (daily, first thing), executive director (a few times a week), approvers in any role (when notified) |
| Can act | No actions on this screen. It only navigates. Everything is visible to any signed-in user; "My approvals" is filtered by the user's roles on the server |
| Status | Draft |

## 1. Purpose and user goals

The dashboard is where every visit starts. In one screen it tells the team where things
stand and what needs them today. Users arrive by opening the app, from the logo, or after
the demo role switcher changes the user's roles (M0).

Within 5 seconds the screen must answer:
1. **What needs me right now?** My pending approvals, with how long I have.
2. **What's due soon?** The next internal deadlines of active pursuits.
3. **What should we look at next?** The top 5 recommendations not yet pursued.

The pipeline counts give a fourth glance: how much is at each stage.

**Primary action:** open the most urgent approval (the first row of "My approvals").
**Secondary actions:** open a recommendation (SC03 drawer), open a deadline's workflow
(SC08), jump to a pipeline stage (SC07 filtered by state), and "View all".

## 2. Information hierarchy

1. **My approvals.** Top left, the first thing people read. Only items the user can act on,
   sorted by due time, because a missed approval is the most expensive mistake.
2. **Upcoming deadlines.** Top right. Days left is the big number.
3. **Top recommendations.** The middle band. Each one has the recommendation badge, score,
   amount and due date.
4. **Pipeline.** A strip of 7 stage tiles along the top (above the lists, but visually
   quiet). "Closed" is a small link, not a tile.

Hidden behind a click:
- each list's full contents ("View all")
- the per-state breakdown inside a stage (a tooltip or popover on the tile)
- recommendation explanations (SC03)

The dashboard stays a summary, so it loads fast and isn't a second matrix.

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ Good afternoon, Dana                                        Riverbend Youth Alliance          │  <- PageHeader
│ Updated just now  [↻]                                                                        │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌Discover┐ ┌Go/no-go┐ ┌ Plan ┐ ┌ Write ┐ ┌Submit┐ ┌Submitted┐ ┌Outcome┐      7 closed ›       │  <- pipeline strip
│ │   31   │ │   2 !  │ │  1   │ │   2   │ │  1 ! │ │    3    │ │   1   │                       │     (Card raised tiles)
│ └────────┘ └────────┘ └──────┘ └───────┘ └──────┘ └─────────┘ └───────┘                       │
├───────────────────────────────────────────────┬──────────────────────────────────────────────┤
│ My approvals (1)                    View all ›│ Upcoming deadlines                 View all ›│
│ 🛡 HITL-5 Submission authorization            │  28  Youth Mentoring Expansion               │
│   Youth Mentoring Expansion                   │ days Awaiting submission auth · Dec 5        │
│   Due in 27 days · Dec 4, 12:00 PM   [Open ›] │  41  Community Food Access                   │
│                                               │ days Drafting · Dec 18                       │
│ (empty: "You're all caught up.")              │   ! 2 Rural Health Outreach  (overdue: red)  │
├───────────────────────────────────────────────┴──────────────────────────────────────────────┤
│ Top recommendations                                              9 recommended · Open matrix ›│
│ ● Pursue 87  Youth Mentoring Expansion · OJJDP · up to $250,000 · due in 31 days     [Open ›] │
│ ● Pursue 81  After-School STEM Pathways · NSF · up to $400,000 · due in 45 days      [Open ›] │
│ ◐ Consider 72 Community Food Access · USDA NIFA · up to $100,000 · due in 41 days    [Open ›] │
│ …                                                                                             │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

Mobile (<= 640 px):
- Order: My approvals, Upcoming deadlines, Top recommendations, Pipeline. On a phone the
  action items come first.
- The pipeline becomes a horizontally scrolling row of compact tiles.
- Each list shows 3 rows, plus "View all".

## 4. Content inventory

All data comes from `GET /v1/dashboard` unless noted.

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Greeting | `GET /v1/me` -> `display_name` (first word); local time | "Good morning/afternoon/evening, Dana" | morning before 12:00, afternoon before 18:00, evening after |
| Agency | `agency_name` | "Riverbend Youth Alliance" | |
| Updated | `generated_at` | "Updated just now", "Updated 4 min ago" | Refreshes on focus and every 60 s |
| Stage tile | `pipeline[].label`, `count` | "Write 2" | 7 tiles in server order; `closed` is a text link "7 closed ›". A tile with `count` 0 is shown greyed with "0", not hidden. `decide` and `submit` tiles show "!" + "needs approval" when > 0, because those stages wait on a person |
| Stage breakdown | `pipeline[].states` | Tooltip/popover "Drafting 1 · In review 0 · Awaiting compliance 0 · Awaiting exec approval 1" | State names via `humanizeState()` (`lib/lifecycle.ts`) |
| Approval row | `my_approvals[]`: `gate`, `summary`, `opportunity_title`, `due_at`, `requested_at` | "🛡 HITL-5 Submission authorization" / title / "Due in 27 days · Dec 4, 12:00 PM" | Gate title from `GATES` (`lib/gates.ts`). Due urgency via `countdown()`: overdue red "Overdue by 2 h", 24 h or less red, 72 h or less amber. "No due date" in grey if null |
| Approval count | `my_approvals_total` | "My approvals (1)" | "View all ›" shows when the total is over 5 |
| Approval link | `gate`, `package_id`, `request_id` | HITL-5 -> `/packages/{package_id}`; every other gate -> `/approvals/{request_id}` | If HITL-5 has no `package_id`, fall back to `/approvals/{request_id}` |
| Deadline row | `upcoming_deadlines[]`: `days_left`, `title`, `state`, `internal_deadline`, `application_due` | Big number "28" + "days", title, "Awaiting submission auth · Dec 5" | `days_left < 0`: "! Overdue {n} days" in red. 0 days: "Today". 3 days or less: red with "!". 7 or less: amber. Tooltip: "Internal deadline Dec 5 · funder deadline Dec 8" |
| Deadline link | `workflow_id` | -> `/workflows/{workflow_id}` | |
| Recommendation row | `top_recommendations[]`: `recommendation`, `composite_score`, `title`, `funder_name`, `award_ceiling`, `application_due` | "● Pursue 87 · Youth Mentoring Expansion · OJJDP · up to $250,000 · due in 31 days" | Badge styles from `RECOMMENDATION` (`features/status.tsx`) with icon + text. Score is an integer, rounded half-up. The award uses `formatMoney(…, {compact: false})` with "up to", or "Amount not stated". Due as in the matrix |
| Recommendation link | `opportunity_id` | -> `/matrix?selected={opportunity_id}` (opens the SC03 drawer) | |
| Recommendation total | `top_recommendations_total` | "9 recommended · Open matrix ›" | -> `/matrix?rec=pursue` |
| Stage link | `pipeline[].stage` | `/workflows?stage={stage}` | For `discover`, -> `/matrix` instead, because those opportunities have no workflow yet |

## 5. Components

- Header: `PageHeader`, with a refresh `Button` (ghost, `aria-label="Refresh dashboard"`).
- Pipeline strip: 7 tiles, each an `<a>` styled as `Card` (`glass-panel`, `glass-active` on press), with the count, label and an optional "!" `Badge` (tone warn).
- Lists: `Card` (`glass-panel`) with a heading and "View all" link, holding a `<ul>` of rows. Each row is one link (the whole row is clickable) with a visible "Open ›" affordance.
- Badges: `RecommendationBadge` (`features/status.tsx`), `GateBadge`, `UrgencyBadge`.
- States: `Loading`, `EmptyState`, `ErrorNotice` from `States.tsx`.
- No new shared primitives.

## 6. Interactions

1. **Mount.** `GET /v1/dashboard` and `GET /v1/me` (the session is usually cached already).
2. **Refresh.** The button, window focus (if the data is over 60 s old) and a 60 s interval
   (paused while the tab is hidden) all refetch. While refreshing, the old data stays and
   "Updated…" changes to "Refreshing…".
3. **Open an approval.** Click a row, or press Enter on it. This navigates to SC22
   (HITL-5) or SC06.
4. **Open a deadline.** Navigates to SC08.
5. **Open a recommendation.** Navigates to `/matrix?selected={id}`.
6. **Stage tile.** Navigates as described in section 4. `/workflows?stage=` is a query SC07
   (M4) has to accept. See open questions.
7. **Role switch** (M0 user menu). When the roles change, the page refetches, because "My
   approvals" depends on the roles.
8. **Keyboard.** Tab moves through the tiles, then approvals, deadlines and recommendations.
   `r` refreshes when focus isn't in an input. No other shortcuts.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading (first load) | 7 tile skeletons and 3 list cards with 3 row skeletons each, plus `role="status"` "Loading your dashboard…" |
| Approvals empty | "You're all caught up. Nothing is waiting for your approval." (check icon) |
| Deadlines empty | "No deadlines in the next 30 days." + link "See all workflows" |
| Recommendations empty, with opportunities in the pipeline | "No new recommendations right now. Everything recommended is already being pursued or was skipped." + "Open matrix" |
| Brand-new agency (every count 0) | One card replaces the lists: "Welcome to Hope. Start by completing your agency profile so Hope can find and rank grants for you." + "Complete your profile" (-> `/profile`) + "See opportunities" (-> `/matrix`) |
| Error (network / 5xx) | `ErrorNotice` "We couldn't load your dashboard." + Retry. If there was data before, it stays, with the banner "Showing data from {time}." |
| Partial data | Never happens. The endpoint is all-or-nothing, so each list has no error of its own |
| Overdue approval | Row in red with "! Overdue by {duration}" |
| Offline | Banner "You're offline. Showing data from {time}." Refresh is disabled |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount, refresh, interval, role switch | `GET /v1/dashboard` | `agency_name`, `generated_at`, `pipeline[]` (`stage`, `label`, `count`, `states`), `top_recommendations[]` (+ `_total`), `my_approvals[]` (+ `_total`, `package_id`), `upcoming_deadlines[]` | Keep the previous data while loading. Interval 60 s, paused when hidden |
| App shell | `GET /v1/me` | `display_name`, `roles` | Session |

Every field above is in the M7 `GET /v1/dashboard` response. The screen makes no other calls.

## 9. Responsive behaviour

- >= 1280 px: the pipeline strip in one row; approvals and deadlines side by side (1:1); recommendations full width with up to 5 rows.
- 1024-1279 px: the same, with recommendations dropping the funder name (it moves to a tooltip).
- 641-1023 px: pipeline tiles wrap to 2 rows (4 + 3); approvals and deadlines stack; lists keep 5 rows.
- <= 640 px: the order from section 3 (approvals, deadlines, recommendations, pipeline), 3 rows per list, and a horizontal scroll strip with snap points for the pipeline.

## 10. Accessibility

- Landmarks: one `<h1>` (the greeting). Each card is a `<section aria-labelledby>` with an
  `<h2>`. The pipeline is a `<nav aria-label="Pipeline stages">` containing a list of links.
- Each tile's accessible name is "Write: 2 opportunities", and "Go / no-go: 2 opportunities,
  needs approval" when it shows "!". The "!" is text, not only colour.
- List rows are single links whose accessible name includes the urgency, for example
  "HITL-5 Submission authorization, Youth Mentoring Expansion, due in 27 days".
- "Updated…" is in an `aria-live="polite"` region, but refreshes caused by the interval
  aren't announced (only manual refreshes are), to avoid noise.
- Contrast is AA, and every tile and card has a 1 px border with at least 3:1 contrast.
- With `prefers-reduced-motion`: no skeleton shimmer and no count animations.

## 11. Fixture data

`apps/web/src/api/dashboard/fixture.ts` exports `FixtureDashboardApi`, with dates relative
to `FIXED_NOW`:

1. **default**:
   - the pipeline from the M7 example (31/2/1/2/1/3/1, closed 7)
   - 5 of 9 recommendations (pursue 87, pursue 81, consider 72, consider 68, pursue 66), one
     of them with no award ceiling
   - 1 approval (HITL-5 with a `package_id`, due in 27 days)
   - 3 deadlines (28 days, 41 days, and one overdue by 2 days)
2. **approver-heavy** (the default when the session roles include `finance_director` and `executive_director`): 7 approvals (total 7, 5 shown). Covers HITL-1, HITL-2 overdue by 3 h, HITL-4 due in 20 h (red), HITL-4 due in 60 h (amber), and one with no due date.
3. **caught-up**: no approvals and no deadlines.
4. **new-agency**: every count 0 and every list empty.
5. **error**: `getDashboard()` rejects with a 500 `ApiError`.

`FixtureDashboardApi` picks the case from the session roles, or from the constructor
option `{ scenario }`. The demo switcher therefore changes "My approvals" with no backend.

## 12. Analytics and success measures

Events:
- `dashboard_viewed {approvals, deadlines, recommendations}`
- `dashboard_approval_opened {gate, overdue: bool}`
- `dashboard_deadline_opened {days_left}`
- `dashboard_recommendation_opened {rank, score}`
- `dashboard_stage_opened {stage}`

Success:
- over 60% of sessions that start on the dashboard reach an approval or a workflow within 2 clicks
- the median time from an approval request being created to its first open from the dashboard is under 4 h
- the dashboard loads (p95) in under 1 s on the demo dataset

## 13. Acceptance criteria

- [ ] AC1 The greeting, agency name and "Updated" time render from `/v1/me` and `generated_at`.
- [ ] AC2 Seven pipeline tiles render in server order with their counts. Zero counts are greyed, not hidden. Decide and submit show "!" when they're over 0. "Closed" is a link. Each tile links to the documented route.
- [ ] AC3 "My approvals" shows up to 5 rows sorted as served, with gate title, opportunity, due urgency (overdue, 24 h or less, 72 h or less). HITL-5 links to `/packages/{package_id}` and the others to `/approvals/{request_id}`. "View all" appears when the total is over 5.
- [ ] AC4 "Upcoming deadlines" shows days left with overdue / today / 3-day / 7-day styling and links to the workflow.
- [ ] AC5 "Top recommendations" shows badge (icon + text), score, title, funder, award ("Amount not stated" when missing) and due date, and links to `/matrix?selected=`.
- [ ] AC6 Each empty state and the brand-new-agency card render with the exact copy.
- [ ] AC7 The error state keeps the last data and shows the "Showing data from" banner.
- [ ] AC8 Refresh runs every 60 s, on focus and on the button, and after a role switch. Interval refreshes aren't announced.
- [ ] AC9 The mobile layout (<= 640 px) puts approvals first, shows 3 rows per list and a scrolling pipeline strip.
- [ ] AC10 axe finds no violations in the default, caught-up and new-agency states.
- [ ] AC11 `app/page.tsx` renders the dashboard instead of redirecting to `/matrix`.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `features/dashboard/Dashboard.test.tsx::greeting and updated time` |
| AC2 | `Dashboard.test.tsx::pipeline tiles counts and links` |
| AC3 | `Dashboard.test.tsx::my approvals urgency and links` (approver-heavy fixture) |
| AC4 | `Dashboard.test.tsx::deadlines styling and links` |
| AC5 | `Dashboard.test.tsx::top recommendations rows` |
| AC6 | `Dashboard.test.tsx::empty states copy` (caught-up, new-agency) |
| AC7 | `Dashboard.test.tsx::error keeps last data` |
| AC8 | `Dashboard.test.tsx::refresh interval focus and role switch` (fake timers) |
| AC9 | `Dashboard.test.tsx::mobile order` (matchMedia mock) |
| AC10 | `features/dashboard/Dashboard.a11y.test.tsx` (vitest-axe) |
| AC11 | `apps/web/src/app/page.test.tsx::renders dashboard` |
| contract | `apps/web/src/api/dashboard/http.test.ts::matches openapi snapshot` |

## 15. Open questions

- **Should SC07 accept a `stage` filter?** Recommended default: yes. M4 accepts
  `/workflows?stage=` with the stage-to-state map from M7 (listed in M7's requests). Until
  then, tiles link to `/workflows` with no filter.
- **Should the dashboard show money totals ("$1.2M in the pipeline")?** Recommended default:
  not in the MVP. They're easy to misread before budgets exist.
- **Should "My approvals" include items for roles the user has but isn't the named approver
  for?** Recommended default: yes, with role-based matching (the server rule). There are no
  named assignees in the MVP.
- **Should there be a nav badge with the approvals count?** Recommended default: yes, later.
  It needs a `nav.ts` badge hook from M0, so it's not part of this spec.
