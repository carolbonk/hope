# SC22: Application package and submission

| | |
|---|---|
| Route | `/packages/[packageId]` (query: `file` = the name of the file being previewed), plus `/packages/new?framework={frameworkId}` (builds the package, then redirects) |
| Feature folder | `apps/web/src/features/packages/` |
| Built by | M7 |
| Primary users | Development director, once per application at the end of the process. AOR (`aor`), once per application to authorize. Executive director, occasionally, to check status |
| Can act | Authorize (HITL-5): roles in the gate's `approver_roles` (`aor`), with the step-up dialog. Rebuild: `development_director`, `program_director`, `executive_director`, `aor`. Mark submitted: `aor`, `development_director`. Download: anyone signed in, once approved |
| Status | Draft |

## 1. Purpose and user goals

This is the last screen of the demo. The team arrives here from:
- the workflow timeline (SC08), at the `Packaging` / `AwaitingSubmissionAuth` step
- the approval inbox (SC05/SC06), when a HITL-5 request links here
- the dashboard's "My approvals"
- SC19's "Build package" (through `/packages/new`)

The job: check that the package is complete, get the AOR's authorization, download the zip,
submit it yourself in Grants.gov or the funder portal, and then record the confirmation number.

Within 5 seconds the screen must answer:
1. **Is the package ready, and is it authorized?** This is the HITL-5 status.
2. **What's in it?** The file list, with page counts and the amount requested.
3. **What do I do next?** Exactly one highlighted next step: Authorize, Download, Mark
   submitted, or Done.

**Primary action** (it depends on the state):
- `pending` + AOR: **Authorize submission**
- `approved`: **Download package**, then **Mark submitted**
- `submitted`: none (the confirmation is shown)

**Secondary actions:** preview a file, rebuild, copy the confirmation number.

## 2. Information hierarchy

1. **Status stepper and next step.** "Built ✓ → Authorized (HITL-5) → Submitted" comes
   first, with a single call-to-action card under it. This screen is about finishing, so
   the next step leads.
2. **What you're submitting.** The opportunity title and number, the funder, the due date
   with a countdown, and the request / cost share / total amounts. These are the facts an
   AOR has to confirm before authorizing.
3. **The files.** A list with name, description, pages and size. Each file has a Preview.
4. **Integrity details.** The package hash, the zip SHA-256 and who built it, collapsed
   under "Technical details". They matter for audit, not for the decision.

