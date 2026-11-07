# SC15: Audit trail

> **Out of scope for the hackathon. Don't build this.** This screen belongs to the earlier design. Hackathon agents build only the H0-H5 screens (SC00, SC01, SC09, SC11, SC24-SC28); see [`README.md`](../README.md).

| | |
|---|---|
| Route | `/audit` (query: `entity_type`, `entity_id`, `actor`, `action`, `from`, `to`, `selected`) |
| Feature folder | `apps/web/src/features/audit/` |
| Built by | [S13](../features/S13-audit-trail.md) |
| Primary users | Compliance officer (weekly, and during audits), executive director (monthly), org admin (when investigating) |
| Can act | View: `org_admin`, `executive_director`, `compliance_officer`, `finance_director`, `development_director`, `aor`. Verify chain: same roles. Export: `org_admin`, `compliance_officer` with step-up MFA |
| Status | Draft |

## 1. Purpose and user goals

The audit trail is where someone accountable proves what happened: who approved a budget,
which manifest hash the AOR authorized, who changed the profile. People arrive from the nav,
from a workflow timeline (SC08 "View full audit trail", which pre-filters by workflow), or from a
deep link an auditor was sent.

Within 5 seconds the screen must answer:
1. Who did what, most recently? (the newest entries, with plain-language actions)
2. Is this trail intact? (the chain-verification status)
3. What happened to *this* record? (the filter chip shows the scoped entity)

**Primary action:** filter to the record or person in question and read the entries.
**Secondary actions:** open an entry's full detail, verify the chain, export for an auditor.

## 2. Information hierarchy

1. **Integrity status.** A one-line badge ("Chain verified · 1,842 entries") in the header, because an audit
   trail is only useful if it can be trusted.
2. **When, who, what, which record.** Each row reads like a sentence: "Nov 7, 2:58 PM · Sam Lee
   (finance director) approved budget sign-off (HITL-2) · Workflow wf-7f3a".
3. **Key evidence.** The artifact hash for approvals, shortened, with a copy button.

The raw `detail` JSON, `hash` and `prev_hash` are behind a click (the detail drawer): auditors
need them, but they would drown the timeline.

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ Audit trail                          ✓ Chain verified · 1,842 entries · 2 min ago [Verify] │  <- PageHeader + integrity badge
│ Every approval, submission and profile change, in order.                  [⤓ Export…]     │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ Record: (Any ▾) [wf-7f3a        ]  Person: [any          ]  Action: (All actions ▾)        │  <- filter bar (Card inset)
│ From: [2026-10-01]  To: [2026-11-07]   [Clear filters]                                     │
│ Showing workflow wf-7f3a ×                                                                 │  <- active-scope chip
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ When                │ Who                      │ What                          │ Record     │
│ Nov 7, 2:58 PM      │ Sam Lee · Finance dir.   │ ✓ Approved Budget sign-off    │ Workflow   │
│                     │                          │   (HITL-2) · hash 9f2c…e01 ⧉  │ wf-7f3a    │
│ Nov 6, 9:12 AM      │ ⚙ Workflow service       │ ◷ Requested Budget sign-off   │ Workflow   │
│                     │                          │   from Finance director       │ wf-7f3a    │
│ Nov 5, 4:40 PM      │ Dana Okafor · Org admin  │ ✎ Changed roles of Sam Lee    │ User       │
│ …                                                                                          │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                    [Load older entries]    │
└───────────────────────────────────────────────────────────────────────────────────────────┘
                                   Detail drawer (480 px, right):
                                   ┌────────────────────────────────────────┐
                                   │ Approved Budget sign-off (HITL-2)  [×] │
                                   │ Nov 7, 2026 2:58:03.120 PM EST         │
                                   │ By Sam Lee (finance director)          │
                                   │ Record  workflow:wf-7f3a  [Open ↗]     │
                                   │ ─ Details ───────────────────────────  │
                                   │ gate            HITL-2                 │
                                   │ decision        approve                │
                                   │ artifact_hash   sha256:9f2c…e01  ⧉     │
                                   │ role            finance_director       │
                                   │ comment         [redacted]             │
                                   │ ─ Integrity ─────────────────────────  │
                                   │ Entry #1842                            │
                                   │ hash       4be1…e09a  ⧉                │
                                   │ prev_hash  77c0…1d3f  ⧉                │
                                   │ [Show raw JSON]                        │
                                   └────────────────────────────────────────┘
