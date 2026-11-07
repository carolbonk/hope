# SC13: Budget review (HITL-2)

| | |
|---|---|
| Route | `/frameworks/[frameworkId]/budget` (query: `edit=1`, `line={line_id}`, `sources={ref}`) |
| Feature folder | `apps/web/src/features/budget/` |
| Built by | M5 |
| Primary users | Finance director (once or twice per pursuit, 10-20 min). Development director (read, before HITL-2) |
| Can act | Edit lines, Recompute: `finance_director`, `admin`. Approve and lock / Request changes (HITL-2): roles in `gate.approver_roles` (`finance_director`), and not the person in `drafted_by` |
| Status | Draft |

## 1. Purpose and user goals

This is where Finance decides **whether the budget Hope drafted is right, compliant and
defensible**, and then signs it off (HITL-2). Users arrive from:
- the approval inbox (HITL-2 card, "Review budget");
- the workflow timeline ("Budget ready for sign-off");
- a notification;
- directly after an inline edit.

Within 5 seconds the screen must answer:
1. **Does it fit the funder's limits?** Ceiling, floor, indirect cap and unallowable costs: pass, adjusted, or fail.
2. **How much are we asking for, and what does it buy?** The request total and the category breakdown.
3. **Can I trust every number?** Each line traces to a named source (salary band, quote,
   NICRA), and any automatic adjustments are explained.

**Primary action:** Approve and lock (HITL-2).
**Secondary actions:** edit lines (quantity, effort, funding source, justification, add or
remove a line), Save and send for re-approval, Request changes, Recompute, and view a source.

## 2. Information hierarchy

1. **Limit checks and the request total.** These are the decision. They sit at the top in
   one strip: the request amount, the ceiling with the remaining headroom, and one chip per check.
2. **The approval bar.** It is sticky at the bottom, and its state is always visible: open,
   blocked and why, or locked.
3. **Line items by SF-424A category.** Each line shows its basis ("$65,000/yr × 100% effort")
   next to the amount, so the arithmetic can be read without opening anything.
   Derived rows (fringe, indirect) are indented and visually quieter.
4. **"Hope adjusted this budget".** A callout appears only when the solver changed
   something, because those are the changes a reviewer must notice.
5. **Hidden behind a click:**
   - the source drawer (full provenance), which is needed to audit, not to triage;
   - the SF-424A summary (collapsed), which is needed for the forms, not the decision;
   - the content hash, shown short with a copy button.

Money is never computed in the browser. While the user edits, changed lines show "Updates on save".

## 3. Wireframe

Desktop (>= 1024 px), review mode:

