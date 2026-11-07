# M7: Application package and home dashboard (hackathon)

> **Out of scope for the hackathon. Don't build this.** This spec belongs to the earlier design (the Phase 1 pipeline and the M0-M7 / S-spec roadmap). Hackathon agents build only H0-H5 (see [`README.md`](../README.md)). Keep this file for after the hackathon.

| | |
|---|---|
| Wave | MVP (runs in parallel with M1-M6 after M0) |
| Depends on | M0 |
| Screens | SC22 (package), SC02 (dashboard) |
| Migrations | `db/migrations/1100_packages.sql` (range 1100-1109) |
| Blueprint | 2.2 A10 (manual-kit path only), 4.3 (`Packaging -> AwaitingSubmissionAuth -> Submitted`), 4.4 HITL-5, 5.4 |
| Replaces for the MVP | S21 (package assembly) and S31 (dashboard). Real S2S submission (S22) is out of scope |
| Status | Draft |

## Goal

This spec delivers the last step of the demo and its first screen:
- **Package.** Hope turns an approved framework into a downloadable application package: an
  SF-424-style summary PDF, an SF-424A budget PDF, one PDF per narrative section, a
  `manifest.json` with SHA-256 hashes and a README, all in one zip. The authorized
  representative approves HITL-5 for the package's exact hash. Hope never submits
  anything itself. Approval unlocks the zip and a "Mark submitted" button, where the user
  types the confirmation number from Grants.gov or the funder portal.
- **Dashboard.** The home page (`/`) shows in one glance:
  - how many opportunities are at each stage
  - the top 5 recommendations
  - the approvals waiting for me
  - the next deadlines

## Current state

On `main` today, assuming M0 is merged:

- **Package port.** `hope_packaging.ports.build_package(framework_id: UUID) -> PackageManifest`
  raises `NotImplementedError` (M0 step 6). `PackageManifest` is in `hope_core.schemas` and
  has `package_id`, `framework_id`, `files: [{name, sha256, bytes}]` and `content_hash`.
  M4 calls this port from the workflow's `Packaging` step.
- **Workflow.** `OpportunityLifecycleWorkflow._assemble_package` (`services/workflow/.../workflow.py`)
  calls `AgentActivities.package` and gets back a `SubmissionPackage {manifest_hash, channel,
  payload_ref, valid, errors}`. `_authorize_and_submit` then opens HITL-5 with
  `artifact_hash = manifest_hash`. The stub (`stubs.py::StubAgents.package`) hashes the
  framework and draft hashes and makes up the payload ref
  `s3://hope-artifacts/packages/<hash>.zip`.
- **Authorize endpoint.** `POST /v1/packages/{package_id}/authorize` exists. M0 moves it from
  `routes.py` into `api/packages.py`. Today its `package_id` is the HITL-5 **gate request
  id**. It locks the gate (`_lock_gate`: approver role and step-up MFA, because HITL-5 is in
  `STEP_UP_MFA_GATES`), records the decision (`_decide`: `approvals` row plus
  `hitl.decided`), then calls `route_outbound`. That call checks the `approvals` row and
  writes `submission.authorized` to the outbox. Response:
  `{request_id, event_id, decision, tracking_id}`.
- **Data the package needs:**
  - `frameworks` (`framework jsonb` = `ProposalFramework`, including `budget: BudgetLedger`
    and `scope.project_title`)
  - `budget_ledgers`
  - the current agency profile version (`legal.legal_name`, `ein`, `uei`, `sam_registration`)
  - `opportunity_versions.normalized` (`GrantOpportunity`)
- **Narratives.** M6 writes the narrative sections (`NarrativeSection {section_id, title,
  body_md, placeholders, evidence_ids, content_hash}`). Where they're stored is up to M6
  (migrations 0800-0809).
- **Dashboard.** `apps/web/src/app/page.tsx` just redirects to `/matrix`. `dashboard.py` is
  an empty router mounted by M0. There's no PDF writer in the lockfile (only the readers
  `pdfplumber` and `pypdfium2`).

## Behaviour

### A. Building a package

