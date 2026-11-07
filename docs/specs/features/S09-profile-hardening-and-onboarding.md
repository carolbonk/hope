# S09: Profile hardening and onboarding via HITL-0

> **Out of scope for the hackathon. Don't build this.** This spec belongs to the earlier design (the Phase 1 pipeline and the M0-M7 / S-spec roadmap). Hackathon agents build only H0-H5 (see [`README.md`](../README.md)). Keep this file for after the hackathon.

| | |
|---|---|
| Wave | 1 |
| Depends on | S00 |
| Screens | SC09, SC10, SC11 |
| Migrations | `db/migrations/0310_profile_onboarding.sql` |
| Blueprint | 2.2 A3, 3, 4.4 (HITL-0), 5.1, 6.1 (SAM.gov), 7.4, 8.3 |
| Status | Draft |

## Goal

The agency's profile becomes trustworthy enough to drive eligibility, budgets and compliance.
The one agency is created through a HITL-0 approval, not committed directly. Uploaded 990s,
audits and NICRA letters turn into reviewable change proposals. SAM.gov registration is checked
live. Expiring fields raise alerts. The web app gets the profile editor, the HITL-0 review
screen and the onboarding wizard (SC09, SC10, SC11).

## Current state

On `main` after S00:

- `services/profile/src/hope_profile/repository.py`, `ProfileRepository`:
  - Reads: `create_agency`, `current`, `as_of`, `get_version`, `history`, `diff`, `completeness`, `proposals`.
  - Writes: `propose`, `decide`, `scan_stale`.
  - Free function `proposal_hash`.
  - Errors: `ProfileNotFoundError`, `VersionConflictError`, `ProfileValidationError`,
    `ProposalStateError`, `SeparationOfDutiesError`, `ApproverRoleError`.
  - S00 switched it to `hope_core.outbox.write_event` and `hope_core.auth.get_principal`, and
    moved `FieldChange`, `ProfileUpdated`, `ProfileChangeProposal`, `StaleFieldAlert`,
    `NarrativeHit` and `CompletenessReport` into `hope_core.schemas.profile_events`.
- `create_agency` **commits version 1 directly**, so the protected `legal`, `financials` and
  `approval_hierarchy` sections skip HITL-0. That is the main gap this spec closes.
- `hope_profile.api.router` (mounted under `/v1` by `services/pillar/src/hope_pillar/api/agencies.py`):
  - `POST /agencies`
  - `GET /agencies/{id}/profile[?as_of=]`, which sets `ETag: "<version>"`
  - `GET .../history`, `GET .../diff?from_version=&to_version=`, `GET .../completeness`
  - `PATCH .../profile` (optional `If-Match`; 200 committed, 202 pending)
  - `GET .../proposals?status=`
  - `POST .../proposals/{pid}/approve|reject` with body `{artifact_hash, comment}`
- `hope_profile.extraction.ProfileExtractor.propose_from_document` exists, but nothing calls it.
  Its response model `ProfileExtraction` covers legal, mission and fiscal-year fields only.
  It extracts no audit or NICRA data.
- `scan_stale` exists, but nothing schedules it. `hope_profile.validators.uei_errors` checks
  the format only.
- `hope_ingestion.connectors.sam_gov.SamGovClient.check_entity(uei)` returns
  `EntityRegistrationCheck` (from `hope_ingestion.contracts`), but the profile never calls it.
- `hope_ingestion.parsing.text.extract_text(data, media_type, artifact_id) -> DocumentText`
  extracts PDF, DOCX and HTML text.
- `POST /v1/ingest/artifacts` (pillar) returns a pre-signed upload URL and inserts an
  `artifacts` row.
- Migration `0300_profile.sql` has `CHECK (decided_by IS NULL OR decided_by <> proposed_by)`
  (constraint name `profile_change_proposals_check`).
- Web:
  - `apps/web/src/features/profile/ProfileEditor.tsx`, `SectionShell.tsx` and `sections.tsx`
    edit five sections.
  - `api/profile/http.ts` (split out by S00) still sends the old pillar body `{changes}` and
    expects `{status: "accepted" | "pending_approval", proposal_id}`. That shape no longer
    exists once S00 removes the pillar's duplicate routes.
  - There is no proposals screen and no onboarding screen.
- `hitl.requested` events from the profile service are projected into `pillar_gate_requests`
  (`hope_pillar.projector`) with `workflow_id = "profile-proposal:{proposal_id}"`, so they
  appear in the S02 approval inbox.

## Behaviour

### A. Onboarding through HITL-0 (single agency)

1. `POST /v1/agencies` (roles `org_admin`) takes an `AgencyDraft`: an `AgencyProfile`
   without `agency_id`, `tenant_id`, `version` or `valid_from`. The server sets
   `tenant_id = HOPE_TENANT_ID`.
2. The server checks what already exists for the tenant:
   - **No `agencies` row:** insert one (`legal_name` from the draft), then insert a proposal
     with `kind = 'onboarding'`, `base_version = 0`, `patch` = the full draft, and `changes` =
     `diff({}, normalized_draft)`.
   - **A committed version exists:** `409 agency_exists`.
   - **An onboarding proposal is still pending:** `409 onboarding_pending` with `proposal_id`.
   - **The agency exists but its only onboarding proposals were rejected:** reuse the
     `agency_id` and create a new onboarding proposal (re-submission).