```text
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ ← Workflow   Mentor Futures: Youth Mentoring Expansion                     [↻ Recompute]  │  <- header (PageHeader)
│ DOJ OJJDP · Youth Mentoring Expansion · due Dec 3 · Version 1 · ● Draft · drafted by      │
│ Maya (Development) · updated 3 min ago                                    [✎ Edit lines]  │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│  REQUEST            CEILING        HEADROOM     │ ✓ Ceiling (adjusted)  ✓ Floor            │  <- limits strip (Card raised)
│  $249,975.60        $250,000.00    $24.40       │ ✓ Indirect ≤ 20% MTDC  ✓ No unallowables │
│  Direct $212,313.00 · Indirect $37,662.60 (20% of MTDC $188,313.00) · Cost share $0.00      │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ ⓘ Hope adjusted this budget to fit the award ceiling                                       │  <- solver callout (Card inset, info)
│   • Curriculum kits: quantity 60 → 41                                     [Undo in edit]   │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ Line items                                                     Show: (All | Changed)       │
│ Category / line                    Basis                                 Amount    Source  │
│ PERSONNEL                                                               $122,600.00        │
│   Program Director          L1     $78,000.00/yr × 1 × 20% effort       $15,600.00   ⓢ    │
│     Fringe on L1                   28% of $15,600.00                     $4,368.00    ⓢ    │
│   Program Manager           L2     $65,000.00/yr × 1 × 100% effort      $65,000.00   ⓢ    │
│     Fringe on L2                   28%                                  $18,200.00   ⓢ    │
│   Youth Mentor              L3     $42,000.00/yr × 2 × 50% effort       $42,000.00   ⓢ    │
│     Fringe on L3                   28%                                  $11,760.00   ⓢ    │
│ TRAVEL                                                                   $2,900.00         │
│   Conference trip           L4     $1,450.00/trip × 2                    $2,900.00   ⓢ    │
│ SUPPLIES                                                                 $3,485.00         │
│   Curriculum kits  ⚙ adjusted L5   $85.00/kit × 41                       $3,485.00   ⓢ    │
│ CONTRACTUAL                                                             $40,000.00         │
│   External evaluation       L7     $40,000.00 × 1 · MTDC counts $25,000 $40,000.00   ⓢ    │
│ OTHER                                                                    $9,000.00         │
│   Participant stipends      L6     $150.00 × 60 · excluded from MTDC     $9,000.00   ⓢ    │
│ INDIRECT                           20% of MTDC $188,313.00              $37,662.60   ⓢ    │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ ▸ SF-424A summary (Sections A and B)                                                       │  <- collapsed
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ HITL-2 Budget sign-off · due in 2 days · hash 4b1e9c0d…7a10 ⧉                              │  <- sticky decision bar
│ [ Comment (required to request changes)                         ]                          │
│                                        [ Request changes ]   [ ✓ Approve and lock ▶ ]      │
└───────────────────────────────────────────────────────────────────────────────────────────┘
                                   Source drawer (right, 420 px):
                                   ┌─────────────────────────────────────┐
                                   │ Program Manager            [×]      │
                                   │ hris:position:PM-02 · salary        │
                                   │ $65,000.00 per year                 │
                                   │ Source: Entered by user             │
                                   │ "2026 salary bands (HR)"            │
                                   │ Captured Oct 1, 2026 · verified by  │
                                   │ Dana (Finance)                      │
                                   │ Used by: L2 (and L2 fringe)         │
                                   └─────────────────────────────────────┘
```

Desktop, edit mode (`?edit=1`). Rows become editable, and the strip shows "Unsaved changes":

```text
│ PERSONNEL                                                                                  │
│   Program Director  L1  [hris:position:PD-01 ▾]  qty [1   ]  effort [15 ]%  [request ▾] 🔒 [🗑] │
│                        justification [Oversees the expansion and partner relations       ]  │
│                        Amount: Updates on save                                              │
│   …                                                                                        │
│ [+ Add line]                                                                               │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ 2 lines changed · [ ] Let Hope fit the budget to the limits (keeps your edited lines)      │
│ Comment [Cut PD effort to 15%, restore all 60 kits                                ]        │
│                     [ Discard ]   [ Save ]   [ Save and send for re-approval ▶ ]            │
```

Mobile (<= 640 px):
- The limits strip becomes a stacked card (request total big, then checks as a vertical list).
- Each category becomes an accordion. Lines are cards: name, basis on the second line,
  amount right-aligned, source icon.
- Edit mode opens each line in a bottom sheet instead of inline inputs.
- The decision bar stays sticky with two full-width buttons; the comment opens in a sheet.
- The source drawer is a full-screen sheet.

## 4. Content inventory

