# SC08: Workflow timeline

> **Out of scope for the hackathon. Don't build this.** This screen belongs to the earlier design. Hackathon agents build only the H0-H5 screens (SC00, SC01, SC09, SC11, SC24-SC28); see [`README.md`](../README.md).

| | |
|---|---|
| Route | `/workflows/[workflowId]` (query: `history` = `all` \| `decisions`, default `all`) |
| Feature folder | `apps/web/src/features/workflow/` |
| Built by | M4 (replaces today's `WorkflowDetail` in `WorkflowScreen.tsx`; keeps and extends `Timeline.tsx`) |
| Primary users | Development director (many times a day during a pursuit), approvers arriving from the list, the demo presenter |
| Can act | Read: every role. Review an open gate: roles in its `approver_roles`. Open budget/draft/package: every role (those screens enforce their own actions) |
| Status | Draft |

## 1. Purpose and user goals

The single page for one pursuit: where it is, what it waits on, what Hope has produced so far,
and the full record of how it got here. Users arrive from SC07, from the "Pursuit started" toast on
SC03, from an approval (SC06 "Back to workflow"), and from a direct link. In the demo this page is
left open while the workflow moves, so it must update by itself.

Within 5 seconds the screen must answer:
1. What is the current step, and is it waiting on a person or on Hope?
2. What do I need to do next, if anything? (one clear call to action)
3. How much time is left before the internal deadline?

**Primary action:** the next-step button (Review the open gate, or open the artifact that was just produced).
**Secondary actions:** open the budget, draft or package; switch the history filter.

## 2. Information hierarchy

1. **Next step card**, top of the page: one sentence and one button. It's the only thing that changes
   what the user does.
2. **Lifecycle stepper**: the visited path and the remaining main path, with the current step raised.
3. **Deadline**: countdown to the internal deadline, and the funder deadline with its timezone.
4. **Artifacts**: links to the budget, the draft and the package, as each one exists.
5. **History**: every transition and decision with actor and time, newest first.
6. **Milestones**: the back-scheduled plan (for planning, not triage), collapsed by default.

Hidden behind a click: gate artifact hashes (copy button in the history item), raw event timeline
(the "All events" toggle), milestone list.

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│ ‹ All workflows                                                                               │
│ Rural Health Care Services Outreach Program                         [◆ Budget sign-off]       │  <- PageHeader + step Badge
│ Health Resources and Services Administration · Pursued by demo on Nov 7                       │
├───────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌ NEXT STEP ────────────────────────────────────────────────────────────────────────────────┐ │
│ │ 🛡 Waiting on Finance director to sign off the budget (HITL-2) · 2d 23h left               │ │  <- Card raised, accent border
│ │ [ Review budget → ]                                     Internal deadline: ⏱ 24 days (Dec 1)│ │
│ └───────────────────────────────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────┬────────────────────────────────────────┤
│ Lifecycle                                            │ Deadline                               │
│  ✓ Checking eligibility        Nov 7, 3:04 PM        │  Internal  Dec 1, 5:00 PM EST  24 days │
│  ✓ Scoring                     Nov 7, 3:04 PM        │  Funder    Dec 4, 5:00 PM EST          │
│  ✓ Recommended                 Nov 7, 3:04 PM        │  Grants.gov buffer: 72 h               │
│  ✓ Go / No-Go (HITL-1)  GO · demo   Nov 7, 3:06 PM   │  ▸ Milestones (6)                      │
│  ✓ Building the budget         Nov 7, 3:07 PM        ├────────────────────────────────────────┤
│  ● Budget sign-off (HITL-2)    CURRENT               │ Artifacts                              │
│  ○ Drafting the narrative                            │  Budget  v1 · $298,500   [Open →]      │
│  ○ Checking the draft                                │  Draft   not started yet               │
│  ○ Compliance check                                  │  Package not started yet               │
│  ○ Executive approval (HITL-4)                       │                                        │
│  ○ Building the package                              │                                        │
│  ○ Submission authorization (HITL-5)                 │                                        │
│  ○ Submitted                                         │                                        │
├──────────────────────────────────────────────────────┴────────────────────────────────────────┤
│ History                                              ( All | Decisions only )                 │
│  Nov 7, 3:07 PM  🛡 Budget sign-off requested from Finance director · due Nov 10              │
│  Nov 7, 3:07 PM  → Building the budget → Budget sign-off · A7 Budget                          │
│  Nov 7, 3:06 PM  ✓ GO by demo (Development director)                                          │
│  …                                                                                             │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

Mobile (<= 640 px): single column in this order: header, Next step (button full width), Deadline
(compact: "24 days left · Dec 1"), Lifecycle (collapsed to the current step plus "Show all 13 steps"),
Artifacts, History.

## 4. Content inventory

| Element | Source (endpoint + JSON field) | Format and example | Rules |
|---|---|---|---|
| Back link | - | "‹ All workflows" | Goes to `/workflows` keeping the last `?status=` from `sessionStorage` |
| Title | `GET /v1/workflows/{id}` -> `title` | "Rural Health Care Services Outreach Program" | Wraps to 2 lines max, then ellipsis |
| Funder + pursued | `funder_name`, `started_by`, `started_at` | "Health Resources and Services Administration · Pursued by demo on Nov 7" | Date via `formatDate` |
| Step badge | `state` | "◆ Budget sign-off" | Same `STEP_LABEL` and icon/tone rules as SC07 |
| Next step text | `state`, `busy`, `gates[]` (open one), `artifacts`, `submission` | See "Next step rules" below | Exactly one sentence and at most one primary button |
| Gate countdown | open gate `due_at` | "2d 23h left" / "3h overdue" | `countdown()`, overdue in red with "!" |
| Stepper | `transitions[]` + `HAPPY_PATH` (MVP path without `AwaitingCompliance` gate label) | ✓ done, ● current, ○ upcoming; time for done steps | Built by `timelineSteps()` from `transitions` (not the fixture-only `history`). Gate decisions shown inline: "GO · demo". Rollbacks show a "↺ Returned to Planning: profile financials changed" row |
| Internal deadline | `internal_deadline`, `deadline_plan.funder_timezone` | "Dec 1, 5:00 PM EST · 24 days" | Time shown in the funder timezone with its abbreviation; countdown thresholds as SC07 |
| Funder deadline | `application_due` | "Dec 4, 5:00 PM EST" | "Rolling" when null |
| Buffer | `deadline_plan.buffer_hours` | "Grants.gov buffer: 72 h" | Hidden when 0 |
| Milestones | `deadline_plan.milestones[]` | "Budget sign-off · Finance director · Nov 17" | Collapsed `<details>`; past milestones aren't returned by the API |
| Budget artifact | `artifacts.framework_id`, `ledger_id` | "Budget v1" + [Open →] `/frameworks/{framework_id}/budget` | "Not started yet" when null. No amount shown here unless M5 adds it (see Open questions) |
| Draft artifact | `artifacts.narrative_hash`, `framework_id` | "Draft ready" + [Open →] `/frameworks/{framework_id}/draft` | "Not started yet" when null; "Drafting…" when `state = Drafting` and busy |
| Package artifact | `artifacts.package_id` | "Package ready" + [Open →] `/packages/{package_id}` | "Not started yet" when null |
| Submission | `submission.submitted_at`, `.submitted_by`, `.confirmation` | "Submitted Nov 8 by demo · Confirmation GRANT1234567" | Replaces the Next step card when present |
| History item: transition | `/history` -> `kind: "transition"`: `from`, `to`, `actor`, `at`, `reason`, `cause` | "→ Building the budget → Budget sign-off · A7 Budget" | Actor labels: `A0` "Hope", `A4` "Eligibility", `A5` "Alignment", `A6` "Recommender", `A7` "Budget", `A9` "Narrative", `A10` "Packaging"; user ids as is. `cause: rollback` uses ↺ and amber |
| History item: gate requested | `kind: "gate_requested"`: `gate`, `approver_roles`, `due_at`, `summary` | "🛡 Budget sign-off requested from Finance director · due Nov 10" | `summary` under it in secondary text, max 2 lines |
| History item: decision | `kind: "gate_decided"`: `decision`, `decided_by`, `role`, `comment` | "✓ GO by demo (Development director)" / "✕ NO-GO by demo: Outside our service area" | Decision labels from `lib/gates.ts` `optionFor()` |
| History item: invalidated | `kind: "approval_invalidated"`: `gate`, `reason` | "⚠ Budget sign-off approval voided: profile financials changed" | Amber |
| Hash copy | `gates[].artifact_hash` | `sha256:3f9a…c21e` | Shown truncated (first 4 + last 4 hex) with a copy button in decision items |

**Next step rules** (first match wins):

| Condition | Text | Button |
|---|---|---|
| `submission` present | "Submitted on {date} by {user}. Confirmation {confirmation}." | none |
| terminal `Declined` | "Declined at go/no-go by {user}: {comment}." | "Back to the matrix" -> `/matrix` |
| terminal `Ineligible` | "Not eligible: {reason}." | "Back to the matrix" |
| terminal `Expired` | "The internal deadline passed before submission." | none |
| open gate, user has an approver role | "Waiting on you: {gate title} ({gate}) · {countdown}" | HITL-2 "Review budget →" `/frameworks/{framework_id}/budget`; HITL-4 "Review draft →" `/approvals/{request_id}`; others "Review →" `/approvals/{request_id}` |
| open gate, user lacks the role | "Waiting on {roles} to {gate verb} ({gate}) · {countdown}" | none; helper "Switch role in the user menu to act as {role}." (demo role switcher) |
| `AwaitingSubmissionAuth`, HITL-5 approved, no submission | "Authorized. Download the package and submit it on the funder's portal, then mark it submitted." | "Open package →" `/packages/{package_id}` |
| `busy` | busy text from SC07 + "This page updates by itself." | none |

Gate verbs: HITL-1 "decide go / no-go", HITL-2 "sign off the budget", HITL-4 "approve the application",
HITL-5 "authorize submission".

## 5. Components

- Header: `PageHeader` (title, description, actions = step `Badge`), back `Link` styled `glass-panel-sm`.
- Next step: `Card` (`glass-panel`) with a 4 px left accent border; `Button` (`primary`) as a `Link`.
- Stepper: existing `Timeline` component (`features/workflow/Timeline.tsx`), extended with an inline
  decision label and rollback rows.
- Deadline and Artifacts: `Card` with a definition list (`<dl>`); milestones in `<details>` inside a `Well`.
- History: `Card` with `Segmented` (All | Decisions only) and an `<ol>`; icons from `Icon`.
- States: `Loading`, `ErrorNotice`, `EmptyState`.
- No new shared primitives.

## 6. Interactions

1. **Load.** On mount, in parallel: `GET /v1/workflows/{id}` and `GET /v1/workflows/{id}/history`.
   The page renders as soon as the first returns; the history card shows its own skeleton.
2. **Live updates.** While the workflow is not terminal and has no `submission`: poll both calls every
   3 s when `busy`, every 10 s otherwise; pause when the tab is hidden; refetch on focus. When `state`
   changes, the stepper animates the new current step (reduced-motion: no animation) and the live region
   announces "Now at Budget sign-off". Polling stops at a terminal state or after `submission`.
3. **Next step button.** Navigates as in the Next step rules. No API calls from this screen.
4. **Artifact links.** Navigate to M5/M6/M7 screens.
5. **History filter.** `( All | Decisions only )` sets `?history=decisions` (history `replace`):
   decisions-only shows `gate_requested`, `gate_decided` and `approval_invalidated`.
6. **Copy hash.** Copies the full `artifact_hash`; toast "Hash copied" (M0 `Toast`).
7. **Keyboard.** Tab order: back link, next-step button, stepper (not focusable, read as a list),
   artifact links, milestones disclosure, history filter, copy buttons. `g` then `w` goes to `/workflows`.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading (first load) | Header skeleton (title bar + badge), a Next step card skeleton, 8 stepper skeleton rows; screen-reader label "Loading workflow…" |
| History loading | 4 skeleton lines inside the History card |
| Not found (`404 not_found`) | `EmptyState`: "We couldn't find this workflow. It may have been started on another Hope instance." + "All workflows" |
| Error (network / 5xx) on detail | `ErrorNotice` "Could not load this workflow" / "Check that the Hope API is running, then reload." + Reload |
| Error on history only | Inside the History card: "History couldn't be loaded." + Retry; the rest of the page stays |
| Polling error | Keep the last data; small amber line under the header "Live updates paused: we couldn't reach Hope. Retrying…"; clears on the next success |
| Empty history (just pursued, nothing projected yet) | "Hope is starting this pursuit. The first steps appear here within a few seconds." |
| Waiting on someone else | Next step text with the role-switch helper (see rules) |
| Offline | Amber banner "You're offline. Live updates are paused." |
| Permission | None for reading; Review buttons follow the rules |
| Stale artifact | Not reachable from here (no decisions on this screen); SC06/SC13 handle `stale_artifact` |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount, poll, focus | `GET /v1/workflows/{workflow_id}` | `title`, `funder_name`, `state`, `busy`, `started_by`, `started_at`, `internal_deadline`, `application_due`, `deadline_plan`, `artifacts`, `submission`, `gates[]`, `transitions[]` | Poll 3 s busy / 10 s otherwise; stop when finished |
| Mount, poll, focus | `GET /v1/workflows/{workflow_id}/history` | `items[]` | Same cadence as detail |
| App shell | `GET /v1/me` | `roles` | Session |

`workflowId` comes from the route and is passed through `decodeURIComponent` (it contains `:`), and
encoded with `encodeURIComponent` in every request.

## 9. Responsive behaviour

- >= 1280 px: two columns (stepper 2/3, deadline + artifacts 1/3), history full width below.
- 1024-1279 px: same, the right column 40%.
- 641-1023 px: single column; Deadline and Artifacts side by side under the stepper.
- <= 640 px: single column in the mobile order of section 3; the stepper collapses to the current step
  with "Show all {n} steps".

## 10. Accessibility

- The stepper is an `<ol aria-label="Lifecycle timeline">`; the current item has `aria-current="step"`
  and each item ends with visually hidden ": done" / ": current" / ": upcoming" (as today).
- The Next step card is a `<section aria-labelledby>` with heading "Next step"; its text is in an
  `aria-live="polite"` region, so state changes are announced once.
- History is an `<ol>`, newest first, each item a sentence; icons have `aria-hidden` with the meaning in text.
- Countdowns and statuses use icon + text; overdue reads "3 hours overdue".
- Focus is never moved by polling. Copy buttons have `aria-label="Copy artifact hash for HITL-2"`.
- `prefers-reduced-motion`: no stepper animation, static busy icon.

## 11. Fixture data

`api/workflow/fixture.ts` returns, for `getWorkflow` and `getHistory`:
1. `wf-budget`: `AwaitingBudgetSignoff`, open HITL-2 (finance_director, due in 70 h), framework set, 7 transitions, GO by `demo`.
2. `wf-drafting`: `Drafting`, `busy: true`; each `getWorkflow` call after the second returns `InReview`, so the live update can be shown in tests and the fixture app.
3. `wf-ready`: `AwaitingSubmissionAuth`, HITL-5 approved, `package_id` set, no submission.
4. `wf-submitted`: `Submitted` with `submission` and the full 16-transition history.
5. `wf-declined`: `Declined` with a NO-GO comment.
6. `wf-rollback`: `Planning` after a `rollback` transition and an `approval_invalidated` item.
7. `wf-missing`: `getWorkflow` throws `ApiError(404, "not_found")`.
Plus an error mode for history only.

## 12. Analytics and success measures

No analytics pipeline in the MVP; events are named for later: `workflow_viewed {workflow_id, state}`,
`workflow_next_step_clicked {state, gate}`, `workflow_artifact_opened {kind}`.
Success: in the demo rehearsal, the presenter never refreshes the page manually, and every step change
appears within 5 s.

## 13. Acceptance criteria

- [ ] AC1 Header shows title, funder, pursued-by line and the step badge with icon + label.
- [ ] AC2 The Next step card follows the rules table for each fixture case (open gate with and without the role, busy, ready to submit, submitted, declined, ineligible, expired), with exactly one primary button at most.
- [ ] AC3 The stepper shows visited steps with times and inline decisions, the current step, the remaining MVP path, and rollback rows.
- [ ] AC4 Deadline card shows internal and funder deadlines in the funder timezone, the countdown with thresholds, the buffer, and the collapsed milestones.
- [ ] AC5 Artifact links appear only when their id exists and point to the M5/M6/M7 routes.
- [ ] AC6 History lists transitions, gate requests, decisions and invalidations newest first with the actor labels; "Decisions only" filters and syncs `?history=`.
- [ ] AC7 Polling runs at 3 s when busy and 10 s otherwise, pauses when hidden, stops at a terminal state, and announces state changes in the live region without moving focus.
- [ ] AC8 Every state in section 7 renders with the exact copy, including 404 and history-only errors.
- [ ] AC9 The mobile layout collapses the stepper to the current step with "Show all".
- [ ] AC10 axe finds no violations in the default, busy, submitted and not-found states.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `apps/web/src/features/workflow/WorkflowDetail.test.tsx::renders header` |
| AC2 | `WorkflowDetail.test.tsx::next step rules` (`it.each` over the fixture cases) |
| AC3 | `features/workflow/Timeline.test.tsx::shows decisions and rollbacks` (extends the existing test) |
| AC4 | `WorkflowDetail.test.tsx::deadline card in funder timezone` |
| AC5 | `WorkflowDetail.test.tsx::artifact links` |
| AC6 | `WorkflowDetail.test.tsx::history items and decisions filter` |
| AC7 | `WorkflowDetail.test.tsx::live updates` (fake timers, `wf-drafting`) |
| AC8 | `WorkflowDetail.test.tsx::state copy` |
| AC9 | `WorkflowDetail.test.tsx::mobile stepper collapse` |
| AC10 | `WorkflowDetail.a11y.test.tsx` (vitest-axe) |

## 15. Open questions

- Show the budget total in the Artifacts card? Recommended: yes, if M5's `GET /v1/frameworks/{id}/budget`
  is cheap; otherwise "Budget v1" only. Default for the MVP: "Budget v1" only (no extra call).
- Should the page offer a "Cancel pursuit" action? Recommended: no for the MVP.
- Should HITL-4 review open SC19 (draft) instead of SC06? Recommended: SC06 (M3), which shows the decision buttons.