1. **`build_package(framework_id)`** in `hope_packaging.builder` is re-exported by
   `hope_packaging.ports`. It runs in `tenant_tx(conn, HOPE_TENANT_ID)` as `hope_app`:
   1. Load the framework row.
      - Missing: raise `PackageError("not_found")`.
      - `status = 'superseded'`: raise `PackageError("framework_superseded")`.
   2. Load these inputs:
      - the profile, the latest version for `framework.agency_id`
      - the opportunity, from `opportunity_versions` at `opportunities.current_version`
      - the ledger, `framework.budget`
      - the sections, from `SectionSource.current_sections(framework_id)`. The default is
        `hope_drafting.ports.current_sections` (see Requests to M0). Tests inject a fake.
   3. Validate the inputs. Collect every failure (don't stop at the first) and raise
      `PackageError("package_invalid", errors=[...])` if there are any:

      | Error code | When |
      |---|---|
      | `missing_ein` | `profile.legal.ein` is empty |
      | `missing_sections` | there are no sections |
      | `unfilled_placeholder:{section_id}:{token}` | a `{{...}}` token is still in a section after filling |
      | `ledger_mismatch:{category}` | the SF-424A category sums ≠ `ledger.totals` (step 5) |
      | `missing_title` | `scope.project_title` is empty |
   4. Fill the placeholders in each `body_md` with `hope_core.narrative.fill_placeholders(body_md, ledger)`
      (Requests to M0). This is the only place money gets into the narrative, and it comes
      from deterministic code, never from the LLM.
   5. Render the files with **reportlab** (`invariant=1`, so the same input gives the same bytes):
      - **`01-summary-sf424.pdf`**, one page. Its header line reads "Summary in SF-424
        layout, prepared by Hope. This is not the official form. Enter these values in the
        official SF-424 in Grants.gov Workspace or the funder's portal." Rows:

        | Row | Source |
        |---|---|
        | Applicant legal name | `legal.legal_name` |
        | EIN | `legal.ein` |
        | UEI | `legal.uei`, or "Not on file" |
        | SAM registration | `sam_registration.status` + `expires_on` |
        | Funding opportunity number | `source.source_id` |
        | Opportunity title | `opportunity.title` |
        | Funding agency | `funder.name` |
        | Assistance listing (ALN) | `funder.aln` joined |
        | Project title | `scope.project_title` |
        | Project period | `deadlines.project_period_months`, or "Not stated" |
        | Federal funds requested | `totals.request_minor` |
        | Applicant / non-federal share | `totals.cost_share_minor` |
        | Total project cost | `totals.project_total_minor` |
        | Application due | `deadlines.application_due`, in its own timezone |
        | Prepared on | `build date` = the framework's `created_at`, not the wall clock, to keep it deterministic |
        | Authorized representative | "Signed electronically through HITL-5 approval on {date}", or "Pending HITL-5" |

        The last row is the only value that differs between a package before and after
        approval. It is **not** part of `content_hash`: it's printed only in the zip's
        README, and the PDF always says "See README".
      - **`02-budget-sf424a.pdf`**: Section B in SF-424A layout. Rows a-k are Personnel,
        Fringe Benefits, Travel, Equipment, Supplies, Contractual, Construction, Other,
        Total Direct Charges, Indirect Charges and Totals. The columns are "Federal
        (request)", "Non-federal (cost share)" and "Total".
        - Each category's Federal value is the sum of `line_items.amount_minor` where
          `funding_source == "request"`. Its Non-federal value is the sum where
          `funding_source` is `cost_share_cash` or `cost_share_in_kind`.
        - The `indirect` category goes in row j.
        - The cross-check must hold or the build stops with `ledger_mismatch`:
          i (federal) = `totals.direct_minor`, j = `totals.indirect_minor`,
          k (federal) = `totals.request_minor`, k (non-federal) = `totals.cost_share_minor`.
        - Under the table the PDF lists every `cap_check` with `status` and
          `adjustment_note`, plus one line per period when `ledger.periods > 1`.
      - **`03-narrative-{nn}-{slug}.pdf`**: one PDF per section, in the order the sections
        come from `current_sections`. `nn` is 01, 02, and so on, and `slug` is the
        `section_id` in kebab case. The title goes in the heading.
        - `body_md` is rendered with a small converter that handles `#`/`##`/`###`
          headings, paragraphs, `-` and `1.` lists, `**bold**` and `*italic*`. Any other
          markup is printed as text. The converter escapes all reportlab mini-HTML.
        - The footer reads "{project title} · {section title} · page n of m".
   6. Build the manifest:
      - `files` holds the three file kinds above, sorted by name, each with `sha256` (hex)
        and `bytes`.
      - `content_hash = hope_core.hashing.content_hash({"framework_id": str, "framework_hash": framework.content_hash, "files": files})`.
        `package_id` is left out, so a rebuild with identical inputs gives the identical hash.
   7. Build the zip. The entries are the files plus:
      - `manifest.json` (the manifest and `generated_by: "hope-packaging/0.1.0"`)
      - `README.txt`, which explains how to submit manually, the HITL-5 status, and the
        reminder "Hope does not submit applications; you do"

      Zip settings: entries in sorted order, `ZipInfo.date_time = (1980, 1, 1, 0, 0, 0)`,
      `ZIP_DEFLATED`.
   8. Store the result:
      - **Same `framework_id` and `content_hash` as an existing package that isn't
        superseded:** return that package. This is idempotent: no new row, and the original
        `built_at` is kept.
      - **Otherwise:**
        - Insert a `packages` row (`status = 'built'`) and a `package_blobs` row (the zip
          bytes). The zip may be at most `HOPE_PACKAGE_MAX_BYTES`, default 20 MB, or the
          build raises `package_too_large`.
        - Mark every other non-superseded package of this framework `superseded`.
        - Publish nothing. M4's workflow opens HITL-5 from the returned manifest.
   9. Return the `PackageManifest`.
2. **The workflow path (M4).** The `Packaging` step calls `build_package` and maps the result
   to `SubmissionPackage`:
   - `manifest_hash = content_hash`
   - `payload_ref = "hope-package:{package_id}"`
   - `channel = opportunity.requirements.submission_channel`, or `"grants_gov"` for Grants.gov sources and `"other"` for the rest
   - `valid = True`; on a `PackageError`, `valid = False` with `errors = e.errors`

   The workflow then opens HITL-5 with `artifact_hash = content_hash` and
   `HitlRequest.package_id = package_id` (Requests to M4).
3. **Manual build** (`POST /v1/frameworks/{framework_id}/package`) calls the same function.
   SC19's "Build package" button and SC22's "Rebuild" use it.

### B. HITL-5 status of a package (derived, never stored)

4. `authorization` is computed on every read, from `pillar_gate_requests` (`gate = 'HITL-5'`,
   `subject_id = opportunity_id`) and from `approvals`. Rules in order, first match wins:

   | `status` | Rule |
   |---|---|
   | `approved` | an `approvals` row exists with `gate = 'HITL-5'`, `decision = 'approve'`, `artifact_hash = package.content_hash` |
   | `pending` | an open HITL-5 gate request exists with `artifact_hash = content_hash` |
   | `stale` | an open HITL-5 gate request exists with a **different** `artifact_hash` (the package changed after the request was opened) |
   | `held` | the latest decided HITL-5 request for this hash has `decision` of `reject` or `defer` |
   | `not_requested` | anything else |

### C. Authorize, download, mark submitted

5. **Authorize** (`POST /v1/packages/{package_id}/authorize`). This is M7's version of the
   built route.
   1. Find the package by `package_id`. If there's no package with that id, use the
      **legacy** behaviour: treat the id as a HITL-5 gate request id, exactly as today. This
      keeps the existing `test_api.py` test and M3's current client working.
   2. For a real package:
      - Superseded package: 409 `stale_artifact` with the current package's `content_hash`
        as `current_hash`.
      - `body.manifest_hash ≠ content_hash`: 409 `stale_artifact`.
   3. Lock the open HITL-5 gate where `subject_id = opportunity_id` and
      `artifact_hash = content_hash`, using the shared `lock_gate` helper (Requests to M0).
      That helper keeps the 403 `forbidden` for a missing `aor` role and the 403
      `step_up_required` without `X-Hope-MFA: true`.
      - No such gate: 409 `authorization_not_requested`.
      - Only a gate with a different hash: 409 `stale_artifact`.
   4. Call `decide(..., "approve", content_hash, comment)`.
   5. Call `route_outbound(OutboundPackage(channel=body.channel, manifest_hash=content_hash,
      payload_ref="hope-package:{package_id}", authorized_by=user_id))`. This records
      `submission.authorized` in the outbox and nothing consumes it in the MVP.
   6. Set `packages.status = 'authorized'`.
   7. Return 202 with the same body as today:
      `{request_id, event_id, decision: "approve", tracking_id}`.
6. **Download** (`GET /v1/packages/{package_id}/download`).
   - Allowed only when `authorization.status == "approved"` and the package isn't superseded.
   - The response streams `package_blobs.zip` as `application/zip` with
     `Content-Disposition: attachment; filename="{opportunity number}-{yyyy-mm-dd}-hope-package.zip"`,
     `ETag: "{content_hash}"` and `X-Hope-Package-Sha256: {zip sha256}`.
   - Errors: 409 `authorization_required`, 409 `stale_artifact`.
7. **Preview a file** (`GET /v1/packages/{package_id}/files/{name}`, new; see Catalog changes).
   This lets the AOR read every file *before* authorizing. It streams one file from the
   stored zip with `Content-Disposition: inline` and is allowed for any signed-in user.
   - `name` must be one of the manifest's `files[].name`, or the response is 404 `not_found`.
   - Every page of a preview PDF carries the overlay text "PREVIEW · not authorized". The
     overlay is stamped on the fly, so the stored bytes and hashes don't change.
8. **Mark submitted** (`POST /v1/packages/{package_id}/mark-submitted`). Roles: `aor`,
   `development_director`.
   1. The package must have `authorization.status == "approved"` for its current
      `content_hash`. Otherwise:
      - 409 `authorization_required`
      - 409 `stale_artifact` (superseded)
   2. Check for an earlier submission:
      - Already `submitted` with the same `confirmation_number`: 200 with the existing
        record (idempotent).
      - Already `submitted` with a different number: 409 `already_submitted` with
        `confirmation_number`.
   3. Validate the body:
      - `confirmation_number` is required: 3-64 characters matching `^[A-Za-z0-9._-]+$`,
        otherwise 422 `invalid_confirmation_number`.
      - `submitted_at` is optional, defaults to now, and may not be in the future (60 s of
        clock skew is allowed), otherwise 422 `invalid_submitted_at`.
      - `channel` is one of `grants_gov`, `funder_portal`, `email`, `mail`, `other`.
   4. Update the package: `status = 'submitted'`, `submitted_at`, `submitted_by`,
      `confirmation_number`, `channel`, `note`.
   5. In the same transaction, publish `application.submitted`
      (`EventType.APPLICATION_SUBMITTED`, topic `gop.outbound.packages`) with an
      `ApplicationSubmitted` payload (Requests to M0). `trace.correlation_id` is the workflow
      id, from `tenant_opportunity.workflow_id`.
   6. M4's workflow moves to `Submitted` when it sees this event (Requests to M4).
   7. Return 200.

   For Grants.gov a hint (not a check) is shown when the number doesn't look like `GRANT`
   followed by digits. See Decisions.

### D. Dashboard

9. **`GET /v1/dashboard`** is open to any signed-in user. It reads as `hope_app` in one
   `tenant_tx`, for `agency_id = HOPE_AGENCY_ID`, and runs 4 queries:
   - **`pipeline`.** Counts of `tenant_opportunity` by `state`, grouped into stages:

     | Stage | States |
     |---|---|
     | `discover` | `Normalized`, `NeedsEligibilityReview`, `Screened`, `Recommended` |
     | `decide` | `AwaitingGoNoGo` |
     | `plan` | `Planning`, `AwaitingBudgetSignoff` |
     | `write` | `Drafting`, `InReview`, `AwaitingCompliance`, `AwaitingExecApproval` |
     | `submit` | `Packaging`, `AwaitingSubmissionAuth`, `SubmissionError` |
     | `submitted` | `Submitted` |
     | `outcome` | `Awarded`, `PostAward`, `NotAwarded` |
     | `closed` | `Declined`, `Expired`, `Ineligible`, `Archived`, `Discarded` |

     Every stage is always present (0 if empty), in this order. Each stage includes its
     per-state counts.
   - **`top_recommendations`.** At most 5 rows where:
     - `workflow_id IS NULL`
     - `state IN ('Screened','Recommended')`
     - `recommendation IN ('pursue','consider')`
     - `coalesce(internal_deadline, application_due) > now()`

     They're ordered by `composite_score DESC NULLS LAST`, then `opportunity_id`. Each row
     joins the current `opportunity_versions.normalized` for `funder.name`,
     `funding.award_ceiling` and `deadlines.application_due`. `top_recommendations_total` is
     the count before the limit.
   - **`my_approvals`.** At most 5 open `pillar_gate_requests` whose `approver_roles`
     overlap the principal's roles (an empty list counts as anyone). They're ordered by
     `due_at NULLS LAST`, then `requested_at`.
     - Each row has the opportunity title. For HITL-5 it also has the `package_id` of the
       package whose `content_hash = artifact_hash`, so the link goes to SC22.
     - `my_approvals_total` is the count before the limit.
   - **`upcoming_deadlines`.** At most 5 rows where:
     - `workflow_id IS NOT NULL`
     - `state` is not terminal and not `Submitted`, `Awarded`, `PostAward` or `NotAwarded`
     - `coalesce(internal_deadline, application_due)` falls within the next 30 days

     They're ordered by that date ascending, with `days_left` computed from the internal
     deadline. Rows already past are included with `days_left < 0` (overdue), at the top.
   - **`generated_at`** is `now()`.

## Contracts

- **Shared models used:**
  - `hope_core.schemas`: `PackageManifest` (M0), `NarrativeSection` (M0), `ProposalFramework`,
    `BudgetLedger`, `LineItem`, `Totals`, `AgencyProfile`, `GrantOpportunity`, `HitlRequest`,
    `HitlDecision`, `Gate`
  - `hope_core.hashing.content_hash`
  - `hope_core.money.Money`
  - `hope_core.auth`: `Role`, `require_roles`, `Principal`
  - `hope_core.errors`: `Problem`, `StaleArtifactError`
  - `hope_core.pillar.OutboundPackage`
- **Models local to this spec** (in `hope_pillar/api/packages.py` and `dashboard.py`):
  `PackageView`, `AuthorizationView`, `MarkSubmittedBody`, `SubmissionView`, `DashboardView`
  and its row models. The web clients mirror them in `api/packages/types.ts` and
  `api/dashboard/types.ts`, checked against the OpenAPI snapshots.
- **Events:**

  | Event type | Topic | Payload | Producer | Consumers |
  |---|---|---|---|---|
  | `hitl.decided` (existing) | `gop.hitl.events` | `HitlDecision` | `packages.py` authorize | workflow (M4) |
  | `submission.authorized` (existing) | `gop.hitl.events` | `OutboundPackage` | `route_outbound` | none in the MVP |
  | `application.submitted` (existing type) | `gop.outbound.packages` | `ApplicationSubmitted` (Requests to M0) | `packages.py` mark-submitted | workflow (M4) moves to `Submitted` |

- **Endpoints.** All are under `/v1` and served by the pillar app. Errors are
  `application/problem+json` with `code`. Roles are values of the M0 `Role` enum.

  **`POST /v1/frameworks/{framework_id}/package`**. Builds the package or returns the
  current one. Roles: `development_director`, `program_director`, `executive_director`, `aor`.
  The body is empty. It returns 201 when a new package was built, or 200 when an identical
  one already exists, with a `PackageView` either way:
  ```json
  {
    "package_id": "6a0c9a52-4f3e-4b7a-9d55-1d2c3b4a5e6f",
    "framework_id": "2f9e7b10-3c4d-4e5f-8a9b-0c1d2e3f4a5b",
    "framework_version": 3,
    "opportunity_id": "3b1f8e0a-6c2d-4f3e-8a9b-0c1d2e3f4a5b",
    "opportunity_title": "Youth Mentoring Expansion",
    "opportunity_number": "O-OJJDP-2026-0042",
    "funder_name": "Office of Juvenile Justice and Delinquency Prevention",
    "application_due": "2026-12-08T23:59:00-05:00",
    "internal_due": "2026-12-05T23:59:00-05:00",
    "workflow_id": "lifecycle-7c1e...",
    "status": "built",
    "content_hash": "sha256:4f1b0c8e...",
    "zip_sha256": "9a7d0c...",
    "zip_bytes": 184233,
    "built_by": "u-dana",
    "built_at": "2026-11-07T15:20:04Z",
    "files": [
      {"name": "01-summary-sf424.pdf", "kind": "summary", "title": "Application summary (SF-424 layout)", "sha256": "1c2d...", "bytes": 21877, "pages": 1},
      {"name": "02-budget-sf424a.pdf", "kind": "budget", "title": "Budget (SF-424A layout)", "sha256": "77ab...", "bytes": 30112, "pages": 2},
      {"name": "03-narrative-01-project-summary.pdf", "kind": "narrative", "title": "Project summary", "sha256": "e0f1...", "bytes": 18003, "pages": 1},
      {"name": "03-narrative-02-need-statement.pdf", "kind": "narrative", "title": "Statement of need", "sha256": "5b6c...", "bytes": 24410, "pages": 3},
      {"name": "manifest.json", "kind": "manifest", "title": "Manifest and hashes", "sha256": "aa01...", "bytes": 1430, "pages": null},
      {"name": "README.txt", "kind": "readme", "title": "How to submit", "sha256": "bb02...", "bytes": 1210, "pages": null}
    ],
    "totals": {"request": {"amount_minor": 25000000, "currency": "USD"},
               "cost_share": {"amount_minor": 5000000, "currency": "USD"},
               "project_total": {"amount_minor": 30000000, "currency": "USD"}},
    "authorization": {"status": "pending", "request_id": "9d1e...", "approver_roles": ["aor"],
                      "requested_at": "2026-11-07T15:21:00Z", "due_at": "2026-12-04T17:00:00Z",
                      "decided_by": null, "decided_at": null, "comment": null, "current_request_hash": "sha256:4f1b0c8e..."},
    "submission": null,
    "superseded_by": null,
    "can": {"authorize": true, "download": false, "mark_submitted": false, "rebuild": true}
  }
  ```
  How some fields are filled:
  - `manifest.json` and `README.txt` show in `files` for the UI, but they are not part of
    `PackageManifest.files` or the content hash.
  - `can` is computed for the calling principal:
    - `authorize`: the principal has a role in the gate's `approver_roles` and the status is `pending`
    - `download`: the status is `approved`
    - `mark_submitted`: the status is `approved`, the package isn't `submitted`, and the
      principal has `aor` or `development_director`
    - `rebuild`: the package isn't submitted and the principal has a build role
  - `submission` is `{confirmation_number, channel, submitted_at, submitted_by, note}` once submitted.
  - `superseded_by` is the newer `package_id` when this package has been superseded.

  Errors:
  - 403 `forbidden`
  - 404 `not_found` (no framework)
  - 409 `framework_superseded`
  - 422 `package_invalid`, for example:
    `{"code": "package_invalid", "errors": ["missing_ein", "unfilled_placeholder:budget-narrative:{{budget.travel}}"]}`
  - 422 `package_too_large`

  **`GET /v1/packages/{package_id}`** returns 200 `PackageView` to any signed-in user.
  Error: 404 `not_found`.

  **`GET /v1/packages/{package_id}/files/{name}`** returns 200 `application/pdf`,
  `application/json` or `text/plain`, inline, with the preview overlay on PDFs. Error: 404
  `not_found`.

  **`GET /v1/packages/{package_id}/download`** returns 200 `application/zip` (headers as in
  Behaviour 6). Errors: 404 `not_found`, 409 `authorization_required`, 409 `stale_artifact`
  (`current_hash`).

  **`POST /v1/packages/{package_id}/authorize`**. The approver comes from the gate's
  `approver_roles` (`aor`), and the request needs the header `X-Hope-MFA: true`. Request:
  `{"manifest_hash": "sha256:4f1b0c8e...", "channel": "grants_gov", "comment": "Reviewed all 4 PDFs"}`.
  Response 202: `{"request_id": "9d1e...", "event_id": "c3b2...", "decision": "approve", "tracking_id": "0f9e..."}`.
  Errors:
  - 403 `forbidden`
  - 403 `step_up_required`
  - 404 `not_found`
  - 409 `stale_artifact` (`current_hash`)
  - 409 `authorization_not_requested`
  - 409 `gate_closed` (the gate was already decided)

  **`POST /v1/packages/{package_id}/mark-submitted`**. Roles: `aor`, `development_director`.
  Request:
  `{"confirmation_number": "GRANT14327793", "channel": "grants_gov", "submitted_at": "2026-11-07T16:02:00-05:00", "note": "Submitted via Workspace by Dana"}`.
  Response 200 is the `PackageView` with `"status": "submitted"` and
  `"submission": {"confirmation_number": "GRANT14327793", "channel": "grants_gov", "submitted_at": "2026-11-07T21:02:00Z", "submitted_by": "u-dana", "note": "Submitted via Workspace by Dana"}`.
  Errors:
  - 403 `forbidden`
  - 404 `not_found`
  - 409 `authorization_required`
  - 409 `stale_artifact`
  - 409 `already_submitted` (`confirmation_number`)
  - 422 `invalid_confirmation_number`
  - 422 `invalid_submitted_at`
  - 422 `validation_error`

  **`GET /v1/dashboard`** returns 200 to any signed-in user:
  ```json
  {
    "agency_id": "5e2c...", "agency_name": "Riverbend Youth Alliance", "generated_at": "2026-11-07T15:30:00Z",
    "pipeline": [
      {"stage": "discover", "label": "Discover", "count": 31, "states": {"Normalized": 4, "NeedsEligibilityReview": 2, "Screened": 16, "Recommended": 9}},
      {"stage": "decide", "label": "Go / no-go", "count": 2, "states": {"AwaitingGoNoGo": 2}},
      {"stage": "plan", "label": "Plan", "count": 1, "states": {"Planning": 0, "AwaitingBudgetSignoff": 1}},
      {"stage": "write", "label": "Write", "count": 2, "states": {"Drafting": 1, "InReview": 0, "AwaitingCompliance": 0, "AwaitingExecApproval": 1}},
      {"stage": "submit", "label": "Submit", "count": 1, "states": {"Packaging": 0, "AwaitingSubmissionAuth": 1, "SubmissionError": 0}},
      {"stage": "submitted", "label": "Submitted", "count": 3, "states": {"Submitted": 3}},
      {"stage": "outcome", "label": "Outcome", "count": 1, "states": {"Awarded": 1, "PostAward": 0, "NotAwarded": 0}},
      {"stage": "closed", "label": "Closed", "count": 7, "states": {"Declined": 2, "Expired": 1, "Ineligible": 4, "Archived": 0, "Discarded": 0}}
    ],
    "top_recommendations": [
      {"opportunity_id": "3b1f...", "title": "Youth Mentoring Expansion", "funder_name": "OJJDP",
       "recommendation": "pursue", "composite_score": 87.0,
       "award_ceiling": {"amount_minor": 25000000, "currency": "USD"},
       "application_due": "2026-12-08T23:59:00-05:00", "internal_deadline": "2026-12-05T23:59:00-05:00", "state": "Recommended"}
    ],
    "top_recommendations_total": 9,
    "my_approvals": [
      {"request_id": "9d1e...", "gate": "HITL-5", "summary": "Authorize submission via grants_gov",
       "workflow_id": "lifecycle-7c1e...", "opportunity_id": "3b1f...", "opportunity_title": "Youth Mentoring Expansion",
       "due_at": "2026-12-04T17:00:00Z", "requested_at": "2026-11-07T15:21:00Z", "package_id": "6a0c..."}
    ],
    "my_approvals_total": 1,
    "upcoming_deadlines": [
      {"workflow_id": "lifecycle-7c1e...", "opportunity_id": "3b1f...", "title": "Youth Mentoring Expansion",
       "state": "AwaitingSubmissionAuth", "internal_deadline": "2026-12-05T23:59:00-05:00",
       "application_due": "2026-12-08T23:59:00-05:00", "days_left": 28}
    ]
  }
  ```
  Errors: none specific (401/403 come from M0's auth).
- **Database** (`db/migrations/1100_packages.sql`):
  ```sql
  CREATE TABLE packages (
    package_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL REFERENCES tenants,
    framework_id        uuid NOT NULL REFERENCES frameworks,
    framework_version   int  NOT NULL,
    framework_hash      text NOT NULL,
    opportunity_id      uuid NOT NULL REFERENCES opportunities,
    agency_id           uuid NOT NULL REFERENCES agencies,
    content_hash        text NOT NULL,
    zip_sha256          text NOT NULL,
    zip_bytes           int  NOT NULL CHECK (zip_bytes > 0),
    manifest            jsonb NOT NULL,          -- PackageManifest + per-file kind/title/pages
    status              text NOT NULL DEFAULT 'built'
                        CHECK (status IN ('built','authorized','submitted','superseded')),
    built_by            text NOT NULL,
    built_at            timestamptz NOT NULL DEFAULT now(),
    superseded_by       uuid REFERENCES packages,
    confirmation_number text,
    channel             text CHECK (channel IN ('grants_gov','funder_portal','email','mail','other')),
    submitted_at        timestamptz,
    submitted_by        text,
    note                text,
    CHECK (status <> 'submitted' OR (confirmation_number IS NOT NULL AND submitted_at IS NOT NULL))
  );
  CREATE UNIQUE INDEX packages_one_current ON packages (framework_id) WHERE status <> 'superseded';
  CREATE INDEX packages_content_hash ON packages (tenant_id, content_hash);

  CREATE TABLE package_blobs (
    package_id  uuid PRIMARY KEY REFERENCES packages ON DELETE CASCADE,
    tenant_id   uuid NOT NULL REFERENCES tenants,
    zip         bytea NOT NULL
  );
  -- The usual tenant_isolation policy (same DO-block pattern as 0001/0100) on both tables.
  ALTER TABLE packages ENABLE ROW LEVEL SECURITY;      ALTER TABLE packages FORCE ROW LEVEL SECURITY;
  ALTER TABLE package_blobs ENABLE ROW LEVEL SECURITY; ALTER TABLE package_blobs FORCE ROW LEVEL SECURITY;
  CREATE POLICY tenant_isolation ON packages      USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
  CREATE POLICY tenant_isolation ON package_blobs USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
  ```
- **Settings** (`hope_packaging/settings.py`, `PackagingSettings`, prefix `HOPE_`):
  `package_max_bytes: int = 20_000_000`, `package_preview_overlay: bool = True`.
- **Dependencies** (in `services/packaging/pyproject.toml`; run `uv lock`): `reportlab>=4.2`,
  `hope-core`, `psycopg`.

## Demo seed

`hope_packaging/demo.py:seed()` must run **after** M5's and M6's seeds (Requests to M0: seed
order). It's idempotent and runs as `hope_app` under `HOPE_TENANT_ID`.

1. For each framework of the demo agency with `status = 'approved_locked'`, a non-empty
   `budget`, at least one section from `current_sections`, and no current package, call
   `build_package`. Errors are logged as a warning and skipped, so the seed never fails
   the demo.
2. If the demo opportunity "Youth Mentoring Expansion" (M1's seed) has a package, write
   nothing more. The live demo then approves HITL-5 and marks it submitted on stage.
3. **Rehearsal flag.** With `HOPE_DEMO_PACKAGE_STATE=submitted`, the seed also records an
   approval and a submission for that package, with confirmation number `GRANT00000001`
   and note "Seeded for rehearsal". This lets SC02 and SC22 be shown in their final state
   without clicking through. The approval row uses `decided_by = "demo-aor"` and the same
   `content_hash`. The default is unset, so the seed doesn't do this.

The dashboard needs no seed of its own. It reads what M1-M6 seed.

## Owns

```text
services/packaging/**                                   (builder.py, render/summary.py, render/budget.py, render/narrative.py,
                                                         render/markdown.py, zipper.py, store.py, settings.py, ports.py, demo.py,
                                                         pyproject.toml, tests/)
services/pillar/src/hope_pillar/api/packages.py
services/pillar/src/hope_pillar/api/dashboard.py
services/pillar/tests/test_packages_api.py
services/pillar/tests/test_dashboard_api.py
services/pillar/tests/snapshots/openapi/packages.json
services/pillar/tests/snapshots/openapi/dashboard.json
apps/web/src/features/packages/**
apps/web/src/features/dashboard/**
apps/web/src/api/packages/**
apps/web/src/api/dashboard/**
apps/web/src/app/packages/**                            ([packageId]/page.tsx, new/page.tsx)
apps/web/src/app/page.tsx
db/migrations/1100_packages.sql
```

## Acceptance criteria

- [ ] AC1 `build_package` on the fixture framework produces exactly the listed files. Each PDF opens with `pdfplumber` and contains its required rows or headings (summary: all 16 row labels; budget: rows a-k with the right sums; narrative: section title and body text).
- [ ] AC2 Building twice with identical inputs gives byte-identical files, the same `content_hash` and the same zip, and the second build returns the existing package (200, no new row).
- [ ] AC3 Changing a narrative section or a ledger line gives a new `content_hash` and supersedes the previous package.
- [ ] AC4 The SF-424A totals equal `ledger.totals`, and cost-share lines appear only in the non-federal column. An inconsistent ledger fails with `ledger_mismatch`.
- [ ] AC5 Placeholders are filled from the ledger. Any token left over fails with `unfilled_placeholder`, and no LLM is called during packaging.
- [ ] AC6 Invalid inputs return 422 `package_invalid` with every error collected (missing EIN, no sections, missing title).
- [ ] AC7 `authorization.status` follows every rule in Behaviour 4 (approved, pending, stale, held, not_requested).
- [ ] AC8 Authorize approves only the gate whose hash equals the package's `content_hash`, requires `aor` and step-up MFA, and records `approvals` + `hitl.decided` + `submission.authorized`. The legacy gate-id path still passes the existing test.
- [ ] AC9 Download returns 409 `authorization_required` before HITL-5 approval, and after approval returns the exact stored zip (sha256 matches `zip_sha256`) with the documented headers.
- [ ] AC10 Previewing a file works before approval and adds the overlay without changing the stored zip.
- [ ] AC11 Mark submitted requires approval for the current hash. It validates the confirmation number and date, is idempotent for the same number, returns 409 `already_submitted` for a different number, and publishes `application.submitted` in the same transaction.
- [ ] AC12 A superseded package returns 409 `stale_artifact` with `current_hash` on authorize, download and mark-submitted.
- [ ] AC13 `GET /v1/dashboard` returns all 8 stages in order with the correct counts, the top 5 by score that aren't pursued yet and have a future deadline, my approvals filtered by my roles (with `package_id` for HITL-5), and deadlines within 30 days, with overdue items first.
- [ ] AC14 Role checks: building, mark-submitted and authorize reject roles outside their lists with 403.
- [ ] AC15 The demo seed builds a package for an approved demo framework, running it twice creates nothing new, and `HOPE_DEMO_PACKAGE_STATE=submitted` produces a submitted package.
- [ ] AC16 The OpenAPI snapshots for `packages` and `dashboard` match. SC22 and SC02 acceptance criteria pass.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/packaging/tests/test_builder.py::test_files_and_contents` | unit |
| AC2 | `test_builder.py::test_deterministic_and_idempotent` | unit + db |
| AC3 | `test_builder.py::test_input_change_supersedes` | db |
| AC4 | `services/packaging/tests/test_budget_pdf.py::test_sf424a_totals_and_cost_share_column`, `::test_ledger_mismatch` | unit |
| AC5 | `services/packaging/tests/test_narrative_pdf.py::test_placeholders_filled`, `::test_unfilled_placeholder_fails`, `::test_no_model_calls` (gateway spy) | unit |
| AC6 | `test_builder.py::test_validation_collects_all_errors` | unit |
| AC7 | `services/pillar/tests/test_packages_api.py::test_authorization_status_rules` (parametrized) | api + db |
| AC8 | `test_packages_api.py::test_authorize_hash_role_mfa`, existing `test_api.py` authorize test | api + db |
| AC9 | `test_packages_api.py::test_download_requires_approval_and_matches_hash` | api + db |
| AC10 | `test_packages_api.py::test_preview_overlay_does_not_change_blob` | api + db |
| AC11 | `test_packages_api.py::test_mark_submitted_rules_and_event` | api + db |
| AC12 | `test_packages_api.py::test_superseded_package_is_stale` | api + db |
| AC13 | `services/pillar/tests/test_dashboard_api.py::test_dashboard_sections` | api + db |
| AC14 | `test_packages_api.py::test_roles` | api |
| AC15 | `services/packaging/tests/test_demo_seed.py::test_seed_idempotent_and_rehearsal_flag` | db |
| AC16 | `services/pillar/tests/test_openapi.py::test_router_snapshots` + SC22 / SC02 test files | api / web |

All tests are offline. There's no LLM in this spec (`MockProvider` isn't even needed), and
sections come from a fake `SectionSource`. Commands: the CI commands in `AGENTS.md`, plus
`UPDATE_SNAPSHOTS=1 uv run pytest services/pillar/tests/test_openapi.py` after a route change.

## Requests to M0 (and to the owners of other specs)

1. **`hope_drafting.ports.current_sections(framework_id: UUID) -> list[NarrativeSection]`**, which
   M6 fills. M7 reads the sections through this port. Until then, M7 injects a
   `SectionSource` in tests and the seed skips frameworks with no sections.
2. **`hope_core.narrative.fill_placeholders(body_md: str, ledger: BudgetLedger) -> str`**, with
   the token grammar shared by M6 (which writes the tokens) and M7 (which fills them).
   Recommended tokens:
   - `{{budget.request_total}}`
   - `{{budget.cost_share_total}}`
   - `{{budget.project_total}}`
   - `{{budget.direct_total}}`
   - `{{budget.indirect_total}}`
   - `{{budget.category.<BudgetCategory>}}`

   Each is rendered as `$250,000` with `Money` formatting.
3. **`ApplicationSubmitted`** payload model in `hope_core.schemas`, registered for
   `EventType.APPLICATION_SUBMITTED`: `package_id: UUID, opportunity_id: UUID,
   workflow_id: str | None, content_hash: str, channel: str, confirmation_number: str,
   submitted_by: str, submitted_at: datetime`.
4. **Shared gate helpers.** `lock_gate(tx, where, *params)` and
   `decide(tx, gate, decision, artifact_hash, comment)` go into a shared module,
   `hope_pillar/api/gates.py`, instead of staying private in `workflows.py`, so that
   `packages.py` can import them. The helper's 403 should carry `code: "step_up_required"`
   when MFA is missing.
5. **Seed order** in `hope-demo-seed`: profile, M1, M2, M4, M5, M6, then M7 last.
6. **`components/ui`**: move the approvals feature's `StepUpDialog` into `components/ui` so SC22
   can reuse it. Until then SC22 has its own small copy in `features/packages`.
7. **M4 (workflow).** In the `Packaging` step:
   - call `hope_packaging.ports.build_package`
   - open HITL-5 with `artifact_hash = manifest.content_hash` and `HitlRequest.package_id`
   - after HITL-5 approval (MVP, no real submit), wait for `application.submitted` and then
     move to `Submitted`, with the confirmation number as the transition note
   - if the package hash changes while HITL-5 is open, re-open HITL-5 with the new hash
8. **M3 (approvals).** For HITL-5 requests, link to `/packages/{package_id}` (SC22) and call
   `POST /v1/packages/{package_id}/authorize` with the real package id.
9. **M6 (SC19).** Add a "Build package" link to `/packages/new?framework={framework_id}`, which
   SC22's route owns.
10. **M4 (SC07).** Accept `/workflows?stage={discover|decide|plan|write|submit|submitted|outcome|closed}`,
    using the stage-to-state map in Behaviour 9. SC02's pipeline tiles link there.
11. **Orchestrator.** `uv.lock` needs a relock for `reportlab` (added in `services/packaging/pyproject.toml`),
    and the M7 status row in `docs/specs/README.md` needs updating. Both are outside M7's Owns list.

## Out of scope

- Real submission (Grants.gov S2S, S22).
- The official SF-424 family of PDF forms. The PDFs here are summaries in the same layout.
- E-signatures, virus scanning, S3 storage (zips live in Postgres for the MVP), compliance
  checks (S19) and verifier findings (S18).
- Dashboard personalisation, charts over time, and win rates.

## Decisions needed

1. **Where zips are stored.** Recommended default: Postgres `bytea`. It's the most reliable for
   a local demo, with no MinIO dependency, and a 20 MB cap. Later this moves to S3 with
   Object Lock.
2. **Can people download before HITL-5?** Recommended default: no, which follows the README
   rule. Single-file previews with a "PREVIEW" overlay let the AOR review the package before
   authorizing.
3. **Grants.gov confirmation number format.** Recommended default: accept any 3-64
   character token and show a soft hint when a Grants.gov number doesn't start with
   "GRANT". Don't block on it, because the format isn't verified here.
4. **Should `ledger.sf424a_mapping` be used?** Recommended default: not for the MVP. Compute
   the categories from `line_items` and cross-check them against `totals`.
5. **Who can mark a package submitted?** Recommended default: `aor` and `development_director`
   (the person who actually clicks Submit in the portal).

## References

- `services/pillar/src/hope_pillar/api/routes.py` (`authorize_package`, `_lock_gate`, `_decide`, `get_matrix`), `pillar.py::route_outbound`
- `services/workflow/src/hope_workflow/workflow.py` (`_assemble_package`, `_authorize_and_submit`), `stubs.py::StubAgents.package`
- `packages/core/src/hope_core/schemas/proposal_framework.py` (`BudgetLedger`, `LineItem`, `Totals`, `CapCheck`)
- `db/migrations/0001_core.sql` (`frameworks`, `budget_ledgers`, `approvals`, `tenant_opportunity`), `0100_pillar.sql` (`pillar_gate_requests`)
- `docs/architecture/blueprint.md` 2.2 A10, 4.3, 4.4, 5.4
- reportlab user guide (`invariant` option): https://docs.reportlab.com/