All data comes from `GET /v1/frameworks/{framework_id}/budget` (`BudgetView`) unless noted.

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Back link | `workflow.workflow_id` | "← Workflow" -> `/workflows/{id}` | Hidden if `workflow` is null |
| Project title | `project_title` | "Mentor Futures: Youth Mentoring Expansion" | One line; ellipsis at 80 characters; full title in a tooltip |
| Opportunity line | `opportunity.funder_name`, `opportunity.title`, `opportunity.application_due` | "DOJ OJJDP · Youth Mentoring Expansion · due Dec 3" | Links to `/opportunities/{id}`. The due date is red with "!" if <= 7 days |
| Version | `version` | "Version 2" | |
| Status | `status` | Badge: "● Draft", "✓ Approved and locked", "Superseded" | Icon + text. Draft is blue, Locked is green with a lock icon |
| Drafted by / updated | `drafted_by`, `updated_at` | "drafted by Maya (Development) · updated 3 min ago" | The display name comes from M0's persona list; fall back to the user id |
| Structure source | `structure_source`, `structure_fallback_reason` | Small note "Drafted from Hope's standard template" | Shown only when `template`. The fallback reason is in a tooltip |
| Request | `ledger.totals.request_minor` | "$249,975.60" | `formatMoney` with cents. The largest number on the page |
| Ceiling | `opportunity.award_ceiling` | "$250,000.00" | "Not stated" plus the warning banner when null |
| Headroom | `ceiling - request` (display only, from two server integers) | "$24.40"; "-$1,913.60 over" in red with ✕ | The only subtraction done in the browser, on integer minor units, and only for display |
| Totals line | `totals.direct_minor`, `indirect_minor`, `mtdc_base_minor`, `cost_share_minor` | "Direct $212,313.00 · Indirect $37,662.60 (20% of MTDC $188,313.00) · Cost share $0.00" | The rate comes from the `indirect-p1` line's `basis.quantity` × 100. "Cost share" is hidden when it is 0 and no cost-share check exists |
| Check chips | `ledger.cap_checks[]` | "✓ Ceiling (adjusted)", "✕ Ceiling: $1,913.60 over", "✓ Indirect ≤ 20% MTDC", "✓ No unallowables", "✕ Cost share: $4,000.00 short" | Order: ceiling, floor, indirect cap, cost share, unallowable. pass ✓ green; adjusted ✓ blue with "(adjusted)"; fail ✕ red. A tooltip shows the limit and the actual value |
| Solver callout | `solver.adjustments[]` | "Curriculum kits: quantity 60 → 41"; "Program Manager: effort 100% → 90%"; "Removed: Coffee service (unallowable)" | The line name comes from `proposed_lines[].description`. Effort is bps / 100 + "%". Hidden when empty |
| Unresolved | `solver.unresolved[]` | "Hope couldn't fit: award_floor" | Red banner (section 7) |
| Category header | grouped `ledger.line_items[].category` | "PERSONNEL $122,600.00" | SF-424A order: personnel, fringe (rows nested under personnel), travel, equipment, supplies, contractual, construction, other, indirect. Empty categories are hidden. The subtotal comes from `sf424a_mapping` |
| Line name | `line_items[].description` | "Program Manager" | `line_id` in a muted monospace chip |
| Basis | `line_items[].basis` + the source's `unit` | "$65,000.00/yr × 1 × 100% effort"; "$85.00/kit × 41"; "28% of $15,600.00" | Unit rate = `basis.unit_rate_minor`. Quantity is shown as stored (decimal string). Effort = `effort_pct_bps`/100 |
| MTDC note | the source `kind`, plus the subaward threshold | "MTDC counts $25,000"; "excluded from MTDC" | Subaward and participant-support lines only |
| Amount | `line_items[].amount_minor` | "$65,000.00" | Right-aligned, tabular numerals |
| Adjusted marker | `solver.adjustments[].line_id` | "⚙ adjusted" chip | Tooltip with before → after |
| Rate changed | `rates_changed[]` | "⚠ rate changed" chip | Tooltip: "The source rate is now $67,000.00/yr. Recompute to use it." |
| Funding source | `line_items[].funding_source` | Shown only when it isn't `request`: chip "Cost share (cash)" or "Cost share (in kind)" | |
| Unallowable | `line_items[].allowability` | "✕ Unallowable" red chip | |
| Source icon | `line_items[].basis.cost_basis_ref` -> `sources[]` | ⓢ button, `aria-label="Source for Program Manager"` | Opens the drawer. A "!" variant appears if the ref is in `missing_refs` |
| Source drawer | `sources[ref]` | Name, ref, kind, rate ("$65,000.00 per year" or "28%"), provenance source label, `source_ref` quote, captured date, verified by, "Used by" lines | Provenance labels: user_input "Entered by user", document_extraction "Extracted from document", erp_sync "Synced from accounting", system "System" |
| SF-424A summary | `ledger.sf424a_mapping` | A table of rows 6a-6k (Federal column) and 5e/5f/5g | Collapsed by default. Labels follow the SF-424A form ("a. Personnel", "b. Fringe Benefits", …) |
| Gate line | `gate.due_at`, `gate.artifact_hash` | "HITL-2 Budget sign-off · due in 2 days · hash 4b1e9c0d…7a10 ⧉" | `lib/time.countdown`. Amber at <= 24 h, red when overdue. The hash shows the first 8 and last 4 characters, with a copy button |
| Locked line | `approval` | "✓ Approved and locked by Dana (Finance) on Nov 8, 2:14 PM · hash 4b1e…" | Replaces the decision bar |
| Edit inputs | `proposed_lines[]` | quantity text input, effort % number input (0-100, step 1), funding source select, justification textarea, lock toggle 🔒 ("Keep as is when fitting") | Shown only in edit mode. Amount shows "Updates on save" for changed lines |
| Add line picker | `catalog[]` | Searchable list: "Program Manager · hris:position:PM-02 · $65,000.00/yr" | The category comes from `kind`: salary → personnel, subaward → contractual, participant_support → other, equipment → equipment; unit_cost/vendor_quote → a category select (travel, supplies, other) |

