# SC06: Approval decision

| | |
|---|---|
| Route | `/approvals/[requestId]` |
| Feature folder | `apps/web/src/features/approvals/` |
| Built by | [M3](../features/M3-approvals.md) (replaces M0's `ComingSoon` placeholder) |
| Primary users | The gate's approver: development/executive director (HITL-1), finance director (HITL-2), executive director (HITL-4), AOR (HITL-5) |
| Can act | Decide: holders of one of `approver_roles` (`can_decide`); HITL-2 and HITL-5 also pass the step-up dialog. View: any user |
| Status | Draft |

## 1. Purpose and user goals

One request, a short preview of the artifact it's bound to, and the decision. Users arrive
from SC05 "Review", SC08's open-gate link, or SC13 / SC19 "Decide" links (M3 D3).

Within 5 seconds the screen must answer:
1. What am I deciding, for which grant, by when?
2. Is it right? (score and deadline / budget totals and caps / draft and prior approvals / package)
3. Can I decide, and what are my options?

**Primary action:** the gate's positive option ("GO", "Approve and lock", "Approve", "Authorize submission").
**Secondary actions:** negative/neutral options with a comment; open the full screen behind the preview (SC04, SC13, SC19, SC22).

## 2. Information hierarchy

1. **Header:** gate, title, SLA, summary.
2. **Preview** (left/top): the numbers the approver needs.
3. **Decision** (right/below): binding line "Your decision applies to version sha256:3f1c…1e3f.", comment, buttons.
4. **History** (bottom, collapsed beyond 3): superseded versions and earlier decisions.

The full budget editor, narrative and package files stay on their screens.

## 3. Wireframe

Desktop (>= 1024 px), HITL-2:

```text
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ ← Approval Inbox                                                                         │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ 🛡 HITL-2 · Budget sign-off   ● Open   ⏱ 20h left · due Nov 8, 10:00 AM   🔒 Verification │  <- header (Card raised)
│ Project AWARE: Advancing Wellness and Resiliency in Education                             │
│ Budget sign-off: request 1,620,000.00                                                     │
│ Approver: Finance Director · Version sha256:3f1c9a…c9d1e3f [Copy]                         │
├────────────────────────────────────────────┬─────────────────────────────────────────────┤
│ Budget · version 2 · 5 periods              │ Your decision                               │  <- preview | decision (Card raised)
│  Direct costs              $1,372,881.36    │ Acting as Finance Director                  │
│  MTDC base                 $1,357,800.00    │ Your decision applies to version            │
│  Indirect (18.2% MTDC)       $247,118.64    │ sha256:3f1c…1e3f.                           │
│  Request                   $1,620,000.00    │ Comment                                     │
│  Cost share                        $0.00    │ ┌─────────────────────────────────────────┐ │
│  Project total             $1,620,000.00    │ │                                         │ │
│ Caps: ✓ Award ceiling  ✓ Indirect cap       │ └─────────────────────────────────────────┘ │
│ Drafted by hope-budget-agent                │ Needed to request changes or reject.        │
│ [Open budget review →]                      │ [Approve and lock] [Request changes] [Reject]│
├────────────────────────────────────────────┴─────────────────────────────────────────────┤
│ History                                                                                   │  <- Card inset
│ Nov 6, 10:30 AM · Superseded · sha256:9b0c…4ae21a                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

Mobile (<= 640 px): single column (header, preview, history collapsed); a sticky bottom bar
"Decide" opens a bottom sheet (M0 `Drawer`) with the binding line, comment and buttons.

## 4. Content inventory

All from `GET /v1/approvals/{request_id}` (M3).

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Gate | `gate` | `GateBadge` "HITL-2 · Budget sign-off" | Icon + text |
| Status | `status`, `decision`, `decided_by`, `decided_at` | "● Open" / "✓ Decided" | Icon + text |
| SLA | `due_at`, `overdue` | "20h left · due Nov 8, 10:00 AM" / "3h overdue" / "No SLA" | `countdown`; thresholds as SC05 |
| Verification marker | `step_up_required` | "🔒 Verification" | HITL-2, HITL-5 |
| Title | `title` | H1, wraps | `null` -> "Untitled opportunity" |
| Summary | `summary` | Body | Full |
| Approver | `acting_role` / `approver_roles` | "Approver: Finance Director" | `roleLabel` list |
| Hash | `artifact_hash` | "sha256:3f1c9a…c9d1e3f" + Copy | 13 + 7 chars; full in `title` and clipboard |
| HITL-1 preview | `preview.composite_score`, `recommendation`, `agency_name`, `award_ceiling`, `application_due`, `internal_deadline`, `links.opportunity` | `ScoreBar` "77"; `RecommendationBadge` "Pursue"; "HRSA · up to $300,000"; "Due Dec 11 (34 days) · internal Dec 8" | Money via `formatMoney`; days red <= 7, amber <= 14; link "Open opportunity →" |
| HITL-2 preview | `preview.version`, `periods`, `totals.*_minor`, `indirect_rate_bps`, `cap_checks[]`, `drafted_by`, `missing`, `links.budget` | Totals `Table` in dollars; "Indirect (18.2% MTDC)"; cap badges | `formatMoney` from minor units; `formatBps`; cap `pass` ✓ good, `fail` ✕ bad, `adjusted` ⚠ warn; `missing` -> warning (section 7) instead of the table |
| HITL-4 preview | `preview.project_title`, `request_minor`, `approvals[]`, `links.draft` | "Community Resilience Grants · request $150,000.00"; "✓ HITL-2 approved by sam.ortiz · Oct 30" | Link "Open draft →" |
| HITL-5 preview | `preview.package_id`, `links.package` | "Package ready for download after authorization" | Link "Open package →" |
| Options | `options[]` | Buttons with `label`, `tone` (primary / neutral / danger) | API order; only when `status=open` and `can_decide` |
| Binding line | `artifact_hash` | "Your decision applies to version sha256:3f1c…1e3f." | Always above the buttons |
| Comment hint | `options[].requires_comment` | "Needed to request changes or reject." (built from the labels that require it) | Hidden if none require it |
| History | `history[]`, `approvals[]` | "Nov 6, 10:30 AM · Superseded · sha256:9b0c…4ae21a"; "Nov 5 · NO-GO by demo-user · 'Outside our service area.'" | Newest first; > 3 collapse behind "Show all ({n})"; hidden when empty |

## 5. Components

- Header, preview, decision: `Card` (`glass-panel`); history: `Card` (`glass-inset`).
- Totals: `Table` (caption "Budget totals"); `ScoreBar`; `GateBadge`, `UrgencyBadge`, `RecommendationBadge`, `Badge`.
- Decision: feature-local `DecisionPanel.tsx` (comment `TextArea`, option `Button`s, binding line) and today's `StepUpDialog.tsx` (moved/renamed only inside the feature).
- Mobile sheet: M0 `Drawer` (bottom variant). Success: M0 `Toast` on SC05.
- Copy: `Button` `ghost`.

## 6. Interactions

1. **Load.** `GET /v1/approvals/{requestId}`.
2. **Option needing a comment with a blank comment.** No request; field error "Add a comment to {label, lower-case}." and focus to the comment.
3. **Option on a step-up gate.** `StepUpDialog` opens ("Confirm it's you"); Cancel returns focus to the button; "Verify and {label}" enabled at 6 digits.
4. **Submit.** `POST /v1/approvals/{requestId}/decision` with
   `{"decision": "<option>", "artifact_hash": "<from the GET>", "comment": "<trimmed>" | null, "role": "<acting_role>"}`
   and `X-Hope-MFA: true` after step-up. Buttons disabled; chosen one reads "Recording…".
   - **202** -> `router.push(next === "/approvals" ? "/approvals?decided={id}" : next)` (HITL-5 approve goes to `/packages/{package_id}`).
   - **409 `stale_artifact`** -> stale notice with both hashes; refetch; keep the comment; focus the notice.
   - **409 `gate_closed`** -> if extras show the same `decision` by the current user, treat as 202 (retry after success); otherwise "Already decided" notice, refetch, read-only.
   - **403 `step_up_required`** -> reopen the dialog with "That code has expired. Enter a new one."
   - **403 `approver_role_required`** -> permission notice "Switch to {roles} in your user menu to decide."; buttons hidden.
   - **403 `separation_of_duties`** -> "You drafted this budget, so someone else must approve it."
   - **422 `comment_required`** -> same as interaction 2 (server backstop).
   - **422 `decision_not_allowed`** -> "This option isn't available for this gate. Reload and try again."
   - **404 `not_found`** -> not-found state.
   - Network / 5xx -> "Decision not recorded" with Retry (same body).
5. **Copy hash.** Copies the full hash; live region "Version hash copied."
6. **Role switched while here.** Refetch (so `can_decide` / `acting_role` update live during the demo).
7. **Keyboard.** `Ctrl+Enter` in the comment = primary option; `Esc` closes the dialog/sheet.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading | Header skeleton + preview skeleton (6 rows) + decision skeleton (box + 3 pills) |
| Not found | "This approval request doesn't exist." + "Back to the inbox" |
| Error (load) | `ErrorNotice` "We couldn't load this request." + "Check that the API is running, then try again." + Reload |
| Read-only: decided | Banner "Decided: {label} by {decided_by} on {date}." (+ for HITL-5 approve: "Open package →") |
| Read-only: superseded | Banner "A newer version replaced this request." + "Back to the inbox" |
| Not your role | "You can view this request. To decide, switch to {roles} in your user menu." |
| Stale artifact | `ErrorNotice` "This changed since you opened it." + "Your decision was not recorded. You reviewed {short hash}; the current version is {short current_hash}. Check the update, then decide again." |
| Budget missing (`preview.missing`) | Warning "The budget this request was opened for has been replaced. Go back to the inbox for the current request." |
| Already decided | `ErrorNotice` "Already decided." + "{decided_by} recorded {label} at {time}." |
| Separation of duties | `ErrorNotice` "You drafted this budget, so someone else must approve it." |
| Submit failed | `ErrorNotice` "Decision not recorded." + "Your comment is still here. Try again." + Retry |
| Offline | Banner "You're offline. Decisions need a connection." Buttons disabled |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount, after 409, role change, focus with empty comment | `GET /v1/approvals/{request_id}` | all `ApprovalDetail` fields | none |
| Decide | `POST /v1/approvals/{request_id}/decision` `{decision, artifact_hash, comment, role}` (+ `X-Hope-MFA`) | 202 `next`, `decision`; problem `code`, `current_hash`, `decided_by`, `decided_at`, `approver_roles` | Invalidates SC05 |
| Shell | `GET /v1/me` (M0) | `roles` | Session |

## 9. Responsive behaviour

- >= 1024 px: preview 60% | decision 40%; history full width.
- 641-1023 px: decision stacks under the preview.
- <= 640 px: single column, tables become `dl`; sticky "Decide" bar + bottom sheet; history collapsed.

## 10. Accessibility

- Tab order: back link, Copy, preview link, comment, options (positive -> negative), history toggle.
- `h1` = title; preview/decision/history are `section`s with `aria-labelledby`.
- `StepUpDialog` (`Modal`): focus on the code input, trapped, Esc cancels, focus returns to the option.
- Errors `role="alert"`; after a 409 focus moves to the notice; field error via `aria-describedby`.
- Danger options use the `x` icon plus text; statuses and caps use icon + text.
- `prefers-reduced-motion`: sheet appears without sliding.

## 11. Fixture data

`apps/web/src/api/approvals/fixture.ts::getApproval` / `decide` for SC05's F1-F5:

| Case | preview | decide behaviour |
|---|---|---|
| F1 HITL-1 | `opportunity`: 77.3, `pursue`, HRSA, ceiling `30000000`, due +34 d, internal +31 d | 202 |
| F2 HITL-2 | `budget`: v2, 5 periods, direct `137288136`, MTDC `135780000`, indirect `24711864`, `1820` bps, request `162000000`, caps pass, `drafted_by: "hope-budget-agent"`; history: superseded v1 | first decide -> 409 `stale_artifact` with `current_hash`, then 202 |
| F3 HITL-4 | `draft`: "Community Resilience Grants", `15000000`, HITL-2 approval by sam.ortiz | 202 |
| F4 HITL-5 | `package`: `package_id` `d8…` | approve -> 202 `next: /packages/d8…` |
| F5 decided | `opportunity` | read-only |
| F6 | `getApproval("missing")` | 404 `not_found` |
| F7 | `FixtureApi({ approvals: "sod" })` | F2 approve -> 403 `separation_of_duties` |
| F8 | `FixtureApi({ approvals: "closed" })` | next decide -> 409 `gate_closed` by "sam.ortiz" |

## 12. Analytics and success measures

Events: `approval_viewed {gate, can_decide}`, `approval_decided {gate, decision, step_up, seconds_on_screen}`, `approval_conflict {code}`.
Success (demo): each gate decided in under 20 s with no reload; the stale-hash 409 is shown once on purpose (F2) and recovers in one click.

## 13. Acceptance criteria

- [ ] AC1 Header shows gate, status, SLA, verification marker, title, summary, approver and short hash with Copy.
- [ ] AC2 Each preview (F1-F4) renders its fields and link.
- [ ] AC3 Buttons follow `options` (labels and tones from the API).
- [ ] AC4 A comment-required option with a blank comment shows the error and sends nothing.
- [ ] AC5 F2/F4: the step-up dialog opens; Verify sends the decision with the reviewed hash, `role` and `X-Hope-MFA: true`.
- [ ] AC6 F2 409 `stale_artifact` shows both hashes, keeps the comment and reloads.
- [ ] AC7 202 navigates to `/approvals?decided={id}`; F4 approve navigates to `/packages/{package_id}`.
- [ ] AC8 `gate_closed` (F8) shows "Already decided." and goes read-only; same-user same-decision is treated as success.
- [ ] AC9 Without the role, the view-only copy shows and buttons are hidden; switching role refetches and shows them.
- [ ] AC10 `separation_of_duties` (F7) and not-found (F6) render their copy.
- [ ] AC11 Every state in section 7 renders with the exact copy.
- [ ] AC12 The step-up dialog traps focus and returns it on cancel.
- [ ] AC13 <= 640 px: sticky "Decide" bar opens the sheet.
- [ ] AC14 axe: no violations (open, read-only, stale).

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `apps/web/src/features/approvals/ApprovalDetail.test.tsx::header content` |
| AC2 | `ApprovalDetail.test.tsx::preview per gate` |
| AC3 | `ApprovalDetail.test.tsx::options from api` |
| AC4 | `ApprovalDetail.test.tsx::requires comment` |
| AC5 | `ApprovalDetail.test.tsx::step up then decide with hash and role` |
| AC6 | `ApprovalDetail.test.tsx::stale artifact recovers` |
| AC7 | `ApprovalDetail.test.tsx::navigates after decision` |
| AC8 | `ApprovalDetail.test.tsx::gate closed handling` |
| AC9 | `ApprovalDetail.test.tsx::view only until role switch` |
| AC10 | `ApprovalDetail.test.tsx::sod and not found` |
| AC11 | `ApprovalDetail.test.tsx::state copy` |
| AC12 | `ApprovalDetail.test.tsx::step up dialog focus` |
| AC13 | `ApprovalDetail.test.tsx::mobile decide sheet` |
| AC14 | `apps/web/src/features/approvals/ApprovalDetail.a11y.test.tsx` (vitest-axe) |

## 15. Open questions

- Keep the step-up dialog for HITL-2/5 in the demo? Recommended default: yes (placeholder, any 6 digits), per M3 D1.
- Should HITL-5 "Authorize submission" ask the AOR to tick "I have reviewed the package"? Recommended default: yes, a required checkbox inside the step-up dialog, because nothing else on this screen shows the files.