Deliberately hidden: the manifest JSON (it's a file in the list), raw hashes in the main
view (shown truncated, in full under the details), and the comment history of the approval
(it's on SC06).

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ ‹ Workflow                                                                                   │
│ Application package                                                                          │
│ Youth Mentoring Expansion · O-OJJDP-2026-0042 · OJJDP                                        │  <- PageHeader
│ Due Dec 8, 2026 11:59 PM ET · internal deadline Dec 5 (28 days)                              │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│  ● Built ───────── ◐ Authorized (HITL-5) ───────── ○ Submitted                               │  <- stepper (Card raised)
│  Nov 7, 3:20 PM      Waiting for the AOR                                                     │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌ Next step ──────────────────────────────────────────────────────────────────────────────┐ │
│ │ 🛡 Authorize submission                                                                   │ │  <- next-step card (Card raised,
│ │ You're approving these exact files (package sha256:4f1b…c8e). Any change after this      │ │     accent border)
│ │ voids the approval.                                                                       │ │
│ │ Comment (optional) [______________________________________________]                      │ │
│ │                                                         [ Authorize submission ▶ ]       │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────┬──────────────────────────────────────────────┤
│ Files (6)                                    │ Amounts                                      │
│ ▤ Application summary (SF-424 layout) 1 p    │  Federal request     $250,000                │
│   01-summary-sf424.pdf · 21 KB  [Preview]    │  Cost share           $50,000                │
│ ▤ Budget (SF-424A layout)             2 p    │  Total project       $300,000                │
│   02-budget-sf424a.pdf · 29 KB    [Preview]  │                                              │
│ ▤ Project summary                     1 p    │ Technical details ▸                          │
│ ▤ Statement of need                   3 p    │  Package hash  sha256:4f1b…c8e [Copy]        │
│ { } Manifest and hashes                      │  Zip SHA-256   9a7d…0c        [Copy]         │
│ ✎ How to submit (README)                     │  Built by Dana Okafor · Nov 7, 3:20 PM        │
│                                   [Rebuild]  │  Framework v3                                │
└──────────────────────────────────────────────┴──────────────────────────────────────────────┘
                     Preview (Drawer, 640 px): PDF in an <iframe>, title and [Open in new tab]
```

Next-step card, after authorization (`approved`):

```text
┌ Next step ─────────────────────────────────────────────────────────────────────────────────┐
│ ✓ Authorized by Ana Ruiz (AOR) on Nov 7, 4:05 PM                                            │
│ 1. Download the package          [ ⬇ Download package (180 KB) ]                            │
│ 2. Submit it on Grants.gov (Hope does not submit for you)   [Open Grants.gov Workspace ↗]   │
│ 3. Record the confirmation                    [ Mark submitted… ]                           │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

Mark-submitted dialog (`Modal`):

```text
┌ Mark as submitted ────────────────────────────────────────── [×] ┐
│ Confirmation number *  [ GRANT14327793            ]              │
│   The tracking number Grants.gov or the funder gave you.         │
│ Submitted via *        ( Grants.gov ▾ )                          │
│ Submitted at           [ 2026-11-07 ] [ 16:02 ]  ET              │
│ Note                   [________________________]                │
│                                [ Cancel ]  [ Mark submitted ▶ ]  │
└──────────────────────────────────────────────────────────────────┘
```

Mobile (<= 640 px):
- Single column. The stepper becomes vertical.
- The next-step card is sticky at the bottom as an action bar (primary button full width,
  with a "Details" toggle).
- Files become a list of cards. The amounts card and technical details become accordions
  under the files.
- Preview opens the PDF in a new tab instead of the drawer.

## 4. Content inventory

| Element | Source (`GET /v1/packages/{id}` unless noted) | Format and example | Rules |
|---|---|---|---|
| Opportunity line | `opportunity_title`, `opportunity_number`, `funder_name` | "Youth Mentoring Expansion · O-OJJDP-2026-0042 · OJJDP" | The title truncates at 80 characters, with the full title in a tooltip |
| Due line | `application_due`, `internal_due` | "Due Dec 8, 2026 11:59 PM ET · internal deadline Dec 5 (28 days)" | `countdown()` on `internal_due`: red "!" when 3 days or less, amber at 7 or less, "Passed" in red if past. The due time is shown in the deadline's own timezone |
| Stepper: Built | `built_at`, `status` | "● Built · Nov 7, 3:20 PM" | Always done unless `superseded` |
| Stepper: Authorized | `authorization.status`, `decided_by`, `decided_at` | not_requested "○ Not requested yet", pending "◐ Waiting for the AOR", stale "⚠ Needs a new approval request", held "⊘ On hold", approved "✓ Authorized · Ana Ruiz" | Icon + text. Never colour alone |
| Stepper: Submitted | `submission` | "✓ Submitted · GRANT14327793" or "○ Not yet" | |
| Next-step card | derived from `status`, `authorization.status`, `can.*` | See section 7 for the copy per state | Exactly one primary button at a time |
| Package hash | `content_hash` | "sha256:4f1b…c8e" (first 4 and last 3 characters) | Full value in the details and in the copy action |
| Files | `files[]` (`title`, `name`, `pages`, `bytes`, `kind`) | "Budget (SF-424A layout) · 2 p · 29 KB" | Server order (sorted by name). Icons: summary/budget/narrative ▤, manifest { }, readme ✎. `bytes` via `Intl.NumberFormat` (KB/MB) |
| Amounts | `totals.request`, `cost_share`, `project_total` | "$250,000" | `formatMoney()` from `lib/money.ts`. Cost share shows "None" when it's 0 |
| Authorized by | `authorization.decided_by`, `decided_at` | "Authorized by Ana Ruiz (AOR) on Nov 7, 4:05 PM" | The display name comes from the `/v1/me` cache if it's the current user, otherwise the user id |
| Approver roles | `authorization.approver_roles` | "Waiting for: Authorized representative (AOR)" | Role labels from the M0 `Role` enum map |
| Submission | `submission.confirmation_number`, `channel`, `submitted_at`, `submitted_by`, `note` | "Submitted on Grants.gov · GRANT14327793 · Nov 7, 4:02 PM by Dana Okafor" | Has a copy button |
| Superseded banner | `superseded_by` | "A newer package replaced this one." + "Open the current package" | Shown at the top, and all actions are disabled |
| Workspace link | `opportunity_number` | "Open Grants.gov Workspace ↗" -> `https://www.grants.gov/` (new tab) | Shown only when the channel is `grants_gov`, otherwise "Open the funder's portal" with no link |

## 5. Components

- Header: `PageHeader` with a back link to `/workflows/{workflow_id}` when `workflow_id` is set, otherwise to `/`.
- Stepper: a new feature-local `PackageStepper` on a `Card` (`glass-panel`), as an `<ol>` with an icon and label per step.
- Next-step card: `Card` (`glass-panel`, 2 px accent border) with `TextArea` and `Button` (primary).
- Step-up dialog: `Modal` with a 6-digit `TextField` (demo: any 6 digits). This is a copy of the approvals `StepUpDialog` until M0 moves it into `components/ui` (M7, Requests to M0, 6).
- Mark-submitted dialog: `Modal` with `TextField`, `SelectField`, a date and a time `TextField`, and `TextArea`.
- File list: `Card` (`glass-inset`) with a list of rows. Each row has a `Button` (ghost) "Preview".
- Preview: the `Drawer` (M0, `components/ui`) holding an `<iframe title="{file title}">`, plus "Open in new tab".
- Amounts and details: `Card` (`glass-inset`), with `<details>` for the technical details.
- Notices: `Toast` (M0) for success; `ErrorNotice` / `SuccessNotice` / `Loading` / `EmptyState` from `States.tsx`.
- Badges: `Badge` with tone and icon for the status labels.

## 6. Interactions

1. **Open the page.** `GET /v1/packages/{packageId}`. If the URL has `?file=02-budget-sf424a.pdf`,
   that preview opens too.
2. **`/packages/new?framework={frameworkId}`.** On mount it calls
   `POST /v1/frameworks/{frameworkId}/package` and shows "Building your package… this takes a
   few seconds."
   - 200 or 201: `router.replace("/packages/{package_id}")`.
   - 422 `package_invalid`: the page "We couldn't build the package" lists each `errors[]`
     entry with the error copy from section 7, plus links ("Fix the budget" ->
     `/frameworks/{id}/budget`, "Fix the draft" -> `/frameworks/{id}/draft`, "Fix the
     profile" -> `/profile`).
   - 404: "This framework doesn't exist."
   - 409 `framework_superseded`: "A newer version of this proposal exists." with a link to
     the workflow.
   - 403: the permission copy.
3. **Preview a file.** Click Preview or press Enter on a row. This opens the drawer with
   `<iframe src="/v1/packages/{id}/files/{name}">`, which carries the PREVIEW overlay, and
   sets `?file=`. Esc closes the drawer and clears `?file`. "Open in new tab" opens the same URL.
4. **Authorize submission** (shown only when `can.authorize`).
   1. Click "Authorize submission". The step-up dialog opens: "Confirm it's you. Enter the
      6-digit code from your authenticator app." (demo: any 6 digits).
   2. Verify sends `POST /v1/packages/{id}/authorize` with the header `X-Hope-MFA: true` and
      the body `{manifest_hash: content_hash, channel: "grants_gov" | other channel, comment}`.
      While it's pending the button reads "Authorizing…".
   3. Results:
      - 202: Toast "Submission authorized". Refetch, and the next-step card moves to the
        approved state.
      - 409 `stale_artifact`: `ErrorNotice` "This package changed after the approval request
        was opened. Reload to see the current package." + Reload.
      - 409 `authorization_not_requested`: "There's no open approval request for this
        package yet. It's created when the workflow reaches the submission step."
      - 409 `gate_closed`: "This request was already decided." + refetch.
      - 403 `step_up_required`: the dialog stays open with "Verification failed. Try again."
      - 403 `forbidden`: "Only the authorized representative can authorize submission."
5. **Download package** (shown when `can.download`). This is an `<a href="/v1/packages/{id}/download" download>`,
   so the browser handles the file. The page logs the analytics event, then shows the hint
   "Downloaded. Next: submit it on Grants.gov, then mark it submitted here."
   - 409 (when the client fetch fallback is used for the error state): "The package isn't
     authorized yet."
6. **Mark submitted** (shown when `can.mark_submitted`). The dialog opens with:
   - channel defaulted from the opportunity (`grants_gov` when `opportunity_number` comes
     from Grants.gov)
   - `submitted_at` defaulted to now, in local time

   Client validation:
   - "Enter the confirmation number."
   - "Use letters, numbers, dots, dashes or underscores (3-64 characters)."
   - "The submission time can't be in the future."
   - For Grants.gov numbers that don't start with "GRANT", a soft hint: "Grants.gov
     tracking numbers usually start with GRANT. Check it before saving." It doesn't block.

   Submit sends `POST /v1/packages/{id}/mark-submitted` with
   `{confirmation_number, channel, submitted_at (ISO with offset), note}`.
   - 200: the dialog closes, Toast "Marked as submitted", the stepper finishes, and the
     card shows the confirmation.
   - 409 `already_submitted`: "This package was already marked submitted with
     {confirmation_number}." + refetch.
   - 409 `authorization_required`: "The package needs HITL-5 authorization first."
   - 409 `stale_artifact`: as in step 4.
   - 422 `invalid_confirmation_number` / `invalid_submitted_at`: an inline error on that field.
7. **Rebuild** (shown when `can.rebuild`, and only before submission). A confirm modal says
   "Rebuild the package? If anything changed, this creates a new package and any approval
   for the old one stops applying." Confirm sends `POST /v1/frameworks/{framework_id}/package`.
   - 200 (identical): Toast "Nothing changed; this package is current."
   - 201 (new): navigate to the new package with Toast "New package built. It needs a new
     authorization."
   - 422: show the errors list as in step 2.
8. **Copy.** The hash, zip SHA-256 and confirmation number copy to the clipboard and
   announce "Copied".
9. **Keyboard.** `d` downloads when it's enabled. `a` opens authorize when it's enabled. On
   a focused file row, `p` previews. Esc closes the dialogs and the drawer.
10. **Polling.** While `authorization.status` is `pending` or `not_requested`, refetch every
    15 s (paused when the tab is hidden), so the screen updates when the AOR approves
    somewhere else.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading | Stepper skeleton (3 dots), card skeleton and 4 file-row skeletons, with `role="status"` "Loading package…" |
| Building (`/packages/new`) | "Building your package… this takes a few seconds." with a spinner (static under reduced motion) |
| Build failed (422) | Title "We couldn't build the package". Items, one per error: `missing_ein` "Add your EIN to the agency profile."; `missing_sections` "Draft the narrative first."; `missing_title` "Give the project a title in the framework."; `unfilled_placeholder:{section}:{token}` "The section “{section}” still has an unfilled value ({token})."; `ledger_mismatch:{category}` "The budget totals don't add up for {category}. Recompute the budget."; `package_too_large` "The package is over 20 MB." |
| Not requested | Card: "Waiting for the approval request. The workflow asks the authorized representative to approve this package when it reaches the submission step." |
| Pending, current user is an approver | Card: "Authorize submission. You're approving these exact files (package {short hash}). Any change after this voids the approval." + button |
| Pending, current user isn't an approver | Card: "Waiting for the authorized representative (AOR) to approve this package." + "Copy link" |
| Stale | Warning card: "The package changed after the approval request was opened. The workflow will ask for a new approval." |
| Held | Card: "The authorized representative put this package on hold." + their comment, if any |
| Approved | The approved card from section 3 |
| Submitted | Success card: "Submitted on {channel label} · {confirmation number} · {date} by {user}. Hope recorded this; the funder's confirmation email is your official receipt." |
| Superseded | Banner: "A newer package replaced this one." + "Open the current package". All actions are hidden |
| Not found (404) | "This package doesn't exist." + "Back to dashboard" |
| Error (5xx / network) | "We couldn't load the package. Try again." + Retry |
| Permission (no build role, on Rebuild) | The Rebuild button is hidden. A direct 403 shows "You don't have permission to rebuild packages." |
| Offline | Banner "You're offline." All action buttons are disabled with the tooltip "You're offline" |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount, after any action, poll | `GET /v1/packages/{id}` | all `PackageView` fields | No cache. Poll every 15 s while authorization is `pending` or `not_requested` |
| `/packages/new` mount, Rebuild | `POST /v1/frameworks/{framework_id}/package` | `package_id`, `errors` | — |
| Preview | `GET /v1/packages/{id}/files/{name}` (iframe src) | binary | Browser cache keyed by `content_hash` (ETag) |
| Authorize | `POST /v1/packages/{id}/authorize` | `request_id`, `tracking_id` | Then refetch |
| Download | `GET /v1/packages/{id}/download` | binary | — |
| Mark submitted | `POST /v1/packages/{id}/mark-submitted` | `PackageView` | Replaces the state. Invalidates the dashboard |
| App shell | `GET /v1/me` | `roles`, `display_name`, `user_id` | Session |

Every field above is in the M7 `PackageView`. `can.*` is computed by the server, so the UI
never reimplements the role rules. It only hides what `can` says is off.

## 9. Responsive behaviour

- >= 1280 px: two columns under the next-step card (files 3/5, amounts and details 2/5). The preview drawer is 640 px.
- 1024-1279 px: the same, with a 520 px drawer.
- 641-1023 px: one column (stepper, card, files, amounts, details). Preview is a full-width drawer.
- <= 640 px: the vertical stepper, a sticky bottom action bar, file cards, accordions, and preview in a new tab. The dialogs become full-screen sheets.

## 10. Accessibility

- Tab order:
  1. back link
  2. next-step card (comment, then the primary button)
  3. file rows (each one focusable, with Preview)
  4. Rebuild
  5. amounts
  6. details toggle
- The stepper is an `<ol aria-label="Package progress">`. Each step has `aria-current="step"`
  when it's active, and its text state is "done", "current" or "not started".
- Dialogs have `role="dialog"` and `aria-labelledby`. Focus starts on the first input and
  returns to the trigger button on close. The step-up input has
  `inputmode="numeric" autocomplete="one-time-code"`.
- Status changes are announced in an `aria-live="polite"` region ("Submission authorized",
  "Marked as submitted", "Copied"). Errors use `role="alert"`.
- The iframe has a `title`, and the drawer has a visible "Open in new tab" link because
  some screen readers struggle with embedded PDFs.
- Status always uses icon + text. Contrast is AA, and every card has a 1 px border with at
  least 3:1 contrast.
- With `prefers-reduced-motion`: no drawer slide, and the spinner becomes static.

## 11. Fixture data

`apps/web/src/api/packages/fixture.ts` exports `FixturePackagesApi`. The packages (dates
relative to `FIXED_NOW`, all with the 6 files from the M7 example):

1. `pkg-pending` (built): authorization `pending`, `approver_roles ["aor"]`, due in 28 days.
2. `pkg-not-requested`: authorization `not_requested`.
3. `pkg-approved`: authorization `approved` by "Ana Ruiz" 1 h ago, `can.download` and `can.mark_submitted` true.
4. `pkg-submitted`: submission `GRANT14327793` on `grants_gov`.
5. `pkg-stale`: authorization `stale`.
6. `pkg-held`: authorization `held`, with the comment "Wait for the board vote on Thursday".
7. `pkg-superseded`: `superseded_by: "pkg-pending"`.
8. `pkg-urgent`: approved, internal due in 2 days (red countdown).

Build fixtures for `/packages/new`:
- `framework=fw-ok` returns 201 `pkg-pending`.
- `framework=fw-invalid` returns 422 with `["missing_ein", "unfilled_placeholder:budget-narrative:{{budget.travel}}", "ledger_mismatch:travel"]`.
- `framework=fw-gone` returns 404.

Behaviour switches:
- `authorize("pkg-pending")` makes it `approved`.
- `authorize("pkg-stale")` returns 409 `stale_artifact`.
- `authorize` without MFA returns 403 `step_up_required`.
- `markSubmitted("pkg-approved", "GRANT1")` makes it `submitted`.
- `markSubmitted("pkg-submitted", "OTHER")` returns 409 `already_submitted`.
- `markSubmitted(..., "bad number!")` returns 422 `invalid_confirmation_number`.
- `rebuild("pkg-approved")` returns 200 (identical).

The fixture's file URLs point at `public/fixtures/sample.pdf`, a 1-page PDF, so the
preview works with no backend.

## 12. Analytics and success measures

Events:
- `package_viewed {package_id, authorization_status, status}`
- `package_built {framework_id, new: bool, file_count}`
- `package_build_failed {errors[]}`
- `package_file_previewed {name}`
- `package_authorized {package_id, seconds_since_request}`
- `package_downloaded {package_id}`
- `package_marked_submitted {package_id, channel, minutes_since_download}`

Success:
- 100% of submitted packages have an approval for their exact hash (by construction)
- the median time from HITL-5 request to authorization is under 24 h
- 0 build failures in the demo rehearsal

## 13. Acceptance criteria

- [ ] AC1 The header, stepper, next-step card, file list (title, name, pages, size), amounts and technical details render from `PackageView`.
- [ ] AC2 The next-step card shows the exact copy and the single right action for each authorization state (`not_requested`, `pending` approver and non-approver, `stale`, `held`, `approved`) and for submitted and superseded.
- [ ] AC3 Authorize opens the step-up dialog and sends `X-Hope-MFA: true` with `manifest_hash = content_hash`. On 202 the card moves to approved. 409 `stale_artifact`, 409 `authorization_not_requested` and 403 `step_up_required` show their copy.
- [ ] AC4 Download is a link to `/v1/packages/{id}/download` that appears only when `can.download` is true.
- [ ] AC5 Mark submitted validates the inputs (required, pattern, no future time, soft "GRANT" hint), sends the documented body, and handles 200, 409 `already_submitted` and 422 field errors.
- [ ] AC6 Preview opens the drawer with the file iframe and syncs `?file=`. Esc closes it and returns focus.
- [ ] AC7 `/packages/new?framework=` builds and redirects, and shows each 422 error with its copy and fix link.
- [ ] AC8 Rebuild confirms, then handles 200 (identical) and 201 (navigate to the new package).
- [ ] AC9 Actions are hidden according to `can.*`. A superseded package disables everything and links to the current package.
- [ ] AC10 Polling refetches every 15 s while authorization is pending and stops once it's approved.
- [ ] AC11 Every state in section 7 renders with the exact copy.
- [ ] AC12 The mobile layout (<= 640 px) shows the vertical stepper and the sticky action bar.
- [ ] AC13 axe finds no violations in the pending, approved, submitted and dialog-open states.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `features/packages/PackageScreen.test.tsx::renders package summary and files` |
| AC2 | `PackageScreen.test.tsx::next step per state` (one case per fixture package) |
| AC3 | `features/packages/AuthorizePanel.test.tsx::step up then authorize and error codes` |
| AC4 | `PackageScreen.test.tsx::download only when allowed` |
| AC5 | `features/packages/MarkSubmittedDialog.test.tsx::validation hint and submit outcomes` |
| AC6 | `PackageScreen.test.tsx::preview drawer syncs url and focus` |
| AC7 | `features/packages/BuildPackage.test.tsx::builds redirects and shows errors` |
| AC8 | `PackageScreen.test.tsx::rebuild identical and new` |
| AC9 | `PackageScreen.test.tsx::actions follow can flags and superseded` |
| AC10 | `PackageScreen.test.tsx::polls while pending` (fake timers) |
| AC11 | `PackageScreen.test.tsx::state copy` |
| AC12 | `PackageScreen.test.tsx::mobile layout` (matchMedia mock) |
| AC13 | `features/packages/Package.a11y.test.tsx` (vitest-axe) |
| contract | `apps/web/src/api/packages/http.test.ts::matches openapi snapshot` |

## 15. Open questions

- **Should Mark submitted require the AOR too?** Recommended default: no. `aor` or
  `development_director` may record it, because the HITL-5 authorization is the control.
- **Should there be one combined "Download and mark submitted" step?** Recommended default:
  no. Keep them separate, because submission happens outside Hope and the confirmation
  number only exists afterwards.
- **Should people be able to undo a "Mark submitted" typo?** Recommended default: not in the
  MVP. A wrong number is fixed by an admin in the database. Note it in the demo script.
- **Should the funder portal link be configurable per opportunity?** Recommended default:
  use Grants.gov for Grants.gov sources, otherwise show the text only.