## 5. Components

- Header: `PageHeader`, with `Button` (neutral) "Recompute" and "Edit lines".
- Status and check chips: `Badge` (tones good, info, warn, bad, neutral), each with an `Icon` and text.
- Limits strip: `Card` (`glass-panel`). The request uses the large numeric style; the chips sit in a wrapping row.
- Solver callout and banners: `Card` (`glass-inset`) with an info or warn icon. Errors use `ErrorNotice`.
- Line items: `Table` / `Th` / `Td` / `Tr`, with category rows as `<tr>` headers
  (`scope="rowgroup"`) and nested fringe rows indented 24 px.
- Edit controls: `TextField` (quantity, effort), `SelectField` (funding source, category,
  cost basis), `TextArea` (justification, comment). The lock toggle and the "Fit" checkbox
  are `Button`s with `glass-active` when on (`aria-pressed`).
- Add line: `Modal` with a search `TextField` and a list.
- Source details: the shared `Drawer` from M0 (side sheet; full screen on mobile).
- Decision bar: sticky `Card` (`glass-panel`), `TextArea`, `Button` neutral "Request
  changes", `Button` primary "Approve and lock". Step-up uses `StepUpDialog` (see M5
  Requests to M0, item 8).
- Toasts: M0's `Toast`.
- New in the feature folder:
  - `BudgetReview.tsx` (screen);
  - `LimitsStrip.tsx`;
  - `LineTable.tsx`;
  - `LineEditor.tsx`;
  - `AddLineDialog.tsx`;
  - `SourceDrawer.tsx`;
  - `DecisionBar.tsx`;
  - `Sf424aSummary.tsx`;
  - `format.ts` (basis strings, built only from server integers).

No new shared primitives.

## 6. Interactions

1. **Open.** `GET /v1/frameworks/{id}/budget`. `?line=L5` scrolls to and highlights L5 for
   2 s (no animation with reduced motion). `?sources=hris:position:PM-02` opens the drawer.
2. **View source.** Click ⓢ, or Enter on a focused ⓢ button. The URL gets `?sources={ref}`,
   the drawer opens, and Esc closes it and returns focus to the button.
3. **Edit lines** (visible when `permissions.can_edit`). Press `e` or click "Edit lines",
   which sets `?edit=1`.
   - Inputs validate locally: quantity must match `^\d+(\.\d{1,4})?$`; effort must be 0-100.
     Errors show under the field and disable Save.
   - Changed lines get a "changed" dot. Their amounts show "Updates on save".
   - **Remove** (🗑) marks the line struck-through with "Undo". Removed lines are dropped
     from the PUT body.
   - **Add line** opens the picker. Choosing a record adds a line with a new `line_id`
     (`L{n+1}`), quantity 1, and effort 100% for personnel. It is focused for editing.
   - **Lock** toggles `locked`.
   - **Fit checkbox** sets `fit: true`.