3. The draft is normalized and validated exactly like a commit:
   - `AgencyProfile.model_validate` and `validators.profile_errors`;
   - `budget_band` is derived by code;
   - errors return `422 validation_failed` with `errors[]`.
4. The response is `202` with a `ChangeResult` (`status: "pending_approval"`, `version: 0`).
   Through the outbox, the service writes `profile.change_proposed` and `hitl.requested`. The
   `hitl.requested` has `gate: HITL-0`, roles `DEFAULT_HITL0_ROLES` (the draft's own hierarchy
   is not trusted yet), and `due_at` = 3 business days after the proposal.
5. Approving an onboarding proposal commits **version 1** with `recorded_by` = the approver
   and writes `approvals` and `audit_log` (`profile.created`). Through the outbox it writes
   `profile.updated` (with `previous_version: null`) and `hitl.decided`. Rejecting it leaves
   the agency without a profile.
6. Until version 1 exists, `GET /v1/agencies/{id}/profile` returns `404 onboarding_pending`
   with `proposal_id`, and `PATCH` returns `409 onboarding_pending`.
7. `ProfileRepository.create_agency` is removed. Tests and fixtures use the new
   `ProfileRepository.start_onboarding(draft, proposed_by) -> ChangeResult`, plus a test
   helper `hope_profile.testing.onboarded_agency(repo, profile)` that proposes and approves.

### B. Separation of duties and the small-organization mode

8. By default, the proposer can never decide their own proposal: `403 separation_of_duties`.
9. `ProfileSettings.allow_self_approval` (`HOPE_PROFILE_ALLOW_SELF_APPROVAL`, default
   `false`) exists for one-person organizations.
   - When it is `true`, the proposer may approve their own proposal only if the request body
     has `"acknowledge_self_approval": true`. Otherwise the response is
     `403 self_approval_needs_acknowledgement`.
   - A self-approval sets `profile_change_proposals.self_approved = true` and the audit
     detail `{"self_approved": true}`.
   - Migration 0310 replaces the DB check with
     `CHECK (decided_by IS NULL OR decided_by <> proposed_by OR self_approved)`.
10. The approver must hold a role from `validators.hitl0_roles(current_profile)` (or
    `DEFAULT_HITL0_ROLES` for onboarding). Otherwise: `403 approver_role_required`.

### C. Hardened change API

11. `PATCH /v1/agencies/{id}/profile` requires `If-Match`:
    - missing: `428 precondition_required`;
    - malformed: `400 bad_if_match`;
    - stale: `409 version_conflict`, with `current_version` in the problem body.
12. Only `PROFILE_EDITOR_ROLES = ("org_admin", "development_director", "finance_director", "program_lead")`
    may `PATCH`. Others get `403 forbidden`. Any signed-in user may `GET`.
13. Every error uses `hope_core.errors.Problem` (`application/problem+json`). Codes:

    | Code | Status |
    |---|---|
    | `not_found` | 404 |
    | `onboarding_pending` | 404 / 409 |
    | `agency_exists` | 409 |
    | `version_conflict` | 409 |
    | `stale_artifact` (with `current_hash`) | 409 |
    | `proposal_not_pending` | 409 |
    | `proposal_conflict` (with `paths[]`) | 409 |
    | `proposal_integrity` | 409 |
    | `separation_of_duties` | 403 |
    | `self_approval_needs_acknowledgement` | 403 |
    | `approver_role_required` (with `roles[]`) | 403 |
    | `forbidden` | 403 |
    | `validation_failed` (with `errors[]`) | 422 |
    | `precondition_required` | 428 |
    | `bad_if_match` | 400 |
    | `unsupported_media_type` | 415 |
    | `source_too_large` | 413 |
    | `artifact_not_found` | 404 |
    | `uei_missing` | 409 |
    | `sam_not_configured` | 503 |
    | `sam_unavailable` | 502 |

    `proposal_integrity` means the stored hash does not match the recomputed hash. It also
    writes the audit action `profile.proposal_integrity_failed`.
14. Proposal responses use the router-local `ProposalView`, which wraps
    `ProfileChangeProposal` with:
    - `kind` (`change` | `onboarding`);
    - `due_at`;
    - `current_version`;
    - `rebase_needed`: `base_version < current_version`;
    - `source`: a `ProfileSourceView` when `provenance.source_ref` starts with `profile-source:`;
    - `viewer`: `{can_decide: bool, blocked_reason: "own_proposal" | "missing_role" | "not_pending" | null}`.

    `GET .../proposals` returns `{"items": [ProposalView]}`, ordered by `proposed_at` (oldest
    first). Add `GET .../proposals/{proposal_id}`, which returns one `ProposalView`.
15. `POST .../proposals/{pid}/approve|reject` returns a `ChangeResult`. Reject needs a
    `comment` of at least 1 character after trimming, or `422 validation_failed`.