```

Mobile (<= 640 px):

```text
┌──────────────────────────────┐
│ Audit trail                  │
│ ✓ Chain verified · 1,842     │
│ [Filters (1)]   [⤓ Export]   │
│ Showing workflow wf-7f3a ×   │
├──────────────────────────────┤
│ Nov 7, 2:58 PM               │
│ ✓ Sam Lee approved Budget    │
│   sign-off (HITL-2)          │
│ Workflow wf-7f3a           › │
├──────────────────────────────┤
│ Nov 6, 9:12 AM               │
│ ◷ Workflow service requested │
│   Budget sign-off            │
│ Workflow wf-7f3a           › │
└──────────────────────────────┘
```

## 4. Content inventory

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Integrity badge | `GET /v1/audit/verify` -> `valid`, `checked`, `verified_at` | "✓ Chain verified · 1,842 entries · 2 min ago" | `valid: false` -> danger badge "✕ Chain broken at entry #1201" linking to that entry. Shows "Checked the latest 100,000 entries" when `checked_from_id > 1` |
| When | `items[].at` | "Nov 7, 2:58 PM" (local time); full timestamp with ms and zone in the tooltip and drawer | Rows are newest first. A date divider ("Today", "Yesterday", "Nov 5") appears between days |
| Who | `actor`, `actor_kind` | User: display name + role if known; Agent: "Agent A10 (Packaging)"; System: "⚙ Workflow service" | Names: from `GET /v1/users` (only when the viewer is `org_admin`) or the current user from `GET /v1/me`; otherwise the id shortened to 8 chars, e.g. "User 6f1c2a9e". Role comes from `detail.role` when present |
| What | `action` + `detail` | Plain-language sentence from `ACTION_COPY` (below), with an icon | Unknown actions show the raw `action` in monospace |
| Approval hash | `detail.artifact_hash` / `detail.manifest_hash` | "hash 9f2c…e01" (first 4 + last 3 hex) with copy button | Only for `hitl.*` and `submission.*` |
| Record | `entity_type`, `entity_id` | "Workflow" over "wf-7f3a" | Links: workflow -> `/workflows/{id}`, opportunity -> `/opportunities/{id}`, package -> `/packages/{id}`, agency -> `/profile`, user -> `/settings/team` (admins only); others plain text |
| Active-scope chip | URL `entity_type` + `entity_id` | "Showing workflow wf-7f3a ×" | × clears both |
| Detail fields | `detail` | Key/value table, keys in monospace | `"[redacted]"` values render in italics "redacted" with a tooltip "Only Org admins and Compliance officers can see this" |
| hash / prev_hash | `hash`, `prev_hash` | Shortened, with copy buttons | `prev_hash: null` shows "First entry in the chain" |

`ACTION_COPY` (in `features/audit/actions.ts`):

| action | Sentence | Icon |
|---|---|---|
| `hitl.requested` | "Requested {GATES[gate].title} ({gate}) from {roles}" | `clock` |
| `hitl.decided` | "{Approved / Rejected / Requested changes on / Chose GO on / Chose NO-GO on / Deferred} {gate title} ({gate})" | `check` (approve, go), `x` (reject, no_go), `alert` (request_changes), `minus` (defer) |
| `submission.authorized` | "Authorized submission via {channel}" | `shield` |
| `application.submitted` | "Submitted the application (tracking {tracking_id})" | `up` |
| `user.invited` / `user.activated` / `user.roles_changed` / `user.deactivated` / `user.reactivated` | "Invited {entity}" / "Signed in for the first time" / "Changed roles of {entity}: {before} → {after}" / "Deactivated {entity}" / "Reactivated {entity}" | `eye` |
| `artifact.downloaded` | "Downloaded {classification} document {sha256 short}" | `lock` |
| `audit.exported` | "Exported {row_count} audit entries" | `up` |
| profile actions (existing, `agency:` subjects) | "Changed the agency profile ({action})" | `eye` |

## 5. Components

- Header: `PageHeader` with the integrity `Badge` (`good`/`check`, `bad`/`x`, or `neutral`/`clock` while checking) and a `ghost` "Verify" `Button`.
- Export: `Button` (neutral) opening an export `Modal`.
- Filter bar: `Card` (`glass-inset`) with `SelectField` (record type), `TextField` (record id, person id), `SelectField` (action group: All, Approvals `hitl.*`, Submissions `submission.*` + `application.*`, Team `user.*`, Documents `artifact.*`, Exports `audit.*`), and two date `TextField`s (`type="date"`).
- Timeline: `Table` (caption "Audit entries") with day dividers as full-width `Tr` rows (`role="rowgroup"` heading).
- Detail: `Modal` `variant="drawer"` (until the shared `Drawer` primitive from SC03 lands).
- Copy buttons: new small `CopyButton` primitive -> **Shared contract addition** (`components/ui/CopyButton.tsx`); until it exists, a local `ghost` `Button` calling `navigator.clipboard.writeText`.
- Step-up: `requestStepUp(returnTo)` from `features/session/oidc.ts` (S01). Dev mode reuses the approvals `StepUpDialog` pattern.

## 6. Interactions

1. **Filter.** Changing any filter writes the URL query (`?entity_type=workflow&entity_id=wf-7f3a&action=hitl.*&from=2026-10-01&to=2026-11-08`)
   and calls `GET /v1/audit` with the same params (dates become `from=<date>T00:00:00<local offset>`, and `to` is the day after the
   chosen date, exclusive). Text inputs are debounced 400 ms. The old rows stay, dimmed (`aria-busy`), while loading.
   - 422 `entity_type_required`: the record-id field shows "Choose a record type first." (The UI disables the id field until a type is chosen, so this only happens from a hand-edited URL.)
   - 422 `invalid_range`: the To field shows "End date must be after the start date."
2. **Load older entries.** `GET /v1/audit?…&cursor={next_cursor}`, appended. The button is hidden when `next_cursor` is null and says "Beginning of the trail" instead.
3. **Open entry.** Click a row or press Enter. Sets `?selected={audit_id}` and opens the drawer from the row data (no extra call).
   A deep link with `selected` that isn't on the first page shows the drawer once that row loads, or "This entry isn't in the current filter." after 3 pages.
4. **Copy hash.** Copies the full hash; a polite live region says "Hash copied".
5. **Verify.** `GET /v1/audit/verify`. Runs automatically on mount, at most once every 10 minutes per tab (cached in memory). The badge shows "Checking chain…" while running.
   - 503 `verify_timeout`: badge `neutral` "Couldn't verify right now" with a Retry link.
6. **Export.** Opens the modal: format (`Segmented` CSV / JSON Lines), and a summary "Exports the {n or "matching"} entries for the current filters ({from} to {to})."
   Confirm -> if `me.mfa` is false, `requestStepUp("/audit?…&export=1")`; on return with `export=1`, the modal reopens.
   With MFA, the browser downloads `GET /v1/audit/export?{filters}&format=csv` (fetch with the bearer token -> blob -> object URL with the
   server's filename).
   - 403 `step_up_required`: start step-up as above.
   - 403 `forbidden`: the Export button is hidden for other roles; if hit anyway, "Only Org admins and Compliance officers can export the audit trail."
   - 422 `export_too_large`: "That's more than 100,000 entries. Narrow the date range and try again."
   - After a successful export the list refreshes, so the new `audit.exported` entry appears at the top.
7. **Record link.** Opens the related screen in the same tab; the browser's back button returns to the same filtered view (state lives in the URL).
8. **Keyboard.** `/` focuses the record-id field, ↑/↓ moves between rows, Enter opens the drawer, Esc closes it.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading (first load) | Header with badge "Checking chain…", filter bar, and 10 skeleton rows (three text bars each) |
| Empty: no entries at all | "Nothing has been recorded yet. Approvals, submissions and profile changes will appear here as they happen." |
| Filtered to empty | "No entries match these filters." + "Clear filters" button |
| Scoped to a record with no entries | "No audit entries for {Workflow wf-7f3a} yet." + "Show all entries" |
| Error loading entries | `ErrorNotice` "We couldn't load the audit trail." + Retry. Rows already shown stay visible |
| Chain broken | Danger banner under the header: "The audit chain is broken at entry #1201. Entries after it can't be proven unaltered. Tell your Hope administrator; don't export until it's investigated." + "Show entry #1201" |
| Permission denied | `EmptyState` with the `lock` icon: "You don't have access to the audit trail. Ask an Org admin or Compliance officer." No API calls are made |
| Offline | Banner "You're offline. Showing the entries already loaded." Filters are disabled |
| Stale artifact | Not applicable (read-only screen) |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount, filter change | `GET /v1/audit?{filters}&limit=50` | all item fields, `next_cursor` | Replaces the list; no cache across filter changes |
| Load older | `GET /v1/audit?{filters}&cursor=…&limit=50` | same | Appends |
| Mount, Verify click | `GET /v1/audit/verify` | `valid`, `checked`, `checked_from_id`, `first_broken_id`, `reason`, `verified_at` | Memory cache 10 min |
| Export | `GET /v1/audit/export?{filters}&format=csv\|jsonl` | file body, `Content-Disposition` | none |
| Mount (admins only) | `GET /v1/users` (S01) | `user_id`, `display_name`, `roles` | Session cache; skipped when the viewer isn't `org_admin` or when S01's client isn't available |
| Shell | `GET /v1/me` (S01) | `roles`, `mfa`, `user_id`, `display_name` | Session |

## 9. Responsive behaviour

- >= 1280 px: four columns, drawer overlays the right side.
- 1024-1279 px: "Who" and "What" merge into one column ("Sam Lee approved Budget sign-off").
- 641-1023 px: the Record column moves under the sentence; filters wrap to two rows.
- <= 640 px: cards as in the mobile wireframe; filters in a bottom sheet behind "Filters (n)"; the drawer is full screen; Export stays in the header.

## 10. Accessibility

- A real `<table>` with `<th scope="col">`; day dividers are `<th scope="rowgroup" colspan="4">`.
- Each row is focusable (`tabindex=0`) with an accessible name equal to the full sentence plus the time.
- The integrity badge is in an `aria-live="polite"` region, so the verification result is announced; a broken chain also uses `role="alert"`.
- Icons are decorative (`aria-hidden`); meaning is always in text ("Approved", "Chain verified").
- The drawer is `role="dialog"` labelled by its title; focus goes to the close button on open and back to the row on close.
- Copy buttons are labelled "Copy hash 4be1…e09a".
- Dates in inputs use native `type="date"` with visible labels "From" and "To".
- `prefers-reduced-motion`: the drawer appears without sliding, and skeletons don't shimmer.

## 11. Fixture data

`apps/web/src/api/audit/fixture.ts`:
- `listAudit` over 60 entries for the fixture tenant covering every action in `ACTION_COPY`, three actor kinds,
  four entity types, a redacted comment, and entries across 5 days; it supports every filter and returns
  `next_cursor` after 50.
- `verify` cases: `valid` (default), `broken` at entry `#1201` (set with `FixtureAuditApi({ chain: "broken" })`),
  `timeout` (throws `ApiError(503, …, "verify_timeout")`), and `partial` (`checked_from_id: 742`).