4. **Save.** `PUT /v1/frameworks/{id}/budget/lines` with `{base_hash: content_hash, fit, comment, lines: <all non-removed lines>}`.
   - While pending, the buttons are disabled and Save shows a spinner.
   - **200 `changed: true`:** leave edit mode, re-render from the response, toast
     "Budget saved: version 2. Request now $251,913.60." If `gate` is open, also show the
     banner "The open sign-off was for version 1. Send it back for re-approval."
   - **200 `changed: false`:** toast "No changes to save."
   - **422 `budget_input_invalid`:** stay in edit mode, show each error under its line
     (`line_id`) or in a top banner (`line_id: null`), and focus the first error.
   - **409 `stale_artifact`:** show the modal "This budget changed since you opened it."
     with buttons [Reload] and [Copy my changes]. Reload refetches; Copy keeps the edits as
     JSON on the clipboard.
   - **409 `framework_locked`:** show the locked banner and leave edit mode.
   - **409 `invalid_state`:** "Budget can't be edited while the pursuit is in {state}." and leave edit mode.
   - **403 `forbidden`:** "Only Finance can edit the budget." and leave edit mode.
5. **Save and send for re-approval** (only when `gate` is open and the user has an approver role).
   1. Run the Save call.
   2. On `changed: true`, call `POST /v1/workflows/{workflow_id}/signals/HITL-2` with
      `{decision: "request_changes", artifact_hash: <gate.artifact_hash from before the save>, comment: "Budget edited in Hope: {comment}"}`
      and the step-up header (step 8).
   3. Toast: "Saved and sent back. Hope will re-check the budget and reopen sign-off."
   4. Refetch every 3 s for up to 60 s, until `gate.artifact_hash == content_hash`. Then
      show the toast "Sign-off reopened for version 2."
   - If the signal fails with 409 `stale_artifact`, refetch and show "Sign-off was already updated."
6. **Discard.** Asks "Discard 2 unsaved changes?" when the form is dirty, then leaves edit
   mode. Esc in edit mode does the same.
7. **Recompute.** `POST /v1/frameworks/{id}/recompute`.
   - 200 `changed: true`: toast "Recomputed with current rates: version 3."
   - 200 `changed: false`: toast "Already up to date."
   - 422 `budget_input_invalid`: banner listing the errors (for example "a source was removed").
   - 409 `framework_locked`: the locked banner.
8. **Approve and lock** (enabled when `permissions.can_decide`).
   1. Open `StepUpDialog`.
   2. On verify, call `POST /v1/workflows/{workflow_id}/signals/HITL-2` with
      `{decision: "approve", artifact_hash: gate.artifact_hash, comment}` and the header `X-Hope-MFA: true`.
   - 202: toast "Budget approved and locked."; refetch until `status` is `approved_locked` (3 s interval, 30 s max).
   - 409 `stale_artifact`: "This budget changed since sign-off was requested. Review the latest version." Then refetch.
   - 403 `forbidden`: "You can't approve this gate." The bar shows `decide_blocked_reason`.
9. **Request changes.** The comment is required ("Add a comment so the team knows what to change.").
   Then the same signal with `decision: "request_changes"`. Toast: "Sent back to planning."
10. **Keyboard.**
    - `e`: edit.
    - `Ctrl+S` / `Cmd+S`: save in edit mode.
    - `Esc`: close the drawer, or discard edits.
    - `?`: shortcut help.
    - In the table, ↑/↓ moves between lines, and Enter opens the source.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading | Header skeleton (2 lines), strip skeleton (3 numbers + 4 chips), 8 table row skeletons |