16. The generic `POST /v1/workflows/{workflow_id}/signals/HITL-0` must not decide profile
    proposals: see Catalog changes (owned by S04). SC06 links HITL-0 requests to SC10.

### D. Source documents (990, audit, NICRA, annual report, strategic plan)

17. The client uploads in two steps:
    1. `POST /v1/ingest/artifacts` (existing) with `{filename, media_type, sha256, size_bytes}`,
       then `PUT` the bytes to the `upload_url`;
    2. `POST /v1/agencies/{id}/sources` with `{artifact_id, kind}`.

    Allowed `kind` values: `form_990`, `audit`, `nicra`, `annual_report`, `strategic_plan`, `other`.
18. The server checks the request:
    - the `artifacts` row must exist for the tenant (`404 artifact_not_found`);
    - `media_type` must be one of `application/pdf`,
      `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `text/html`,
      `application/xml`, `text/xml` (`415 unsupported_media_type`);
    - the size must be at most `ProfileSettings.max_source_bytes` = 25 MiB (`413 source_too_large`).

    The same `(agency_id, artifact_id)` twice returns the existing row with `200`;
    otherwise the response is `202`.
19. In the same transaction as the insert, the server writes `profile.source_uploaded`
    (payload `ProfileSourceUploaded`, see Contracts) to the outbox. The source starts as
    `status = 'queued'`.
20. The worker `hope-profile-worker` (`hope_profile.worker:main`) consumes
    `profile.source_uploaded` with group `profile.sources`, using
    `KafkaPostgresPillar.consume`, the same way `hope_pillar.workers.projector` does. It
    dispatches to `hope_profile.sources.handler_for(kind, media_type)`.
    - `hope_profile/sources/__init__.py` discovers handler modules with `pkgutil.iter_modules`.
      Each module exposes `HANDLER: SourceHandler`, so later specs (S15 `irs.py`) add files
      without editing this one.
    - S09 ships `sources/documents.py`, which handles `*` kinds for PDF, DOCX and HTML.
    - `SourceHandler` is a Protocol: `kinds: frozenset[str]`,
      `media_types: frozenset[str]`, and
      `handle(ctx: SourceContext, source: ProfileSourceView, data: bytes) -> SourceOutcome`.
21. `documents.py` does the following:
    1. Status becomes `processing`. It reads the bytes from S3 (`hope_ingestion.artifacts.S3BlobStore`)
       and checks `hope_ingestion.artifacts.active_content_reason`. Any reason gives
       `failed`, `error_code = "active_content"`.
    2. It extracts text with `extract_text`. If `text_quality_ok` is false, the result is
       `failed`, `error_code = "needs_ocr"`, until S11's OCR entry point exists.
    3. It calls `ProfileExtractor.propose_from_document`, with the response model chosen by `kind`:
       - `audit` uses `AuditExtraction` (`audit_type`, `fiscal_year`, `findings`) and maps to
         `financials.last_audit`, with `artifact_id` set to the source's `artifact_id`.
       - `nicra` uses `NicraExtraction` (`rate_bps`, `base`, `agreement_expires_on`) and maps
         to `financials.indirect_rate`, with `type = "negotiated_nicra"`.
       - All other kinds use today's `ProfileExtraction`.
       - No response model contains a money field.
       - Text is wrapped with `untrusted()`. Values below `MIN_CONFIDENCE` or failing a
         validator are dropped and recorded in `dropped`.
       - `Provenance.source_ref = "profile-source:{source_id}"`.
    4. `annual_report`, `strategic_plan` and `other` text is also indexed with
       `NarrativeMemory.index_asset(kind="mission", approved_for_reuse=False)`.
    5. The final status is:
       - `proposed`, with `proposal_id`, `accepted[]` and `dropped{}`;
       - `nothing_found`, when no field survives;
       - `failed`, with `error_code` set to `extraction_failed`, `needs_ocr` or `active_content`.
22. Extraction always files a proposal (`require_review=True`) and never commits.
23. The handler is idempotent: an already processed `source_id` (status not in `queued`,
    `processing`) is skipped. A `processing` row older than 15 minutes is retried. Failures
    after 3 attempts go to the DLQ through `run_with_retry`.
24. `GET /v1/agencies/{id}/sources` (Catalog change) lists `ProfileSourceView` rows, newest
    first, with `?status=` and `?kind=` filters.

### E. Live SAM.gov registration

25. `GET /v1/agencies/{id}/registration[?refresh=true]`:
    1. reads `legal.uei` from the current profile; without one it returns `409 uei_missing`;
    2. returns the latest `profile_registration_checks` row when it is younger than
       `registration_cache_hours` (24) and `refresh` is not set;
    3. otherwise calls `SamGovClient.check_entity(uei)` and stores the result.

    Without `HOPE_SAM_API_KEY` it returns `503 sam_not_configured`. On an HTTP error or
    timeout it returns the cached row with `stale: true` if there is one, else `502 sam_unavailable`.
26. The response is `RegistrationView`: `EntityRegistrationCheck` fields plus `stale`,
    `profile_matches` and `mismatches[]`. `profile_matches` compares SAM's status, expiry and
    exclusion flag with `legal.sam_registration`. Each mismatch is
    `{path, profile, sam}` (for example `legal.sam_registration.expires_on`).
27. `POST /v1/agencies/{id}/registration/sync` (Catalog change, roles `PROFILE_EDITOR_ROLES`)
    proposes `legal.sam_registration` from the latest check, using
    `Provenance(source="sam_gov", source_ref="sam:{uei}:{checked_at}", confidence=1.0)` and
    `require_review=True`. It returns `202` with a `ChangeResult`, or `200` with `no_change`.

    Status mapping:

    | SAM data | `status` |
    |---|---|
    | `registration_status == "Active"` and `days_until_expiry >= 0` | `active` |
    | `found` and expired, or status "Inactive" / "Expired" | `expired` |
    | `found == false` | `none` |
    | anything else | `pending` |

    `exclusions_flag = exclusion_flagged`.
28. A legal-name mismatch between SAM and `legal.legal_name` is reported in `mismatches` but
    never auto-proposed.

### F. Alerts and the daily scan

29. `GET /v1/agencies/{id}/profile/alerts` (Catalog change) returns
    `{"alerts": [StaleFieldAlert], "as_of": date}`. The server computes it live with
    `validators.stale_fields(current_profile, today)`. Nothing is emitted.
30. `hope-profile-daily` (`hope_profile.worker:daily`) runs once a day at 06:00 in
    `HOPE_TZ` (default `America/New_York`), from the deployment scheduler (S28). It does two
    things:
    1. refreshes the registration check if SAM is configured and the cache is older than 24 h;
    2. runs `scan_stale` (one `profile.stale_field` per field, threshold and date, as today).

### G. Workflow revalidation

31. Every `profile.updated` with `protected_changed: true` already carries the changed
    paths. The workflow (S07) consumes it; S09 only guarantees the event is written through
    the outbox in the commit transaction.

### H. Web (SC09, SC10, SC11)

32. `apps/web/src/api/profile/` implements the new shapes:
    - `getProfile`, `patchProfile(patch, etag)` (RFC 7396 merge patch body), `getCompleteness`,
      `getAlerts`, `getHistory`, `getDiff`;
    - `listProposals`, `getProposal`, `approveProposal`, `rejectProposal`;
    - `listSources`, `createSource`, `uploadArtifact` (wraps `POST /v1/ingest/artifacts` plus
      the `PUT`);
    - `getRegistration`, `syncRegistration`, `startOnboarding`.

    Each has `http.ts` and `fixture.ts` implementations. The screens are specified in
    `screens/SC09`, `SC10` and `SC11`.

### What the LLM may and may not do

LLMs only fill `ProfileExtraction`, `AuditExtraction` and `NicraExtraction`. They never
produce money, never commit, and never choose roles or approvers. Every model call goes
through `ModelGateway.structured(ModelTier.MID, …)`, with `MockProvider` in tests.

## Contracts

- **Shared models used:**
  - `hope_core.schemas`: `AgencyProfile` and its sections, `PROTECTED_PROFILE_PATHS`,
    `Provenance`, `HitlRequest`, `HitlDecision` (with `role` from S00), `Gate.PROFILE_COMMIT`;
  - `hope_core.schemas.profile_events`: `FieldChange`, `ProfileUpdated`,
    `ProfileChangeProposal`, `StaleFieldAlert`, `CompletenessReport`, `NarrativeHit`;
  - `hope_core.auth`: `Principal`, `require_roles`;
  - `hope_core.outbox.write_event`;
  - `hope_core.errors.Problem`.
- **Shared contract additions** (needed by wave 1, so they go into S00):
  - `ProfileSourceUploaded` in `hope_core.schemas.profile_events`, the payload of
    `profile.source_uploaded` (S00 adds the event type and a payload). It must have exactly
    these fields: `source_id: UUID`,
    `agency_id: UUID`, `artifact_id: UUID`, `sha256: str`, `kind: Literal["form_990", "audit",
    "nicra", "annual_report", "strategic_plan", "other"]`, `media_type: str`,
    `filename: str`, `uploaded_by: str`.
  - `kind` and `due_at` stay in the router-local `ProposalView`, not in the shared
    `ProfileChangeProposal`, so `proposal_hash` and the event payload are unchanged.
  - `apps/web/src/nav.ts`: set `ready: true` for `/profile/proposals` and `/onboarding`.
    `/onboarding` is `hidden: true`, so it is not shown in the nav.
  - `apps/web/src/components/ui`: a `Stepper` primitive (SC11) and a `FileDrop` primitive
    (SC09, SC11). Until they exist, the screens build local fallbacks in their feature folder.
- **Events** (all written through `write_event` inside the transaction):

  | Event type | Topic | Payload | Producer | Consumers |
  |---|---|---|---|---|
  | `profile.change_proposed` | `gop.profile.events` | `ProfileChangeProposal` | profile | SC10 (via API), S12 |
  | `hitl.requested` (gate HITL-0) | `gop.hitl.events` | `HitlRequest` (`workflow_id = "profile-proposal:{id}"`, `due_at`) | profile | pillar projector, S02, S12 |
  | `hitl.decided` | `gop.hitl.events` | `HitlDecision` | profile | pillar projector, S13 |
  | `profile.updated` | `gop.profile.events` | `ProfileUpdated` | profile | workflow (S07), matching |
  | `profile.source_uploaded` | `gop.profile.events` | `ProfileSourceUploaded` | profile API | `hope-profile-worker` |
  | `profile.stale_field` | `gop.profile.events` | `StaleFieldAlert` | `hope-profile-daily` | S12 |

- **Endpoints.** All are under `/v1` and owned by `hope_profile.api.router`. Dev callers
  identify themselves with `X-Hope-User`, `X-Hope-Roles` and `X-Hope-MFA`; there is no
  tenant header.

  `POST /agencies`, roles `org_admin`. Request:

  ```json
  {
    "legal": {"legal_name": "Riverbend Community Health Alliance", "ein": "84-3917265",
              "uei": "R7KX4M2N9P1Q", "tax_status": "501c3_public_charity", "state_of_incorporation": "WA"},
    "mission": {"mission_statement": "Preventive care, dental services and mental health support for rural families."},
    "financials": {"fiscal_year_end": "06-30", "annual_operating_budget": {"amount_minor": 185000000, "currency": "USD"}},
    "approval_hierarchy": [{"gate": "HITL-1", "approver_roles": ["development_director"]}]
  }
  ```

  Response `202` (a `ChangeResult`; `ChangeResult.proposal` is the shared `ProfileChangeProposal`):

  ```json
  {
    "status": "pending_approval", "version": 0,
    "changes": [{"path": "legal.ein", "old": null, "new": "84-3917265", "protected": true}],
    "proposal": {
      "proposal_id": "5d0c9f0e-2a51-4c8e-9a51-1f4c6b7e2d10", "tenant_id": "…", "agency_id": "b2e7d4c1-8a5f-4b3e-9d2c-7f6a1e0c5b38",
      "base_version": 0, "patch": {"legal": {"…": "…"}},
      "changes": ["…"], "provenance": null, "content_hash": "sha256:3f9a…", "status": "pending",
      "proposed_by": "u-dana", "proposed_at": "2026-11-07T15:00:00Z"
    }
  }
  ```

  Errors: `403 forbidden`, `409 agency_exists`, `409 onboarding_pending`,
  `422 validation_failed`, for example:

  ```json
  {"type": "about:blank", "title": "Validation failed", "status": 422, "code": "validation_failed",
   "errors": ["legal.ein prefix 07 is not an IRS-assigned prefix"]}
  ```

  `GET /agencies/{agency_id}/profile[?as_of=ISO-8601]` (any role): `200 ProfileVersion`
  with an `ETag` header.

  ```json
  {"version": 14, "valid_from": "2026-09-30T14:00:00Z", "valid_to": null,
   "recorded_at": "2026-09-30T14:00:01Z", "recorded_by": "u-marcus", "profile": {"…": "AgencyProfile"}}
  ```

  Errors: `404 not_found`, `404 onboarding_pending` (with `proposal_id`).

  `PATCH /agencies/{agency_id}/profile`, roles `PROFILE_EDITOR_ROLES`.
  - Headers: `If-Match: "14"` (required) and `Content-Type: application/merge-patch+json`
    (`application/json` is also accepted).
  - Body: an RFC 7396 merge patch, for example `{"mission": {"ntee_codes": ["E32", "F30"]}}`.
  - `200 ChangeResult` (`committed`, `no_change`) or `202 ChangeResult` (`pending_approval`).
    The response carries a new `ETag` when the change committed.
  - Errors: `400 bad_if_match`, `403 forbidden`, `409 version_conflict`,
    `409 onboarding_pending`, `422 validation_failed`, `428 precondition_required`.

  `GET /agencies/{agency_id}/profile/history` returns `[ProfileVersion]`, oldest first.

  `GET /agencies/{agency_id}/profile/diff?from_version=&to_version=` returns `[FieldChange]`.
  Use `from_version=0` for onboarding, which diffs against `{}`.

  `GET /agencies/{agency_id}/profile/completeness` returns
  `{"score": 63, "missing": ["legal.uei", "programs.outcomes"]}`.

  `GET /agencies/{agency_id}/profile/alerts` (new) returns:

  ```json
  {"as_of": "2026-11-07", "alerts": [{"agency_id": "…", "field": "legal.sam_registration.expires_on",
   "reason": "sam_expiring", "threshold": "30d", "ref_date": "2026-12-01", "days_remaining": 24}]}
  ```

  `GET /agencies/{agency_id}/profile/proposals?status=pending|approved|rejected|all`
  (default `pending`) returns `{"items": [ProposalView]}`.

  `GET /agencies/{agency_id}/profile/proposals/{proposal_id}` (new) returns one `ProposalView`:

  ```json
  {
    "proposal": {"proposal_id": "…", "base_version": 12, "status": "pending",
                 "changes": [{"path": "financials.indirect_rate.rate_bps", "old": 1500, "new": 2650, "protected": true}],
                 "provenance": {"source": "document_extraction", "source_ref": "profile-source:9a1e…",
                                "captured_at": "2026-11-06T18:20:00Z", "confidence": 0.86},
                 "content_hash": "sha256:7c21…", "proposed_by": "agent:A3", "proposed_at": "2026-11-06T18:20:04Z"},
    "kind": "change", "due_at": "2026-11-11T18:20:04Z", "current_version": 14, "rebase_needed": true,
    "source": {"source_id": "9a1e…", "kind": "nicra", "filename": "NICRA-2026.pdf", "sha256": "e3b0…", "status": "proposed"},
    "viewer": {"can_decide": true, "blocked_reason": null}
  }
  ```

  `POST /agencies/{agency_id}/profile/proposals/{proposal_id}/approve`, roles from
  `hitl0_roles`. Body:
  `{"artifact_hash": "sha256:7c21…", "comment": null, "acknowledge_self_approval": false}`.
  - `200 ChangeResult` (`committed`).
  - Errors: `403 separation_of_duties`, `403 self_approval_needs_acknowledgement`,
    `403 approver_role_required`, `404 not_found`, `409 stale_artifact`,
    `409 proposal_not_pending`, `409 proposal_conflict`, `409 proposal_integrity`.

  `POST .../reject`: the same body, but `comment` is required. Returns `200 ChangeResult`
  (`rejected`).

  `POST /agencies/{agency_id}/sources` (new), roles `PROFILE_EDITOR_ROLES`. Body:
  `{"artifact_id": "…", "kind": "nicra"}`. `202` returns a `ProfileSourceView`:

  ```json
  {"source_id": "9a1e…", "agency_id": "…", "artifact_id": "…", "kind": "nicra", "filename": "NICRA-2026.pdf",
   "media_type": "application/pdf", "sha256": "e3b0…", "size_bytes": 482113, "status": "queued",
   "proposal_id": null, "accepted": [], "dropped": {}, "error_code": null,
   "uploaded_by": "u-dana", "uploaded_at": "2026-11-07T15:02:00Z", "processed_at": null}
  ```

  `GET /agencies/{agency_id}/sources?status=&kind=` (new) returns `{"items": [ProfileSourceView]}`.

  `GET /agencies/{agency_id}/registration[?refresh=true]` (new) returns `RegistrationView`:

  ```json
  {"uei": "R7KX4M2N9P1Q", "found": true, "active": true, "blocks_federal": false,
   "legal_business_name": "RIVERBEND COMMUNITY HEALTH ALLIANCE", "registration_status": "Active",
   "registration_expiration_date": "2027-05-18", "days_until_expiry": 192, "expiry_warning_days": null,
   "exclusion_flagged": false, "checked_at": "2026-11-07T11:00:02Z", "stale": false,
   "profile_matches": true, "mismatches": []}
  ```

  Errors: `409 uei_missing`, `502 sam_unavailable`, `503 sam_not_configured`.

  `POST /agencies/{agency_id}/registration/sync` (new) returns `202 ChangeResult` or `200` with `no_change`.

- **Database** (`0310_profile_onboarding.sql`):

  ```sql
  ALTER TABLE profile_change_proposals
    ADD COLUMN kind text NOT NULL DEFAULT 'change' CHECK (kind IN ('change','onboarding')),
    ADD COLUMN due_at timestamptz,
    ADD COLUMN self_approved boolean NOT NULL DEFAULT false,
    DROP CONSTRAINT profile_change_proposals_check,
    ADD CONSTRAINT profile_change_proposals_sod
      CHECK (decided_by IS NULL OR decided_by <> proposed_by OR self_approved);
  CREATE UNIQUE INDEX profile_one_pending_onboarding ON profile_change_proposals (agency_id)
    WHERE kind = 'onboarding' AND status = 'pending';

  CREATE TABLE profile_sources (
    source_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL REFERENCES tenants,
    agency_id    uuid NOT NULL REFERENCES agencies,
    artifact_id  uuid NOT NULL REFERENCES artifacts,
    kind         text NOT NULL CHECK (kind IN ('form_990','audit','nicra','annual_report','strategic_plan','other')),
    filename     text NOT NULL,
    media_type   text NOT NULL,
    sha256       text NOT NULL,
    size_bytes   bigint NOT NULL,
    status       text NOT NULL DEFAULT 'queued'
                 CHECK (status IN ('queued','processing','proposed','nothing_found','failed')),
    attempts     int NOT NULL DEFAULT 0,
    proposal_id  uuid REFERENCES profile_change_proposals,
    accepted     jsonb NOT NULL DEFAULT '[]',
    dropped      jsonb NOT NULL DEFAULT '{}',
    error_code   text,
    uploaded_by  text NOT NULL,
    uploaded_at  timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    UNIQUE (agency_id, artifact_id)
  );

  CREATE TABLE profile_registration_checks (
    check_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL REFERENCES tenants,
    agency_id    uuid NOT NULL REFERENCES agencies,
    uei          text NOT NULL,
    result       jsonb NOT NULL,          -- EntityRegistrationCheck
    checked_at   timestamptz NOT NULL DEFAULT now()
  );
  CREATE INDEX profile_registration_latest ON profile_registration_checks (agency_id, checked_at DESC);
  ```

  RLS: `ENABLE` + `FORCE` + policy `tenant_isolation` on both new tables, the same loop as
  `0300_profile.sql`, and `GRANT SELECT, INSERT, UPDATE, DELETE … TO hope_app, hope_system`.

- **Settings** (`hope_profile/settings.py`, `ProfileSettings(BaseSettings)`, prefix `HOPE_PROFILE_`):

  | Setting | Default |
  |---|---|
  | `allow_self_approval` | `false` |
  | `max_source_bytes` | `26214400` |
  | `registration_cache_hours` | `24` |
  | `hitl0_sla_business_days` | `3` |
  | `daily_run_hour` | `6` |

  `HOPE_TZ` and `HOPE_SAM_API_KEY` are read from the existing settings classes.

## Owns

```text
services/profile/src/hope_profile/api.py
services/profile/src/hope_profile/repository.py
services/profile/src/hope_profile/extraction.py
services/profile/src/hope_profile/validators.py
services/profile/src/hope_profile/settings.py
services/profile/src/hope_profile/onboarding.py
services/profile/src/hope_profile/registration.py
services/profile/src/hope_profile/worker.py
services/profile/src/hope_profile/testing.py
services/profile/src/hope_profile/sources/__init__.py
services/profile/src/hope_profile/sources/base.py
services/profile/src/hope_profile/sources/documents.py
services/profile/pyproject.toml
services/profile/tests/**
services/pillar/tests/snapshots/openapi/agencies.json
db/migrations/0310_profile_onboarding.sql
apps/web/src/features/profile/**
apps/web/src/features/onboarding/**
apps/web/src/api/profile/**
apps/web/src/app/profile/page.tsx
apps/web/src/app/profile/proposals/page.tsx
apps/web/src/app/onboarding/page.tsx
docs/specs/README.md (S09 status row only)
```

`uv.lock` changes only through `uv lock` after adding `hope-ingestion` and `hope-pillar` to
`services/profile/pyproject.toml` (README rule 6).

## Acceptance criteria

- [ ] AC1 `POST /v1/agencies` creates the agency and a pending onboarding proposal (`version: 0`); no profile version exists until a second user with a HITL-0 role approves it, and then version 1 is committed with `recorded_by` = the approver.
- [ ] AC2 A second `POST /v1/agencies` returns `409 agency_exists` after onboarding, and `409 onboarding_pending` (with `proposal_id`) while a proposal is pending; after a rejection a new onboarding proposal for the same `agency_id` is accepted.
- [ ] AC3 `GET .../profile` returns `404 onboarding_pending` with `proposal_id` before approval.
- [ ] AC4 Self-approval returns `403 separation_of_duties` by default. With `HOPE_PROFILE_ALLOW_SELF_APPROVAL=true` it needs `acknowledge_self_approval: true` (else `403 self_approval_needs_acknowledgement`), sets `self_approved`, and is audited.
- [ ] AC5 The approver needs a role from `hitl0_roles` (`DEFAULT_HITL0_ROLES` for onboarding); otherwise `403 approver_role_required` with `roles`.
- [ ] AC6 `PATCH` without `If-Match` returns 428, a stale one returns `409 version_conflict` with `current_version`, and a non-editor role returns 403.
- [ ] AC7 Every error response is `application/problem+json` with the `code` listed in Behaviour 13.
- [ ] AC8 `GET .../proposals` and `GET .../proposals/{id}` return `ProposalView` with a correct `kind`, `due_at` (3 business days, skipping Saturday and Sunday), `rebase_needed`, `source` and `viewer.blocked_reason`.
- [ ] AC9 Reject without a comment returns 422; with a comment it returns `rejected` and writes `approvals` + `hitl.decided`.
- [ ] AC10 `POST .../sources` validates the artifact, media type and size; it is idempotent per artifact; and it writes `profile.source_uploaded` to the outbox in the same transaction (a rollback leaves neither).
- [ ] AC11 The worker turns a NICRA PDF into a pending proposal for `financials.indirect_rate` (`negotiated_nicra`, `rate_bps`, `base`, `agreement_expires_on`), and an audit PDF into one for `financials.last_audit`, with `Provenance(source="document_extraction", source_ref="profile-source:{id}")`; nothing is committed.
- [ ] AC12 The worker sets `nothing_found`, `failed`/`needs_ocr` (a scanned PDF fixture) and `failed`/`active_content` correctly, skips already-processed sources, and retries a stuck `processing` row.
- [ ] AC13 No extraction response model has a field of type `Money` or a name ending in `_minor` (schema scan).
- [ ] AC14 Handler discovery loads every module in `hope_profile.sources` that exports `HANDLER`, without editing `__init__.py`.
- [ ] AC15 `GET .../registration` uses the 24 h cache, `?refresh=true` bypasses it, it returns `503 sam_not_configured` without a key, falls back to the cached row with `stale: true` on a SAM error, returns `409 uei_missing`, and reports `mismatches`.
- [ ] AC16 `POST .../registration/sync` files a `sam_gov`-provenance proposal using the status mapping in Behaviour 27, or returns `no_change`.
- [ ] AC17 `GET .../profile/alerts` returns the live `stale_fields` output; `hope-profile-daily` refreshes the registration check and emits each stale alert once.
- [ ] AC18 Every state change and its event commit in one transaction (outbox), for proposal, decision, onboarding and source creation.
- [ ] AC19 The OpenAPI snapshot `agencies.json` matches the routes and models above.
- [ ] AC20 SC09, SC10 and SC11 meet their own acceptance criteria.
- [ ] AC21 All CI commands in `AGENTS.md` pass; the existing profile tests are updated from `create_agency` to `onboarded_agency`.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/profile/tests/test_onboarding.py::test_onboarding_needs_hitl0` | db |
| AC2 | `test_onboarding.py::test_single_agency_rules` | db |
| AC3 | `test_api.py::test_profile_pending_onboarding_404` | api |
| AC4 | `test_repository.py::test_self_approval_modes` | db |
| AC5 | `test_repository.py::test_onboarding_uses_default_roles` | db |
| AC6 | `test_api.py::test_patch_preconditions_and_roles` | api |
| AC7 | `test_api.py::test_problem_codes` (parametrized over every code) | api |
| AC8 | `test_api.py::test_proposal_view`, `test_onboarding.py::test_business_day_due_at` | api / unit |
| AC9 | `test_api.py::test_reject_requires_comment` | api |
| AC10 | `test_sources.py::test_create_source_validation_and_idempotency`, `test_sources.py::test_source_event_atomic` | db |
| AC11 | `test_sources.py::test_nicra_and_audit_extraction_propose` (MockProvider) | db |
| AC12 | `test_sources.py::test_worker_failure_states_and_idempotency` | db |
| AC13 | `test_extraction.py::test_no_money_in_extraction_models` | unit |
| AC14 | `test_sources.py::test_handler_discovery` (temp module on `sys.path`) | unit |
| AC15 | `test_registration.py::test_cache_refresh_errors_and_mismatch` (`httpx.MockTransport` + `services/ingestion/tests/fixtures/sam_gov/*.json`) | db |
| AC16 | `test_registration.py::test_sync_status_mapping` | db |
| AC17 | `test_api.py::test_alerts_live`, `test_worker.py::test_daily_runs_once` | db |
| AC18 | `test_outbox_atomicity.py::test_every_write_path_is_atomic` | db |
| AC19 | `services/pillar/tests/test_openapi.py::test_router_snapshots[agencies]` | api |
| AC20 | see SC09, SC10, SC11 test plans | unit |
| AC21 | CI | ci |

Commands: the CI commands in `AGENTS.md`, plus `pnpm --filter @hope/web test` and
`pnpm --filter @hope/web build`.

## Out of scope

- OCR for scanned uploads (S11). Until then the worker returns `needs_ocr`.
- IRS lookups and 990 XML import (S15).
- CRM sync (S24).
- Notifications and escalations for HITL-0 SLAs (S12, S02). This spec sets `due_at` only.
- E-signature. Editing a proposal in place (reject and resubmit instead).
- Multi-agency tenants.

## Decisions needed

- **Self-approval for one-person organizations.** Recommended default: off. It can be
  enabled with `HOPE_PROFILE_ALLOW_SELF_APPROVAL=true` plus an explicit acknowledgement per
  approval, and every use is audited.
- **Profile depends on `hope-ingestion` (SAM client, text extraction, S3 store) and
  `hope-pillar` (`KafkaPostgresPillar.consume`).** Recommended default: accept these library
  dependencies for the MVP. The alternative is to promote `SamGovClient`, `extract_text` and
  the blob store into `hope_core` in C2.
- **SAM.gov key limits.** A personal key without a role allows about 10 requests a day.
  Recommended default: the 24 h cache plus one daily refresh, and `?refresh=true` limited to
  `org_admin`.
- **Who may `PATCH`.** Recommended default: `org_admin`, `development_director`,
  `finance_director` and `program_lead`. There is no `grant_writer` role in code yet (S01
  decides the role list).
- **HITL-0 SLA business days.** Recommended default: Monday to Friday, with no holiday
  calendar in the MVP.
- **`If-Match` mismatch status.** Recommended default: `409 version_conflict` (consistent
  with S00) instead of 412.

## References

- `services/profile/src/hope_profile/{repository,api,extraction,validators,memory}.py`
- `db/migrations/0300_profile.sql`
- `services/ingestion/src/hope_ingestion/connectors/sam_gov.py`, `hope_ingestion/contracts.py::EntityRegistrationCheck`
- `services/ingestion/src/hope_ingestion/parsing/text.py`, `hope_ingestion/artifacts.py`
- `services/pillar/src/hope_pillar/projector.py` (HITL projection), `api/routes.py::ingest_artifact`
- Blueprint 2.2 A3, 4.4, 7.4.
- SAM.gov Entity Management API v3: https://open.gsa.gov/api/entity-api/
- RFC 7396 JSON Merge Patch.