- `export` returns a small CSV blob, or throws `step_up_required` when the session's `mfa` is false, and `export_too_large` when `from` is empty.
- An "empty" instance with no entries, and a session without a read role for the permission-denied state.

## 12. Analytics and success measures

Events: `audit_viewed {filters}`, `audit_entry_opened {action, entity_type}`, `audit_verified {valid, checked}`,
`audit_exported {format, row_count}`, `audit_chain_broken_seen {first_broken_id}` (also sent as an error to S29 telemetry).
Success: a compliance officer can answer "who approved this, and against which hash" in under 30 seconds
(timed in usability tests), and every single-audit export in the pilot is produced from this screen.

## 13. Acceptance criteria

- [ ] AC1 Rows render newest first with time, who (name or short id, role), the plain-language sentence for each action in `ACTION_COPY`, and a linked record.
- [ ] AC2 Filters are written to the URL, restored on reload, and sent to `GET /v1/audit`; the record id is disabled until a record type is chosen.
- [ ] AC3 "Load older entries" appends the next page and is replaced by "Beginning of the trail" at the end.
- [ ] AC4 The detail drawer shows every detail key, renders `[redacted]` values as "redacted" with the tooltip, and shows hash and prev_hash with copy buttons.
- [ ] AC5 The integrity badge shows verified, broken (with the banner and link), partial, and timeout states.
- [ ] AC6 Export is hidden for roles other than Org admin and Compliance officer; without MFA it starts step-up; with MFA it downloads the file and then refreshes the list.
- [ ] AC7 `export_too_large`, `invalid_range` and `entity_type_required` show their messages.
- [ ] AC8 Every state in section 7 renders with the exact copy, and the permission-denied state makes no API call.
- [ ] AC9 Keyboard: `/`, ↑/↓, Enter, Esc work, and focus returns to the row when the drawer closes.
- [ ] AC10 The mobile layout shows cards and the filter sheet.
- [ ] AC11 axe finds no violations in the default, drawer-open, broken-chain and empty states.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `apps/web/src/features/audit/AuditScreen.test.tsx::renders entries as sentences` |
| AC2 | `AuditScreen.test.tsx::syncs filters with url` |
| AC3 | `AuditScreen.test.tsx::loads older entries` |
| AC4 | `AuditDetail.test.tsx::shows details redaction and hashes` |
| AC5 | `AuditScreen.test.tsx::integrity badge states` (one case per verify fixture) |
| AC6 | `ExportDialog.test.tsx::export requires role and step-up` |
| AC7 | `AuditScreen.test.tsx::validation messages` |
| AC8 | `AuditScreen.test.tsx::state copy` (one case per state) |
| AC9 | `AuditScreen.test.tsx::keyboard navigation` |
| AC10 | `AuditScreen.test.tsx::mobile layout` (matchMedia mock) |
| AC11 | `AuditScreen.a11y.test.tsx` (vitest-axe) |
| sentences | `apps/web/src/features/audit/actions.test.ts::every action has copy` |

## 15. Open questions

- Should non-admins see colleagues' names? Recommended default: yes, once S13 returns `actor_display_name`
  (C2 follow-up, S13 Decision 2). Until then only admins see names.
- Should the screen auto-refresh? Recommended default: no; a "New entries" pill appears if a refetch on
  window focus finds newer entries, and clicking it scrolls to the top.
- Should "View raw JSON" be available to everyone with read access? Recommended default: yes, it shows the same (redacted) data.