| Not found (404) | "We couldn't find this budget. It may belong to a pursuit that was removed." + "Go to workflows" |
| Draft, no open gate (`Planning`) | Info bar in the decision area: "Sign-off isn't open yet. Hope is still checking this budget." Edit is available |
| Gate open, user can decide | Decision bar enabled (section 3) |
| User drafted it (`you_drafted_this`) | Decision bar disabled: "You prepared this version, so another Finance approver must sign it off." |
| Not an approver | "Sign-off needs the Finance director role." (Edit hidden if `can_edit` is false) |
| Locked | Green bar: "✓ Approved and locked by {name} on {date}. This budget can't be changed." Edit and Recompute are hidden |
| Over ceiling (check `fail`) | Red banner: "The request is {amount} over the funder's ceiling. Edit lines, or let Hope fit the budget." + [Edit lines] |
| Solver unresolved | Red banner: "Hope couldn't make this budget meet: {rules}. Adjust the lines manually." (rule labels: award_floor "the award floor", cost_share_ratio "the cost-share requirement") |
| No ceiling stated (`warnings` has `no_award_ceiling`) | Amber banner: "This opportunity doesn't state an award ceiling, so the ceiling check is skipped. Confirm the ceiling in the RFP before approving." |
| Template fallback | Muted note under the title: "Drafted from Hope's standard template." The tooltip shows the reason, e.g. "The AI draft didn't pass checks." |
| Rates changed | Amber banner: "{n} source rates changed since this budget was computed." + [Recompute] |
| Missing source | Red banner: "{n} lines use a source that no longer exists. Edit or remove them." |
| Unsaved edits on navigation | Browser confirm: "You have unsaved budget changes. Leave anyway?" |
| `budget_input_invalid` | Per-line red text with the server message; top banner "Fix {n} problems to save." |
| `stale_artifact` | Modal: "This budget changed since you opened it." [Reload] [Copy my changes] |
| Error (network / 5xx) | "We couldn't load the budget. Try again." + Retry. On save errors the edits are kept |
| Offline | Amber strip: "You're offline. Changes can't be saved until you reconnect." Save is disabled |
| Empty ledger (no direct lines) | "This budget has no lines yet." + [Add line] (edit roles), or "Ask Finance to build the budget." |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount, Reload, after a decision | `GET /v1/frameworks/{id}/budget` | everything in `BudgetView` | No stale cache; refetch on window focus if older than 60 s and not in edit mode |
| Save | `PUT /v1/frameworks/{id}/budget/lines` | the response replaces the view | |
| Save and send | `PUT …/budget/lines`, then `POST /v1/workflows/{workflow_id}/signals/HITL-2` | `gate.artifact_hash` from before the save | Poll the GET every 3 s, up to 60 s |
| Recompute | `POST /v1/frameworks/{id}/recompute` | the response replaces the view | |
| Approve / Request changes | `POST /v1/workflows/{workflow_id}/signals/HITL-2` `{decision, artifact_hash, comment}` | `request_id` in the toast detail | Poll the GET every 3 s, up to 30 s |
| App shell | `GET /v1/me` | `user_id`, `roles` (enables controls; the server is the authority) | Session |

The web client is `apps/web/src/api/budget/`:
- `types.ts` mirrors `BudgetView`;
- `http.ts` implements `getBudget(id)`, `saveLines(id, body)`, `recompute(id)`,
  `signalBudget(workflowId, body, {stepUp})`;
- `fixture.ts` holds the cases in section 11.

## 9. Responsive behaviour

- **>= 1280 px:** full table. The drawer overlays the right side, and the decision bar spans the content width.
- **1024-1279 px:** the Basis column wraps to two lines, and the Source column becomes an icon only.
- **641-1023 px:** the limits strip wraps into two rows (numbers, then chips). The Basis
  column moves under the line name, and edit inputs stack in two columns.
- **<= 640 px:** the layout in section 3 (cards, category accordions, a bottom sheet per
  edited line, a sticky two-button decision bar, a full-screen drawer). The SF-424A summary
  becomes a two-column list.

## 10. Accessibility

