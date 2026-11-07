# SC05: Approval inbox

| | |
|---|---|
| Route | `/approvals` (query: `mine`, `status`, `gate` (repeatable), `decided`) |
| Feature folder | `apps/web/src/features/approvals/` |
| Built by | [M3](../features/M3-approvals.md) (replaces today's inline-decision `ApprovalInbox.tsx` / `RequestCard.tsx`) |
| Primary users | In the demo: the presenter switching roles (development director -> finance director -> executive director -> AOR). In real use: each approver, a few times a week |
| Can act | View: any user. Decide (in SC06): the request's `approver_roles` (`development_director`/`executive_director` HITL-1, `finance_director` HITL-2, `executive_director` HITL-4, `aor` HITL-5) |
| Status | Draft |

## 1. Purpose and user goals

The inbox is the approver's to-do list for the four MVP gates. Users arrive from the nav,
from the dashboard's "Waiting on you" card (SC02, M7), from SC08's open-gate link, or right
after switching role in the app-shell role switcher (M0).

Within 5 seconds the screen must answer:
1. What is waiting on me (my current role)?
2. What is most urgent? (overdue first, then soonest SLA)
3. What kind of decision is each one, for which grant?

**Primary action:** open the top request ("Review" -> SC06).
**Secondary actions:** filter by gate, show decided requests, turn off "Assigned to me" to see everything.

Decisions are made in SC06, not inline, because each gate's approver must see the artifact (budget totals, package) first.

## 2. Information hierarchy

1. **Urgency:** SLA countdown; overdue rows first with the alert icon.
2. **Gate and grant:** "HITL-2 · Budget sign-off" + opportunity title.
3. **Summary line** from the workflow ("Budget sign-off: request 1,620,000.00").
4. **Roles / step-up marker.**

Hidden behind "Review": preview, hash, options, history.

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ Approval Inbox                                       [4 open]  [⚠ 1 overdue]              │  <- PageHeader + count badges
│ Decisions waiting on your role, most urgent first. Each decision is bound to the exact   │
│ version you review.                                                                       │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ Acting as: Finance Director (change in your user menu)                                    │  <- role hint (Well, glass-inset)
│ [✓ Assigned to me]  Status: (Open|Decided)                                                │  <- filter bar (Card inset)
│ Gates: [Go/No-Go 1] [Budget 1] [Executive 1] [Submission 1]                [Clear filters]│
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ SLA            │ Gate                     │ Opportunity                           │        │  <- Table
│ ⚠ 3h overdue   │ 🛡 HITL-4 · Executive     │ Community Resilience Grants           │[Review]│
│                │                          │ Executive approval                    │        │
│ ⏱ 6h left  🔒  │ 🛡 HITL-5 · Submission    │ Community Health Workers for Public…  │[Review]│
│ ⏱ 20h left 🔒  │ 🛡 HITL-2 · Budget        │ Project AWARE: Advancing Wellness…    │[Review]│
│ ⏱ 4d left      │ 🛡 HITL-1 · Go / No-Go    │ Rural Health Care Services Outreach…  │[Review]│
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

Mobile (<= 640 px):

```text
┌──────────────────────────────┐
│ Approval Inbox               │
│ [4 open] [⚠ 1 overdue]       │
│ Acting as: Finance Director  │
│ [✓ Assigned to me] [Open ▾]  │
│ [Go/No-Go][Budget][Exec][Sub]│ <- chips scroll horizontally
├──────────────────────────────┤
│ ⚠ 3h overdue                 │ <- Card per request
│ 🛡 HITL-4 · Executive approval│
│ Community Resilience Grants  │
│ Executive approval           │
│ [          Review          ] │
└──────────────────────────────┘
```

## 4. Content inventory

All from `GET /v1/approvals` (M3) unless noted.

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Open count | `counts.open` | Badge "4 open" (info, `inbox` icon) | Same `assignee` and gate filters; ignores Status |
| Overdue count | `counts.overdue` | Badge "1 overdue" (bad, `alert` icon) | Hidden at 0; click turns the list to open + sorted (already first) and moves focus to the first overdue row |
| Acting as | `GET /v1/me` `roles` (after the role switcher) | "Acting as: Finance Director" / "Acting as: all roles" | `roleLabel`; "all roles" when the demo user has every `Role` |
| Gate chips | `counts.by_gate` | "Budget 1" | Fixed order HITL-1, HITL-2, HITL-4, HITL-5; selected chip pressed with ✓; count 0 chips stay visible but muted |
| SLA | `items[].due_at`, `overdue` | "20h left", "3h overdue", "No SLA" | `lib/time.ts::countdown`: overdue bad+alert; <= 24 h bad+clock; <= 3 d warn+clock; else neutral+clock; re-rendered every 30 s |
| Step-up marker | `items[].step_up_required` | 🔒 + sr-only "Needs verification" | HITL-2, HITL-5 |
| Gate | `items[].gate` | `GateBadge` "HITL-2 · Budget sign-off" | Icon + text |
| Opportunity | `items[].title` | "Project AWARE: Advancing Wellness and Resiliency in Education" | Ellipsis at 48 chars, full title in `title` attr; `null` -> "Untitled opportunity" |
| Summary | `items[].summary` | "Budget sign-off: request 1,620,000.00" | 1 line, ellipsis |
| Not-assigned tag | `items[].can_decide` | Tag "Not your role" | Only when `mine=0` and `can_decide` false |
| Decided text | `items[].decision`, `decided_by`, `decided_at` | "NO-GO by demo-user · Nov 5" | Status = Decided only; label from the gate's option labels (same table as M3) |
| Action | `items[].request_id`, `can_decide` | "Review" (primary) / "View" (neutral) | Always links to `/approvals/{request_id}` |

## 5. Components

- `PageHeader` with `Badge`s; role hint in `Well` (`glass-inset`).
- Filter bar `Card` (`glass-inset`): "Assigned to me" toggle `Button` (`aria-pressed`, `glass-active` when on); `Segmented` Open/Decided; gate chips as toggle buttons in a `fieldset`.
- `Table` (caption "Approval requests"); mobile `Card` list.
- `GateBadge`, `UrgencyBadge`, `roleLabel` from today's `features/status.tsx` (unchanged).
- `Loading`, `EmptyState`, `ErrorNotice`, `SuccessNotice`; `Toast` (M0) for the "Decision recorded" message.
- New inside the feature (not shared): `ApprovalRow.tsx`, `GateChips.tsx`.

## 6. Interactions

1. **Mount.** `GET /v1/approvals?status=open&assignee=me` (plus `gate=` for selected chips). URL defaults `?mine=1&status=open`.
2. **"Assigned to me" toggle.** Sets `?mine=0|1`; refetch without/with `assignee=me`. Previous rows stay, dimmed, `aria-busy="true"`.
3. **Status segmented.** `?status=decided` -> `GET /v1/approvals?status=decided…`.
4. **Gate chip.** Toggles `gate` in the URL (repeatable) and refetches; "Clear filters" resets to `?mine=1&status=open`.
5. **Review / View.** Navigates to `/approvals/{request_id}`; Enter on a focused row does the same.
6. **Role switched (M0 user menu).** The shared client sends the new `X-Hope-Roles`; SC05 listens for the role-change event M0 emits (or a `storage` event on its `localStorage` key) and refetches.
7. **Return from SC06.** `?decided={request_id}` -> `Toast` "Decision recorded." once; param removed with `router.replace`; list refetched.
8. **Background refresh.** On window focus and every 30 s while visible: refetch (so a HITL-1 opened by Pursue appears during the demo without reload).
9. **Keyboard.** ↑/↓ moves between rows, Enter opens.

Errors: any failure -> error state (section 7); 422 `validation_error` from bad URL params -> reset filters + notice.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading (first) | Two grey badge pills + 4 skeleton rows (pill, two text bars, button) |
| Empty, mine + open | "Nothing is waiting on you as {role}. Switch role in your user menu, or see all open requests." + link "See all open requests" (sets `mine=0`) |
| Empty, all + open | "No approvals are open. Pursue an opportunity from the matrix to start one." + link "Open the matrix" (`/matrix`) |
| Empty, decided | "No decisions yet." |
| Filtered to empty | "No requests match these gates." + "Clear filters" |
| Error (network / 5xx) | `ErrorNotice` "We couldn't load your approvals." + "Check that the API is running, then try again." + Reload; rows already shown stay |
| Error `validation_error` | Notice "Some filters in the link weren't valid and were reset." |
| Permission | n/a for listing; rows outside the role show "Not your role" and "View" |
| Offline | Banner "You're offline. The list may be out of date." |
| Just decided | Toast "Decision recorded." |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount, filter change, role change | `GET /v1/approvals?status=&gate=&assignee=me&limit=100` | `items[*]`, `counts.open`, `counts.overdue`, `counts.by_gate` | Keep previous rows while loading |
| Focus, every 30 s visible | same | same | Replace list |
| App shell | `GET /v1/me` (M0) | `roles` | Session; refetched by M0 on role switch |

## 9. Responsive behaviour

- >= 1024 px: table SLA | Gate | Opportunity (title + summary) | Action.
- 641-1023 px: Gate badge moves under the title; table keeps 3 columns.
- <= 640 px: card per request; Status becomes a select; chips scroll horizontally; full-width buttons.

## 10. Accessibility

- Tab order: overdue badge (button), Assigned toggle, Status, gate chips, Clear filters, each row's action.
- Toggles use `aria-pressed`; chips in `fieldset` with legend "Gates".
- `<table>` with caption and `th scope="col"`.
- SLA text always says "left", "overdue" or "No SLA"; badges are icon + text.
- `aria-live="polite"` region announces "{n} requests" after filter/role changes.
- 1 px borders (>= 3:1) on cards and chips in addition to shadows; `glass-focus` ring.
- `prefers-reduced-motion`: no skeleton shimmer, no dimming transition.

## 11. Fixture data

`apps/web/src/api/approvals/fixture.ts` mirrors the M3 seed at `FIXED_NOW = 2026-11-07T15:00:00Z`:

| Case | gate | title | roles | due | status |
|---|---|---|---|---|---|
| F1 `rhcso` | HITL-1 | Rural Health Care Services Outreach Program | development_director, executive_director | +4 d | open |
| F2 `aware` | HITL-2 | Project AWARE: Advancing Wellness and Resiliency in Education | finance_director | +20 h | open, step-up, stale on first decide |
| F3 `crg` | HITL-4 | Community Resilience Grants | executive_director | -3 h | open, overdue |
| F4 `chw` | HITL-5 | Community Health Workers for Public Health Response and Resilient Communities | aor | +6 h | open, step-up |
| F5 `yof` | HITL-1 | Youth Opportunity Fund | development_director, executive_director | - | decided `no_go` |

`assignee=me` uses the fixture session roles (all `Role` values by default; tests pass
`roles: ["finance_director"]`). Switches: `new FixtureApi({ approvals: "empty" | "error" })`.

## 12. Analytics and success measures

Events (console logger from M0, if any): `approvals_viewed {open, overdue, mine, role}`, `approval_opened {gate, overdue}`.
Success (demo): from the role switch to opening the right request takes one click; no reload is needed to see a newly opened HITL-1.

## 13. Acceptance criteria

- [ ] AC1 With all roles and defaults, F1-F4 show, overdue F3 first, then by `due_at`; F5 is absent.
- [ ] AC2 With roles `["finance_director"]`, only F2 shows and the hint reads "Acting as: Finance Director".
- [ ] AC3 Header shows "4 open" and "1 overdue"; chips show `counts.by_gate`.
- [ ] AC4 Gate chips and Status update the URL and the list, and are restored on reload.
- [ ] AC5 Status "Decided" shows F5 with "NO-GO by demo-user".
- [ ] AC6 "Assigned to me" off with roles `["aor"]` shows F1-F4 with "View" + "Not your role" on F1-F3.
- [ ] AC7 `?decided=` shows the toast once and removes the param.
- [ ] AC8 A role change refetches the list.
- [ ] AC9 Every state in section 7 renders with the exact copy.
- [ ] AC10 <= 640 px renders cards.
- [ ] AC11 axe: no violations (default, empty, error).

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `apps/web/src/features/approvals/ApprovalInbox.test.tsx::lists open requests by urgency` |
| AC2 | `ApprovalInbox.test.tsx::filters by acting role` |
| AC3 | `ApprovalInbox.test.tsx::header counts and gate chips` |
| AC4 | `ApprovalInbox.test.tsx::syncs filters with url` |
| AC5 | `ApprovalInbox.test.tsx::decided view` |
| AC6 | `ApprovalInbox.test.tsx::read only rows outside role` |
| AC7 | `ApprovalInbox.test.tsx::decided toast once` |
| AC8 | `ApprovalInbox.test.tsx::refetches on role change` |
| AC9 | `ApprovalInbox.test.tsx::state copy` |
| AC10 | `ApprovalInbox.test.tsx::mobile cards` (matchMedia mock) |
| AC11 | `apps/web/src/features/approvals/ApprovalInbox.a11y.test.tsx` (vitest-axe) |

## 15. Open questions

- Keep inline quick decisions on the list? Recommended default: no; one decision path (SC06).
- Remember the "Assigned to me" choice? Recommended default: no for the MVP; always default on.
