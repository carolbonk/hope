# SC07: Workflows

| | |
|---|---|
| Route | `/workflows` (query: `status` = `active` \| `waiting` \| `finished` \| `all`, default `active`) |
| Feature folder | `apps/web/src/features/workflow/` |
| Built by | M4 (replaces today's `WorkflowList` in `WorkflowScreen.tsx`) |
| Primary users | Development director (daily, "what's stuck?"), executive director and finance director (when asked to approve) |
| Can act | Read: every role. The only actions are navigation (open a workflow, open an approval). Pursue happens on SC03 |
| Status | Draft |

## 1. Purpose and user goals

The workflows list is the pipeline view: every opportunity the agency is pursuing and where it
is. Users arrive from the nav, from the "Pursuit started" toast on SC03 ("Open workflow" goes to
SC08, "All workflows" comes here), and from the dashboard (M7).

Within 5 seconds the screen must answer:
1. What is waiting on a human, and on whom? (open gate + approver role + time left)
2. What is Hope working on right now? (busy rows)
3. Which pursuits are closest to their internal deadline?

**Primary action:** open the workflow (SC08) or, for a row waiting on me, open the approval.
**Secondary actions:** switch the status filter.

## 2. Information hierarchy

1. **Waiting-on-a-human rows first** (sorted by gate due time), because those are the only rows a
   user can unblock. The "Waiting on" cell is the most prominent cell in the row.
2. **Title and state.** What the grant is and the lifecycle step, in plain words ("Budget sign-off").
3. **Deadline urgency** as days left to the internal deadline.
4. **Busy indicator** ("Hope is drafting…") so users don't think a row is stuck.

Hidden behind a click (SC08): the transition history, the deadline plan, artifacts. Finished
pursuits are hidden by default (filter "Active") because the list is for work in progress; a count
shows how many are finished.

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Workflows                                                       Updated just now  [↻]      │  <- PageHeader
│ 3 active · 2 waiting on approval · 3 finished                                              │  <- summary strip (Card raised)
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ Show: ( Active 3 | Waiting on approval 2 | Finished 3 | All 6 )                            │  <- Segmented (Card inset)
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ Opportunity                          │ Step                 │ Waiting on              │ Internal deadline │ Updated │
│ Rural Health Care Services Outreach  │ ◆ Budget sign-off    │ 🛡 HITL-2 · Finance     │ ⏱ 24 days         │ 3 min ago│
│ Health Resources and Services Admin. │                      │ director · 2d 23h left  │ Dec 1             │          │
│                                      │                      │ [Review →]              │                   │          │
│ Project AWARE                        │ ◆ Go / No-Go         │ 🛡 HITL-1 · Development │ ⚠ 6 days          │ 1 h ago  │
│ SAMHSA                               │                      │ director · 4h left      │ Nov 13            │          │
│ Youth Mentoring Expansion            │ ⟳ Drafting           │ Hope is drafting the    │ ⏱ 40 days         │ 20 s ago │
│ DOJ · OJJDP                          │                      │ narrative…              │ Dec 17            │          │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ 3 finished pursuits hidden · Show them                                                     │  <- footer
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

Mobile (<= 640 px): each row is a card; the segmented control scrolls horizontally.

```text
┌──────────────────────────────────┐
│ Workflows                    [↻] │
│ 3 active · 2 waiting · 3 done    │
│ (Active|Waiting|Finished|All) →  │
├──────────────────────────────────┤
│ Rural Health Care Services Out…  │
│ HRSA                             │
│ ◆ Budget sign-off   ⏱ 24 days    │
│ 🛡 Waiting on Finance director   │
│   2d 23h left      [Review →]    │
├──────────────────────────────────┤
│ Youth Mentoring Expansion        │
│ ⟳ Hope is drafting the narrative │
└──────────────────────────────────┘
```

## 4. Content inventory

| Element | Source (endpoint + JSON field) | Format and example | Rules |
|---|---|---|---|
| Summary counts | `GET /v1/workflows` -> `counts.active`, `counts.waiting`, `counts.finished` | "3 active · 2 waiting on approval · 3 finished" | Each count is a button that sets the filter. Counts don't depend on the current filter |
| Updated | client time of the last successful fetch | "Updated just now" / "Updated 2 min ago" | Live via `useNow(30_000)` |
| Title | `items[].title` | "Rural Health Care Services Outreach Program" | One line, ellipsis after 56 characters, full title in `title` attribute. Links to `/workflows/{workflow_id}` |
| Funder | `items[].funder_name` | "Health Resources and Services Administration" | Secondary text, one line, ellipsis |
| Step | `items[].state` | "Budget sign-off" | Label map below; icon: ◆ waiting state, ⟳ busy, ✓ `Submitted`, ✕ `Declined`/`Ineligible`/`Archived`/`Discarded`, ⏱ `Expired`. Label from `STEP_LABEL` (not `humanizeState`) |
| Waiting on | `items[].open_gate.gate`, `.approver_roles[]`, `.due_at` | "HITL-2 · Finance director · 2d 23h left" | Roles via `roleLabel`, joined with " or ". Countdown via `countdown(due_at, now)`; `overdue` -> red "!" + "3h overdue". If the user has one of the roles, show the `[Review →]` button to `/approvals/{request_id}` |
| Busy text | `items[].busy` + `state` | "Hope is drafting the narrative…" | Text per state below; shown when `busy` is true; reduced-motion: static ⟳ |
| Finished text | `state` terminal or `Submitted` | "Submitted" / "Declined at go/no-go" / "Not eligible" / "Expired" | Grey text, no countdown |
| Internal deadline | `items[].internal_deadline` (falls back to `application_due` with "(funder)" suffix) | "24 days" with "Dec 1" below | `countdown(..., {urgentMs: 3 d, soonMs: 10 d})`: red <= 3 d, amber <= 10 d; "No deadline" when both are null; hidden for finished rows |
| Updated | `items[].updated_at` | "3 min ago" | Relative; full local time in the tooltip |
| Hidden count | `counts.finished` when filter is `active` | "3 finished pursuits hidden · Show them" | Hidden when 0 |

`STEP_LABEL`: Normalized "Checking eligibility", NeedsEligibilityReview "Eligibility review",
Screened "Scoring", Recommended "Recommended", AwaitingGoNoGo "Go / No-Go", Planning "Building the
budget", AwaitingBudgetSignoff "Budget sign-off", Drafting "Drafting the narrative", InReview
"Checking the draft", AwaitingCompliance "Compliance check", AwaitingExecApproval "Executive
approval", Packaging "Building the package", AwaitingSubmissionAuth "Submission authorization",
Submitted "Submitted", Declined "Declined at go/no-go", Ineligible "Not eligible", Archived
"Archived", Expired "Expired", others `humanizeState`.

Busy text per state: Normalized "Hope is checking eligibility…", Screened "Hope is scoring the fit…",
Planning "Hope is building the budget…", Drafting "Hope is drafting the narrative…", InReview "Hope
is checking the draft…", AwaitingCompliance "Hope is checking required sections…", Packaging "Hope
is building the package…", AwaitingSubmissionAuth (gate decided, waiting for Mark submitted)
"Ready to submit. Mark it submitted on the package page." with a link to `/packages/{package_id}`
(from SC08's detail; on the list, the text only).

## 5. Components

- Page header: `PageHeader` with a refresh `Button` (`neutral`, icon only, `aria-label="Refresh"`).
- Summary strip: `Card` (`glass-panel`) with count `Button`s styled as links.
- Filter: `Segmented` (`components/ui/Field.tsx`), active segment `glass-active`.
- Table: `Table`, `Th`, `Tr`, `Td`; the title cell holds the only row link; `[Review →]` is a `Button`
  rendered as a `Link`.
- Badges: `GateBadge` (`features/status.tsx`) in the Waiting-on cell, `UrgencyBadge` for countdowns,
  `Badge` for the step (tone `info` waiting, `neutral` busy, `good` submitted, `bad` declined/ineligible,
  `warn` expired).
- States: `Loading`, `EmptyState`, `ErrorNotice`.
- No new shared primitives.

## 6. Interactions

1. **Load.** `GET /v1/workflows?status={status}` on mount and when `status` changes. The URL keeps
   the filter (`/workflows?status=waiting`); an unknown value falls back to `active`. The previous rows
   stay visible (opacity 60%) while loading.
2. **Auto-refresh.** Every 15 s while the tab is visible, and on window focus; paused when hidden
   (`document.visibilityState`). If any row is `busy`, every 5 s instead.
3. **Filter.** Click a segment or a summary count -> updates `?status=` (history `replace`) and refetches.
4. **Open workflow.** Click the title (or Enter on it) -> `/workflows/{encodeURIComponent(workflow_id)}`.
5. **Review.** `[Review →]` -> `/approvals/{request_id}` (M3's SC06). Only rendered when
   `session.roles` (from `GET /v1/me`) intersects `open_gate.approver_roles`; otherwise the cell reads
   "Waiting on Finance director".
6. **Refresh.** The header button refetches immediately.
7. **Keyboard.** Tab order: refresh, segments (arrow keys move between them), then each row's title
   link and Review button. `r` refreshes when focus isn't in an input.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading (first load) | Summary strip skeleton (3 grey pills) + 5 skeleton rows; `Loading` label "Loading workflows…" for screen readers |
| Empty: no pursuits yet (`counts` all 0) | "No pursuits yet. Pick an opportunity on the matrix and choose Pursue to start one." + button "Open the matrix" -> `/matrix` |
| Filtered to empty: waiting | "Nothing is waiting on an approval right now." + "Show all active" |
| Filtered to empty: active (but finished > 0) | "No active pursuits. {n} finished pursuits are hidden." + "Show them" |
| Filtered to empty: finished | "No finished pursuits yet." |
| Error (network / 5xx) | `ErrorNotice` title "Could not load workflows", body "Check that the Hope API is running, then reload." + Reload. Keep the last rows if any, with the banner above them |
| Error `validation_error` | Reset the filter to `active` silently and refetch |
| Offline (`navigator.onLine` false) | Amber banner "You're offline. Showing the last loaded list." Auto-refresh pauses |
| Permission | None: every role can read. Review buttons follow interaction 5 |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount, filter change, refresh, poll | `GET /v1/workflows?status=…` | `items[]` (all fields), `counts` | No cache beyond component state; poll 15 s (5 s if any `busy`), on focus |
| App shell | `GET /v1/me` (M0 session) | `roles` | Session |

Client: `apps/web/src/api/workflow/` exports `listWorkflows({status})`, `getWorkflow(id)`,
`getHistory(id)`, `pursue(opportunityId)` (types in `types.ts`, HTTP in `http.ts`, fixture in
`fixture.ts`).

## 9. Responsive behaviour

- >= 1280 px: all five columns.
- 1024-1279 px: "Updated" moves under the title as secondary text.
- 641-1023 px: "Internal deadline" merges into the Step cell ("Budget sign-off · 24 days").
- <= 640 px: cards as in section 3; Review button full width at the bottom of the card.

## 10. Accessibility

- A real `<table>` with `<caption class="sr-only">Workflows</caption>` and `<th scope="col">`.
- Step, urgency and gate use icon + text, never colour alone; countdowns have `aria-label`
  "Internal deadline in 24 days, December 1".
- The summary counts and "Updated …" are in an `aria-live="polite"` region; polling updates don't move focus.
- The segmented control is a `radiogroup` with `aria-checked`.
- Busy spinners respect `prefers-reduced-motion` (static icon).
- Borders at 3:1 contrast in addition to liquid-glass shadows.

## 11. Fixture data

`api/workflow/fixture.ts` (extends today's `buildWorkflows`): 6 workflows:
1. `AwaitingGoNoGo`, HITL-1 due in 4 h (urgent), roles development/executive director.
2. `AwaitingBudgetSignoff`, HITL-2 due in 70 h, role finance_director.
3. `Drafting`, `busy: true`, internal deadline in 40 days.
4. `AwaitingExecApproval`, HITL-4 overdue by 3 h.
5. `Submitted` (finished), confirmation set.
6. `Declined` (finished).
Plus: an empty list (`counts` 0), a list where `waiting` is empty, and an error mode
(`new FixtureApi({ fail: "listWorkflows" })`).

## 12. Analytics and success measures

No analytics pipeline in the MVP; events are named for later: `workflows_viewed {status, count}`,
`workflow_opened {workflow_id, state}`, `workflow_review_clicked {gate}`.
Success: in the demo, a presenter can find the row waiting on them and open it in one click.

## 13. Acceptance criteria

- [ ] AC1 Rows render with title, funder, step label + icon, waiting-on (gate, role, countdown) or busy text, internal deadline countdown and updated time, in the specified order.
- [ ] AC2 The default filter is Active; finished pursuits are hidden with a working "Show them" footer; `?status=` round-trips through the URL and an unknown value falls back to `active`.
- [ ] AC3 Summary counts render from `counts` and act as filters.
- [ ] AC4 The Review button appears only when the session has an approver role for the open gate and links to `/approvals/{request_id}`.
- [ ] AC5 Countdown colours: overdue red with "overdue", <= 3 days red, <= 10 days amber; "No deadline" when null.
- [ ] AC6 Polling runs every 15 s (5 s when a row is busy), pauses when the tab is hidden, and refetches on focus.
- [ ] AC7 Every state in section 7 renders with the exact copy.
- [ ] AC8 The mobile layout (<= 640 px) renders cards.
- [ ] AC9 axe finds no violations in the default, empty and error states.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `apps/web/src/features/workflow/WorkflowList.test.tsx::renders rows with step, waiting on and deadline` |
| AC2 | `WorkflowList.test.tsx::filters by status and syncs url` |
| AC3 | `WorkflowList.test.tsx::summary counts filter` |
| AC4 | `WorkflowList.test.tsx::review button only for approver roles` |
| AC5 | `WorkflowList.test.tsx::deadline urgency` |
| AC6 | `WorkflowList.test.tsx::polls and pauses when hidden` (fake timers) |
| AC7 | `WorkflowList.test.tsx::state copy` (one case per state) |
| AC8 | `WorkflowList.test.tsx::mobile layout` (matchMedia mock) |
| AC9 | `WorkflowList.a11y.test.tsx` (vitest-axe) |

## 15. Open questions

- Should finished pursuits be visible by default? Recommended: no; the footer link is enough.
- Should "Waiting on" show the assignee's name? Recommended: no, roles only (there are no real users in the MVP).