- **Table semantics.** The table is a real `<table>` with a caption ("Budget line items,
  version 2"). Category rows use `<th scope="rowgroup">` and columns use `<th scope="col">`.
  Amounts have `aria-label`s with the full value ("65,000 dollars").
- **Not colour alone.** Every check chip, status, unallowable and rate-changed marker has an
  icon and text.
- **Contrast.** Red and green are AA on the liquid-glass surface. Cards and inputs have a
  1 px border at 3:1 or more.
- **Tab order:** back link → title links → Recompute → Edit → limits chips (each focusable,
  with its tooltip shown on focus) → solver callout → table rows and source buttons →
  SF-424A toggle → decision bar (comment, Request changes, Approve).
- **Edit mode.** Each input has a visible label ("Quantity for Curriculum kits", "Effort %
  for Program Manager"). Errors are linked with `aria-describedby`. On a failed save, focus
  moves to the first error.
- **Drawer and modals.** They use `role="dialog"`, `aria-labelledby` and a focus trap. Esc
  closes them, and focus returns to the trigger.
- **Live regions.** Save, recompute and decision results, and "Sign-off reopened", are
  announced in an `aria-live="polite"` region. Blocking errors use `role="alert"`.
- **Reduced motion.** With `prefers-reduced-motion`, there is no row highlight animation,
  no drawer slide, and spinners become a static "Working…" label.

## 11. Fixture data

`api/budget/fixture.ts` provides one `BudgetView` per case. Amounts match the M5 golden
demo budget, so the screen and the API agree.

| Case | Key facts |
|---|---|
| `fitted` (default) | Version 1, draft. Request $249,975.60, ceiling $250,000.00. `award_ceiling` adjusted (L5 60 → 41). Gate open; `can_decide: true`; `can_edit: true` |
| `over_ceiling` | Engine-only: L5 = 60, request $251,913.60, `award_ceiling` fail ($1,913.60 over). No adjustments |
| `drafter` | Same as `fitted`, but `drafted_by` = the current user; `decide_blocked_reason: "you_drafted_this"` |
| `no_gate` | Workflow in `Planning`, `gate: null` |
| `locked` | `status: approved_locked`, `approval` by "demo-finance" on 2026-11-08T14:14:00Z; `can_edit: false` |
| `rates_changed` | `rates_changed: ["L2"]`; source PM-02 is now $67,000.00 |
| `missing_ref` | `missing_refs: ["quote:travel:conf-trip"]` |
| `no_ceiling_template` | `award_ceiling: null`, `warnings: ["no_award_ceiling"]`, `structure_source: "template"`, `structure_fallback_reason: "AI draft failed validation twice"` |
| `unresolved` | `solver.feasible: false`, `unresolved: ["award_floor"]` |
| `cost_share` | Cost-share line L8 (`cost_share_in_kind`, volunteer mentors), `cost_share_ratio` check fail, $4,000.00 short |
| `empty` | No direct lines |
| Save responses | `saveLines` returns `changed: true` (version 2, request $251,913.60), or by flag: `changed: false`; 422 `budget_input_invalid` on L8; 409 `stale_artifact`; 409 `framework_locked`; 409 `invalid_state` (`Drafting`); 403 |
| Errors | `getBudget` 404 and a network error |

## 12. Analytics and success measures

Events (logged through the app's existing analytics hook, or `console.debug` until there is one):
- `budget_viewed {framework_id, version, status, checks_failing}`
- `budget_source_opened {ref, kind}`
- `budget_edit_started`
- `budget_saved {changed, lines_changed, fit}`
- `budget_save_failed {code}`
- `budget_recomputed {changed}`
- `budget_decision {decision, version}`

Success: the median time from the HITL-2 request to a decision is under 1 business day; at
least 90% of approved budgets have no `fail` checks at approval; and no budget is approved
with `missing_refs` (guarded in the UI).

## 13. Acceptance criteria

- [ ] AC1 The default fixture renders the request, ceiling, headroom and totals line, one chip per check with icon and text, and the solver callout.
- [ ] AC2 Lines are grouped in SF-424A order with category subtotals, basis strings ("$65,000.00/yr × 1 × 100% effort"), amounts, nested fringe rows, the indirect row and MTDC notes.
- [ ] AC3 The source drawer opens from ⓢ with the provenance label, `source_ref`, captured date, verified-by and "Used by"; `?sources=` deep-links to it, and focus returns on close.
- [ ] AC4 Edit mode shows inputs only for `can_edit`; invalid quantity or effort blocks Save; changed lines show "Updates on save" and no client-computed amount.
- [ ] AC5 Save sends the exact PUT body (all lines, `base_hash`, `fit`, `comment`) and re-renders from the response; `changed: false` shows "No changes to save."
- [ ] AC6 422 `budget_input_invalid` maps each error to its line, focuses the first one, and keeps the edits.
- [ ] AC7 409 `stale_artifact`, `framework_locked`, `invalid_state` and 403 each show their exact copy from section 7.
- [ ] AC8 "Save and send for re-approval" calls PUT, then the HITL-2 signal with `request_changes` and the pre-save gate hash, and polls until the gate hash matches the new `content_hash`.
- [ ] AC9 Approve and lock opens step-up, sends `approve` with `gate.artifact_hash` and `X-Hope-MFA: true`, and shows the locked state after refetch.
- [ ] AC10 Request changes requires a comment.
- [ ] AC11 The decision bar shows the right disabled copy for `you_drafted_this`, `not_an_approver`, `no_open_gate` and `locked`.
- [ ] AC12 Banners render for over-ceiling, unresolved, no ceiling, template fallback, rates changed and missing source, with the exact copy.
- [ ] AC13 Recompute shows "Recomputed with current rates: version 3." or "Already up to date."
- [ ] AC14 Keyboard: `e`, `Ctrl+S`, Esc and ↑/↓ work.
- [ ] AC15 Mobile (<= 640 px) shows category accordions, line cards, the bottom-sheet editor and the sticky decision bar.
- [ ] AC16 axe finds no violations in the default, edit mode, drawer-open and locked states.
- [ ] AC17 Playwright demo flow (fixture API): open the `over_ceiling` fixture → edit L5 to 41 → Save → approve as a different persona → locked.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1, AC12 | `apps/web/src/features/budget/BudgetReview.test.tsx::renders limits, checks and banners` |
| AC2 | `features/budget/LineTable.test.tsx::groups lines with basis and fringe` |
| AC3 | `features/budget/SourceDrawer.test.tsx::shows provenance and deep link` |
| AC4, AC6 | `features/budget/LineEditor.test.tsx::validates and maps server errors` |
| AC5 | `BudgetReview.test.tsx::save sends full body and rerenders` |
| AC7 | `BudgetReview.test.tsx::conflict copy` (one case per code) |
| AC8 | `BudgetReview.test.tsx::save and send for reapproval` (fake timers) |
| AC9, AC10, AC11 | `features/budget/DecisionBar.test.tsx::approve, request changes, blocked reasons` |
| AC13 | `BudgetReview.test.tsx::recompute toasts` |
| AC14 | `BudgetReview.test.tsx::keyboard shortcuts` |
| AC15 | `BudgetReview.test.tsx::mobile layout` (matchMedia mock) |
| AC16 | `features/budget/BudgetReview.a11y.test.tsx` (vitest-axe) |
| AC17 | `apps/web/e2e/budget.spec.ts::edit and approve flow` (Playwright, fixture API) |
| client | `apps/web/src/api/budget/http.test.ts::paths, bodies and problem codes` |

## 15. Open questions

- **Show an approximate live total while editing?** Recommended default: no. Money is only
  computed by the engine; show "Updates on save".
- **Should Save automatically send the budget back for re-approval when a gate is open?**
  Recommended default: no. Offer "Save" and "Save and send for re-approval" side by side, so
  Finance can make several saves before re-submitting.
- **Let reviewers edit justifications without creating a new version?** Recommended
  default: no. Justifications are part of the hashed framework, so any edit is a new version.
- **Show cost basis for lines not in this budget?** Recommended default: only in the "Add
  line" picker (`catalog`).
