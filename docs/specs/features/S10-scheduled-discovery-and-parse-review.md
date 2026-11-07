# S10: Scheduled discovery and parse-review queue

> **Out of scope for the hackathon. Don't build this.** This spec belongs to the earlier design (the Phase 1 pipeline and the M0-M7 / S-spec roadmap). Hackathon agents build only H0-H5 (see [`README.md`](../README.md)). Keep this file for after the hackathon.

| | |
|---|---|
| Wave | 1 |
| Depends on | S00 |
| Screens | SC12 (parse review). SC17 (built by S01) calls this spec's schedule endpoints |
| Migrations | `db/migrations/0210_discovery_and_parse_review.sql` |
| Blueprint | 2.2 A1/A2, 4.3 (`Ingested -> NeedsParseReview -> Normalized / Discarded`), 6.1, 8.5 |
| Status | Draft |

## Goal

Hope finds new grants on its own, without a person running a script. A worker polls each
enabled source (Grants.gov in this spec) on a schedule that an admin can change. Every
opportunity the parser can't finish lands in a parse-review queue. There, a person picks
between conflicting values, fills in a missing deadline, or confirms a flagged document is
safe, and the opportunity then moves on to scoring. Without this spec, any RFP with a
missing deadline or a conflict stays stuck forever.

## Current state

On `main`, after PRs #1-#9 and S00:

- `hope_ingestion.pipeline.IngestionPipeline.run(connector, query, cursor)` runs discovery
  for one `SavedSearch`. Nothing calls it except
  `services/ingestion/scripts/grants_gov_smoke.py` (manual) and the tests. There is no
  scheduler, no worker entrypoint, and no stored schedule.
- `PostgresIngestionStore` (`repository.py`) already has `get_cursor` / `put_cursor` on
  `connector_cursors (source_system, search_key)` (`0200_ingestion.sql`), but nothing
  writes cursors.
- When `apply_policy` returns `blocking`, `IngestionPipeline.ingest` publishes
  `opportunity.parse_incomplete` with `ParseIncomplete {opportunity, version, blocking[],
  questions_to_funder[]}`. S00 moves this model to `hope_core.schemas.ingest`. Nothing
  consumes the event: there is no queue, no API and no way to resolve it.
  `BlockingIssue.reason` is one of `missing | conflict | corrupt | unreadable`. The `field`
  values are:
  - `deadlines.application_due`
  - `funding.award_ceiling` (conflicts only)
  - any conflicting field from `policy.resolve`
  - `source.artifacts`
  - `parse_quality.injection_suspected`
  - `parse_quality.model_budget_exceeded`
- When the OCR stub (`parsing/ocr.py::NoOcr`) is hit, the pipeline adds the warning
  `ocr_fallback_not_implemented:{artifact_id}`.
- `policy.internal_deadline(opp)` subtracts 72 h when `deadline.time_assumed` is in
  `parse_quality.warnings`. S00 adds `Deadlines.internal_due` and
  `ExtractedDeadline.time_assumed`, but `policy.apply_policy` doesn't fill them yet.
- `OpportunityState.NEEDS_PARSE_REVIEW` and `Gate.PARSE_REVIEW = "REVIEW-PARSE"` exist in
  `hope_core`. S00 adds `EventType.PARSE_REVIEW_RESOLVED = "opportunity.parse_review_resolved"`.
- The pillar API (`hope_pillar.api`) has an empty `parse_reviews.py` router (S00).

## Behaviour

### A. Discovery schedules

1. **Schedule rows.** `source_schedules` has one row per `source_system`. The migration
   seeds `grants_gov` with these values (an admin turns it on in SC17):
   - `enabled = false`
   - `interval_minutes = 120` (blueprint 6.1: REST delta every 2 h)
   - `saved_search` set to the `SavedSearch` defaults (statuses `forecasted` and `posted`, `page_size` 25)
   - `max_records = 500`
2. **Tick.** `python -m hope_ingestion.worker` calls `DiscoveryScheduler.tick(now)` every
   `HOPE_DISCOVERY_TICK_SECONDS` (default 30). One tick claims **at most one** due schedule
   with an atomic lease:
   ```sql
   UPDATE source_schedules SET lease_until = now() + make_interval(secs => %(lease)s), lease_owner = %(worker)s
    WHERE source_system = (
      SELECT source_system FROM source_schedules
       WHERE enabled AND next_run_at <= now() AND (lease_until IS NULL OR lease_until < now())
       ORDER BY next_run_at LIMIT 1 FOR UPDATE SKIP LOCKED)
   RETURNING *;
   ```
   The lease defaults to `HOPE_DISCOVERY_LEASE_SECONDS = 3600`. Two workers never run
   the same source at once. A crashed worker's lease expires and another worker picks the
   source up.
3. **Run.** The scheduler does the following:
   1. Insert a `discovery_runs` row with `status = 'running'`.
   2. Build the connector from the `CONNECTORS` registry (`connectors/registry.py`:
      `{"grants_gov": GrantsGovConnector}`).
   3. Load the cursor with `get_cursor(source_system, search_key)`. Here
      `search_key = content_hash(saved_search)`, so editing the search starts a new cursor.
   4. Call `IngestionPipeline.run(connector, saved_search, cursor, on_record=...)`. The new
      `on_record(result, cursor)` callback runs after each record. It saves the cursor
      (`put_cursor`) and adds to the run's counts, so a crash resumes from the last
      finished record.
4. **Outcomes.**
   - **Success:** all records finished.
     - The cursor resets to `Cursor()`. Grants.gov `search2` has no delta token, so each
       run walks the whole search again. Records that haven't changed come back as
       `IngestResult.status == "unchanged"` and emit nothing.
     - The run row gets `status = 'succeeded'`.
     - The schedule gets `last_status = 'succeeded'`, `consecutive_failures = 0`,
       `next_run_at = started_at + interval`, `lease_until = NULL`.
   - **Partial:** a single record raised an error. Typical causes are
     `SourceUnavailableError` on one attachment, or a `RuntimeError("all model providers failed")`.
     - The error is logged with `source_id`, `failed` is incremented, and the run continues.
     - At the end, `status = 'partial'`. The schedule advances as for success.
   - **Failure:** the source itself failed. Either `discover` raised, or `health()` returned
     `ok = false` before the run started.
     - The run row gets `status = 'failed'` and `error` set to the exception class and
       message (max 500 chars, no secrets).
     - `consecutive_failures` increases by one.
     - `next_run_at = now + min(interval * 2^consecutive_failures, 24 h)`.
     - The cursor is **not** reset, so the next run resumes where this one stopped.
   - **Not configured:** `health()` returns `configured = false` (for example SAM.gov with
     no key, later Candid).
     - The run gets `status = 'skipped'` and `error = 'not_configured'`.
     - `next_run_at` advances by the normal interval. It does not back off.
5. **Schedule edits** (`PUT /v1/sources/schedules/{source}`) take effect on the next tick.
   - Enabling a schedule, or shortening its interval, sets
     `next_run_at = least(next_run_at, now())`, so the first run starts within one tick.
   - Disabling a schedule leaves a run that is already going to finish. The lease still
     protects it.
6. **Run now** is out of scope here. A user who wants an immediate run shortens the
   interval. See Decisions needed.

### B. Parse-review queue

7. **Opening a review.** `IngestionPipeline` gets a new optional field
   `reviews: ReviewQueue | None`, which the worker sets to `PostgresReviewQueue`. After
   `repository.save` in `ingest`:
   - **`result.blocking` is not empty:** call
     `reviews.open(opportunity_id, version, content_hash, blocking, questions_to_funder, artifacts, reasons)`.
     - `artifacts` lists every stored artifact as `{artifact_id, sha256, media_type, filename}`.
     - The call first marks any open review for that opportunity `superseded`, then inserts
       a new `open` row. Both happen in one transaction.
   - **`result.blocking` is empty:** call `reviews.close_superseded(opportunity_id)`. Any
     open review becomes `superseded`, because a re-ingest or amendment fixed it.
   - **`IngestResult.status == "unchanged"`:** do nothing.
8. **Review reasons.** `reasons` is a set derived from the blocking issues:
   - `injection` when `field == "parse_quality.injection_suspected"`
   - `budget_exceeded` when `field == "parse_quality.model_budget_exceeded"`
   - otherwise, the issue's own `reason` (`missing | conflict | corrupt | unreadable`)

   `ReviewReason` is a shared literal (see Contracts).
9. **OCR warning.** In `pipeline._store_document`, the stub warning is renamed from
   `ocr_fallback_not_implemented:{id}` to `ocr_unreadable:{id}`. S11's engine returns
   `None` both for no engine and for low confidence, so one name covers both.
10. **Policy fills the new fields.** `policy.apply_policy` sets:
    - `ExtractedDeadline.time_assumed = True` when the time was assumed
    - `Deadlines.internal_due = policy.internal_deadline(opp)`

    The `deadline.time_assumed` warning stays, so existing consumers keep working.

### C. Resolving and discarding (API, then the ingestion consumer)

11. **`POST /v1/parse-reviews/{review_id}/resolve`** runs in the request's `tenant_tx`.
    1. Check roles. The principal needs one of `PARSE_REVIEW_ROLES` (see Endpoints).
       Otherwise return 403 `forbidden`.
    2. Lock the row (`SELECT ... FOR UPDATE`).
       - Missing: 404 `not_found`.
       - Status not `open`: 409 `review_closed`, with the current `status`.
    3. Compare `body.version_hash` with `parse_reviews.content_hash`. If they differ, return
       409 `stale_artifact` with `current_hash`. This happens when a newer version superseded
       the review between page load and submit.
    4. Validate `body.fields` (all errors are 422):
       - Every blocking `field` must have exactly one entry. Missing ones return
         `unresolved_fields` with a `fields` list.
       - Each entry's `field` must be in `RESOLVABLE_FIELDS`, and its `action` must be one
         the field allows. Otherwise return `invalid_value` with `field`.
       - `pick`: `candidate_index` must index into that issue's `candidates`. Otherwise return
         `invalid_candidate`.
       - `enter`: the typed `value` must validate for that field's value model, and
         `evidence` must name an `artifact_id` that belongs to this review with `page >= 1`.
         Otherwise return `invalid_value` with `field` and `detail`.
       - A deadline `timezone` must be a valid IANA zone (`zoneinfo.ZoneInfo`). Otherwise
         return `invalid_value`.
       - `acknowledge` is allowed only for `parse_quality.injection_suspected`,
         `parse_quality.model_budget_exceeded` and `source.artifacts`. If the opportunity
         would still have no `deadlines.application_due` after the resolution, return
         `unresolved_fields` with `["deadlines.application_due"]`. A safe document with no
         deadline is still blocked (8.5).
    5. Update the row: `status = 'resolving'`, `resolved_by = principal.user_id`,
       `resolution = body` (JSON).
    6. Write `opportunity.parse_review_resolved` (payload `ParseReviewResolved`, below) with
       `hope_core.outbox.write_event`, in the same transaction, with
       `tenant_id = HOPE_TENANT_ID` and `data_classification = "internal"`.
    7. Return 202 with the updated review summary.

    The LLM plays no part in a resolution. Every value comes from a person, or from a
    candidate that deterministic code parsed.
12. **`POST /v1/parse-reviews/{review_id}/discard`** runs the same role, lock and
    `review_closed` checks. `version_hash` is required, with the same 409 `stale_artifact`
    rule. It then:
    - sets `status = 'discarded'`, `resolved_by`, `resolved_at = now()` and the discard
      `reason` / `note`
    - writes `opportunity.parse_review_resolved` with `action = "discard"`
    - returns 200

    No new version is written. Discarded opportunities are excluded from
    `opportunity_parse_status` (below), which is what S03 search uses.
13. **Consumer** (`hope_ingestion.review.ParseReviewResolver`) subscribes to
    `opportunity.parse_review_resolved` in group `ingestion-parse-review`, as `hope_system`.
    1. Idempotency: if the review isn't `resolving` (for `resolve`) or is already in the
       target status, acknowledge the event and stop.
    2. Load the version the review points to. If the opportunity's `current_version` has
       moved past it, set the review to `superseded` and stop. The newer version has its own
       review or none.
    3. Apply each `ResolvedField` to a copy of the `GrantOpportunity`:
       - **`pick`.** Re-parse `candidates[i].value` with the same validator that produced it:
         `parse_deadline` for deadlines, `parse_money` for money fields, `parse_indirect`,
         `parse_cost_share`, and the plain string for text fields. Keep the candidate's
         `evidence`. Set `confidence = 1.0` and `extractor = "human:{user_id}"`. If
         re-parsing fails (it shouldn't), set the review `status = 'open'` again with
         `error = 'candidate_unparseable'` and stop.
       - **`enter` deadline.** `DeadlineValue {local: "2027-03-03T17:00", timezone, time_stated}`
         becomes an `ExtractedDeadline` with the value localised to `timezone`. When
         `time_stated = false`:
         - the time is 23:59
         - `time_assumed = true`
         - the `deadline.time_assumed` warning is added

         Evidence is the reviewer's `{artifact_id, page, quote?}`.
       - **`enter` money.** `Money` comes straight from the body: integer `amount_minor`,
         entered by a person and never by an LLM.
       - **`enter` other values.** `IndirectCostPolicy`, `CostShare` and `str` are used
         unchanged. Their evidence goes into `funding.evidence` or the field's `evidence`.
       - **`acknowledge`.**
         - For injection, `parse_quality.injection_suspected` stays `true` (it's a fact
           about the document). The warning `injection_acknowledged:{user_id}` is added.
         - For `source.artifacts` and budget, the warning `{field}_acknowledged:{user_id}`
           is added.
    4. Recompute the derived fields:
       - `missing_critical_fields`, with resolved ones removed
       - `pipeline_path`, with `"human"` appended
       - `deadlines.internal_due = policy.internal_deadline(opp)`

       Validate the result as a `GrantOpportunity`. An exception here sets the review back to
       `open` with `error`.
    5. `repository.save(opp)` writes the next version. `amendment_seq` stays the same,
       because a human fix is not a funder amendment.
    6. Set the review `resolved`, with `resolved_at` and `resolved_version`. Publish
       `opportunity.normalized` with `cause.caused(...)` from the resolved event, so the trace
       carries the reviewer's action. Matching re-scores from that event as it would for any
       normalized opportunity.
    7. Steps 5-6 are not one transaction across the publish. If the publish fails after the
       save, a redelivered event sees status `resolving` and `current_version == resolved_version`,
       re-publishes `normalized` and marks the review `resolved` (`event_id` dedup in the
       outbox makes this safe).
14. **Discard consumer:** no state change beyond what the API wrote. The handler only
    acknowledges the event. A later lifecycle-projection consumer (S04) may move per-tenant
    rows to `Discarded`.

### D. Tenant model

15. Opportunities and reviews are public, cross-tenant rows, so `parse_reviews` has no
    `tenant_id` and no RLS. Ingestion writes it as `hope_system`. The API (`hope_app`) may
    `SELECT` and `UPDATE` only these columns: `status`, `resolution`, `resolved_by`,
    `resolved_at`, `discard_reason`, `discard_note`, `updated_at`. The MVP is single-tenant
    (decision 1 covers multi-tenant later).

## Contracts

- **Shared models used:**
  - `hope_core.schemas.grant_opportunity`: `GrantOpportunity`, `ExtractedDeadline`,
    `Deadlines`, `IndirectCostPolicy`, `CostShare`, `SourceSystem`
  - `hope_core.schemas.common.Evidence`
  - `hope_core.money.Money`
  - `hope_core.schemas.ingest` (S00): `ParseIncomplete`, `BlockingIssue`, `Candidate`
  - `hope_core.envelope.PillarEnvelope`
  - `hope_core.auth`: `Principal`, `require_roles`
  - `hope_core.errors`: `Problem`, `StaleArtifactError`, `NotFound`, `Forbidden`
  - `hope_core.outbox.write_event`
- **Shared contract additions** (for S00 / C2, not this PR). All go in
  `packages/core/src/hope_core/schemas/ingest.py`:
  ```python
  # moved from hope_ingestion.connectors.base, fields unchanged
  class Cursor(Contract): position: int = 0; etag: str | None = None; updated_since: datetime | None = None
  class SavedSearch(Contract): keywords: list[str] = []; aln: list[str] = []; agencies: list[str] = []
      eligibilities: list[str] = []; statuses: list[Literal["forecasted","posted","closed","archived"]] = ["forecasted","posted"]
      page_size: int = Field(25, ge=1, le=1000); max_records: int | None = None

  ReviewReason = Literal["missing", "conflict", "corrupt", "unreadable", "injection", "budget_exceeded"]
  ParseReviewStatus = Literal["open", "resolving", "resolved", "discarded", "superseded"]
  ResolveAction = Literal["pick", "enter", "acknowledge"]

  class DeadlineValue(Contract):
      local: datetime                      # naive wall-clock time in `timezone`
      timezone: str                        # IANA, validated with zoneinfo
      time_stated: bool = True             # False -> 23:59 + time_assumed (8.5)

  class ResolvedField(Contract):
      field: str                           # one of RESOLVABLE_FIELDS
      action: ResolveAction
      candidate_index: int | None = None   # action == "pick"
      deadline: DeadlineValue | None = None
      money: Money | None = None
      indirect_cost_policy: IndirectCostPolicy | None = None
      cost_share: CostShare | None = None
      text: str | None = Field(None, max_length=500)
      evidence: Evidence | None = None     # required for action == "enter"
      # model_validator: exactly the value attribute matching the field's kind is set for "enter"

  RESOLVABLE_FIELDS: dict[str, tuple[Literal["deadline","money","indirect","cost_share","text","ack"], frozenset[ResolveAction]]] = {
      "deadlines.application_due": ("deadline", {"pick", "enter"}),
      "deadlines.loi_due": ("deadline", {"pick", "enter"}),
      "deadlines.questions_due": ("deadline", {"pick", "enter"}),
      "funding.award_ceiling": ("money", {"pick", "enter"}),
      "funding.award_floor": ("money", {"pick", "enter"}),
      "funding.total_program_funding": ("money", {"pick", "enter"}),
      "funding.indirect_cost_policy": ("indirect", {"pick", "enter"}),
      "funding.cost_share": ("cost_share", {"pick", "enter"}),
      "title": ("text", {"pick", "enter"}),
      "funder.name": ("text", {"pick", "enter"}),
      "source.artifacts": ("ack", {"acknowledge"}),
      "parse_quality.injection_suspected": ("ack", {"acknowledge"}),
      "parse_quality.model_budget_exceeded": ("ack", {"acknowledge"}),
  }

  class ParseReviewResolved(Contract):
      """Payload of opportunity.parse_review_resolved (EventType from S00)."""
      review_id: UUID
      opportunity_id: UUID
      version: int
      version_hash: str                    # "sha256:..." of the reviewed version
      action: Literal["resolve", "discard"]
      fields: list[ResolvedField] = []
      comment: str | None = Field(None, max_length=2000)
      discard_reason: Literal["not_an_rfp", "duplicate", "expired", "unreadable", "other"] | None = None
      decided_by: str
      decided_at: datetime
  ```
  The other shared changes:
  - Register `ParseReviewResolved` as the payload schema for
    `EventType.PARSE_REVIEW_RESOLVED` (topic `gop.opportunity.events`).
  - Re-run `hope-export-schemas`.
  - **Not a model, but shared:**
    - `services/ingestion/pyproject.toml` adds `hope-pillar`, because the worker uses
      `KafkaPostgresPillar` as its `PillarPort`. S11 changes the same file, so S00/C2 batches both.
    - `hope_ingestion/parsing/ocr.py` gets `def build_ocr_engine() -> OcrEngine: return NoOcr()`,
      the seam S11 replaces.
    - The pillar app mounts an empty `api/sources.py` router.
    - `apps/web/src/api/client.ts` composes `parseReview` from `api/parse-review`.
- **Events:**

  | Event type | Topic | Payload | Producer | Consumers |
  |---|---|---|---|---|
  | `opportunity.parse_incomplete` (existing) | `gop.opportunity.events` | `ParseIncomplete` | ingestion pipeline | this spec (review row is written in-process, not by consuming the event) |
  | `opportunity.parse_review_resolved` | `gop.opportunity.events` | `ParseReviewResolved` | pillar API `parse_reviews.py` (outbox) | `hope_ingestion.review.ParseReviewResolver` |
  | `opportunity.normalized` (existing) | `gop.opportunity.events` | `GrantOpportunity` | ingestion pipeline, and now `ParseReviewResolver` | matching (`hope_matching.agents`) |

- **Endpoints.** All are under `/v1` in the pillar app, and errors are
  `application/problem+json`. Role constants live in `parse_reviews.py`:
  - `PARSE_REVIEW_ROLES = {"grant_writer", "development_director", "program_director", "executive_director"}`
  - `SOURCE_ADMIN_ROLES = {"admin", "executive_director"}`

  Viewing needs any signed-in principal.

  **`GET /v1/parse-reviews`.** Query parameters:
  - `status` (default `open`; `open | resolving | resolved | discarded | superseded | all`)
  - `reason` (`ReviewReason`, repeatable)
  - `source_system`
  - `q` (title contains, case-insensitive, min 2 chars)
  - `sort` (`due` (default: `application_due` nulls first, then `created_at`) | `newest` | `oldest`)
  - `cursor`
  - `limit` (default 25, max 100)

  Response 200:
  ```json
  {
    "items": [{
      "review_id": "7f6c1d2e-0b7a-4e57-9a51-2d3c4b5a6f70",
      "opportunity_id": "3b1f8e0a-6c2d-4f3e-8a9b-0c1d2e3f4a5b",
      "version": 2,
      "version_hash": "sha256:9c1e...",
      "title": "OJJDP FY 2026 Mentoring for Youth Impacted by Opioids",
      "funder_name": "Office of Juvenile Justice and Delinquency Prevention",
      "source_system": "grants_gov",
      "source_id": "O-OJJDP-2026-172743",
      "source_url": "https://www.grants.gov/search-results-detail/360123",
      "status": "open",
      "reasons": ["conflict"],
      "blocking_fields": ["funding.award_ceiling"],
      "application_due": "2026-12-08T23:59:00-05:00",
      "internal_due": "2026-12-05T23:59:00-05:00",
      "created_at": "2026-11-07T14:02:11Z",
      "updated_at": "2026-11-07T14:02:11Z"
    }],
    "next_cursor": null,
    "total": 1,
    "counts": {"open": 4, "resolving": 0, "resolved": 12, "discarded": 2}
  }
  ```
  `total` counts matches for the current filter. `counts` covers all statuses, ignoring the
  `status` filter, for the screen's tabs. The cursor is opaque base64 of the sort key plus
  `review_id`. Errors: 422 `validation_error` (bad enum or limit).

  **`GET /v1/parse-reviews/{review_id}`.** Response 200 is the summary fields plus:
  ```json
  {
    "review_id": "…", "status": "open", "version": 2, "version_hash": "sha256:9c1e…",
    "opportunity": { "...": "GrantOpportunity of that version (opportunity_versions.normalized)" },
    "blocking": [{
      "field": "funding.award_ceiling", "reason": "conflict",
      "kind": "money", "allowed_actions": ["pick", "enter"],
      "candidates": [
        {"value": "$500,000", "evidence": [{"artifact_id": "a1…", "page": 3, "char_start": 812, "char_end": 840, "quote": "Award Ceiling: $500,000"}]},
        {"value": "$750,000", "evidence": [{"artifact_id": "a1…", "page": 9, "char_start": 120, "char_end": 151, "quote": "awards of up to $750,000 each"}]}
      ]
    }],
    "injection_signals": [],
    "questions_to_funder": ["What indirect cost rate and base are allowed under this opportunity?"],
    "warnings": ["funding.indirect_cost_policy_assumed"],
    "artifacts": [{"artifact_id": "a1…", "sha256": "5d0f…", "media_type": "application/pdf", "filename": "O-OJJDP-2026-172743.pdf", "pages": 24}],
    "resolution": null,
    "resolved_by": null, "resolved_at": null, "resolved_version": null,
    "error": null
  }
  ```
  `kind` and `allowed_actions` come from `RESOLVABLE_FIELDS`, so the UI never hard-codes
  them. `injection_signals` lists the `candidates[].value` strings of the
  `parse_quality.injection_suspected` issue (for example `"pattern:ignore_instructions"`,
  `"hidden_text"`). `pages` is the page count captured at open time. Errors: 404 `not_found`.

  **`POST /v1/parse-reviews/{review_id}/resolve`.** Roles: `PARSE_REVIEW_ROLES`. Request:
  ```json
  {
    "version_hash": "sha256:9c1e…",
    "fields": [
      {"field": "funding.award_ceiling", "action": "pick", "candidate_index": 0},
      {"field": "deadlines.application_due", "action": "enter",
       "deadline": {"local": "2026-12-08T17:00:00", "timezone": "America/New_York", "time_stated": true},
       "evidence": {"artifact_id": "a1…", "page": 1, "quote": "Applications due December 8, 2026 5:00 PM ET"}}
    ],
    "comment": "Ceiling on p.3 is the per-award cap; p.9 is the multi-site cap."
  }
  ```
  Response 202 is the summary, with `"status": "resolving"`. Errors:
  - 403 `forbidden`
  - 404 `not_found`
  - 409 `review_closed` (extra field: `status`)
  - 409 `stale_artifact` (extra field: `current_hash`)
  - 422 `unresolved_fields` (extra field: `fields`)
  - 422 `invalid_value` (extra fields: `field`, `detail`)
  - 422 `invalid_candidate` (extra field: `field`)
  - 422 `validation_error`

  **`POST /v1/parse-reviews/{review_id}/discard`.** Roles: `PARSE_REVIEW_ROLES`. Request:
  `{"version_hash": "sha256:…", "reason": "not_an_rfp", "note": "Newsletter, not a solicitation"}`.
  `note` is required when `reason == "other"` (max 2000). Response 200 is the summary with
  `"status": "discarded"`. Errors are the same as for resolve, minus the field errors.

  **`GET /v1/sources/schedules`.** Router `api/sources.py`; any signed-in principal. Response 200:
  ```json
  {"items": [{
    "source": "grants_gov", "label": "Grants.gov", "enabled": true, "interval_minutes": 120,
    "saved_search": {"keywords": ["youth", "mentoring"], "aln": ["16.726"], "agencies": [], "eligibilities": ["12"],
                     "statuses": ["forecasted", "posted"], "page_size": 25, "max_records": 500},
    "next_run_at": "2026-11-07T16:00:00Z",
    "last_run": {"run_id": 41, "status": "partial", "started_at": "2026-11-07T14:00:02Z", "finished_at": "2026-11-07T14:06:40Z",
                 "discovered": 37, "normalized": 3, "parse_incomplete": 1, "unchanged": 32, "failed": 1, "error": null},
    "consecutive_failures": 0,
    "configured": true
  }]}
  ```
  `configured` is `false` when the connector's `health().configured` is false. The API
  reads it from `source_schedules.configured`, which the worker writes on every tick. The API
  never calls connectors. `label` comes from a constant map in `api/sources.py`.

  **`PUT /v1/sources/schedules/{source}`.** Roles: `SOURCE_ADMIN_ROLES`. Request:
  `{"enabled": true, "interval_minutes": 120, "saved_search": { …SavedSearch… }}`. Rules:
  - all three keys are required
  - `interval_minutes` is between 15 and 1440
  - `saved_search.max_records` is at most 2000
  - `keywords` has at most 10 entries, each 2-60 characters

  Response 200 is the updated item. Errors:
  - 403 `forbidden`
  - 404 `unknown_source` (no schedule row for `source`)
  - 422 `validation_error`
- **Database** (`db/migrations/0210_discovery_and_parse_review.sql`):
  ```sql
  CREATE TABLE source_schedules (
    source_system        text PRIMARY KEY,
    enabled              boolean NOT NULL DEFAULT false,
    interval_minutes     int NOT NULL DEFAULT 120 CHECK (interval_minutes BETWEEN 15 AND 1440),
    saved_search         jsonb NOT NULL DEFAULT '{}',
    next_run_at          timestamptz NOT NULL DEFAULT now(),
    lease_until          timestamptz,
    lease_owner          text,
    configured           boolean NOT NULL DEFAULT true,
    last_status          text CHECK (last_status IN ('succeeded','partial','failed','skipped')),
    consecutive_failures int NOT NULL DEFAULT 0,
    updated_by           text,
    updated_at           timestamptz NOT NULL DEFAULT now()
  );
  INSERT INTO source_schedules (source_system, saved_search)
    VALUES ('grants_gov', '{"statuses":["forecasted","posted"],"page_size":25,"max_records":500}');

  CREATE TABLE discovery_runs (
    run_id           bigserial PRIMARY KEY,
    source_system    text NOT NULL REFERENCES source_schedules,
    search_key       text NOT NULL,
    status           text NOT NULL CHECK (status IN ('running','succeeded','partial','failed','skipped')),
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    discovered       int NOT NULL DEFAULT 0,
    normalized       int NOT NULL DEFAULT 0,
    parse_incomplete int NOT NULL DEFAULT 0,
    unchanged        int NOT NULL DEFAULT 0,
    failed           int NOT NULL DEFAULT 0,
    error            text
  );
  CREATE INDEX discovery_runs_recent ON discovery_runs (source_system, started_at DESC);

  CREATE TABLE parse_reviews (
    review_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id   uuid NOT NULL REFERENCES opportunities,
    version          int NOT NULL,
    content_hash     text NOT NULL,
    status           text NOT NULL DEFAULT 'open'
                     CHECK (status IN ('open','resolving','resolved','discarded','superseded')),
    reasons          text[] NOT NULL,
    blocking         jsonb NOT NULL,          -- list[BlockingIssue]
    questions        jsonb NOT NULL DEFAULT '[]',
    artifacts        jsonb NOT NULL DEFAULT '[]',
    resolution       jsonb,
    resolved_by      text,
    resolved_at      timestamptz,
    resolved_version int,
    discard_reason   text,
    discard_note     text,
    error            text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (opportunity_id, version) REFERENCES opportunity_versions (opportunity_id, version)
  );
  CREATE UNIQUE INDEX parse_reviews_one_active ON parse_reviews (opportunity_id)
    WHERE status IN ('open','resolving');
  CREATE INDEX parse_reviews_status ON parse_reviews (status, created_at DESC);

  -- Latest review state per opportunity, for S03 search and SC04 banners.
  CREATE VIEW opportunity_parse_status AS
    SELECT DISTINCT ON (opportunity_id) opportunity_id, review_id, status, reasons
      FROM parse_reviews ORDER BY opportunity_id, created_at DESC;

  REVOKE INSERT, UPDATE, DELETE ON source_schedules, discovery_runs, parse_reviews FROM hope_app;
  GRANT UPDATE (enabled, interval_minutes, saved_search, next_run_at, updated_by, updated_at)
    ON source_schedules TO hope_app;
  GRANT UPDATE (status, resolution, resolved_by, resolved_at, discard_reason, discard_note, updated_at)
    ON parse_reviews TO hope_app;
  GRANT SELECT ON opportunity_parse_status TO hope_app, hope_system;
  ```
  These are public tables with no RLS, matching `0200_ingestion.sql`.

## Owns

```text
services/ingestion/src/hope_ingestion/scheduler.py          (DiscoveryScheduler, PostgresScheduleStore, WorkerSettings)
services/ingestion/src/hope_ingestion/review.py             (ReviewQueue protocol, InMemoryReviewQueue, PostgresReviewQueue, ParseReviewResolver)
services/ingestion/src/hope_ingestion/worker.py             (python -m hope_ingestion.worker)
services/ingestion/src/hope_ingestion/connectors/registry.py
services/ingestion/src/hope_ingestion/pipeline.py           (reviews hook, on_record callback, ocr warning rename)
services/ingestion/src/hope_ingestion/policy.py             (fill internal_due / time_assumed)
services/ingestion/tests/test_scheduler.py
services/ingestion/tests/test_parse_review.py
services/ingestion/tests/test_review_db.py
services/ingestion/tests/test_worker.py
services/ingestion/tests/test_pipeline.py                   (ocr warning assertion only)
services/ingestion/tests/test_policy.py                     (internal_due assertions)
services/pillar/src/hope_pillar/api/parse_reviews.py
services/pillar/src/hope_pillar/api/sources.py
services/pillar/tests/test_parse_reviews_api.py
services/pillar/tests/test_sources_api.py
services/pillar/tests/snapshots/openapi/parse_reviews.json
services/pillar/tests/snapshots/openapi/sources.json
apps/web/src/features/parse-review/**
apps/web/src/api/parse-review/**
apps/web/src/app/parse-review/page.tsx
apps/web/src/app/parse-review/[reviewId]/page.tsx
db/migrations/0210_discovery_and_parse_review.sql
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 A tick claims at most one due, enabled, unleased schedule. Two schedulers ticking concurrently never run the same source.
- [ ] AC2 A disabled schedule, or one not yet due, is never run.
- [ ] AC3 The cursor is saved after every record. A run killed mid-way resumes from the last finished record, and a successful run resets the cursor.
- [ ] AC4 A run whose source fails is recorded as `failed`, backs off exponentially (capped at 24 h) and keeps its cursor. One failing record makes the run `partial` and does not stop it.
- [ ] AC5 A not-configured source is recorded as `skipped` and is not backed off.
- [ ] AC6 Run counts (`discovered`, `normalized`, `parse_incomplete`, `unchanged`, `failed`) match the `IngestResult`s.
- [ ] AC7 A blocking ingest opens exactly one review with the right `reasons`, blocking issues, questions and artifacts. A later non-blocking version supersedes it. An unchanged re-ingest leaves it alone.
- [ ] AC8 `apply_policy` sets `Deadlines.internal_due` and `ExtractedDeadline.time_assumed` (date-only deadline -> 23:59 local, `internal_due` 72 h earlier).
- [ ] AC9 `GET /v1/parse-reviews` filters by status, reason, source and `q`, sorts by `due`/`newest`/`oldest`, pages with a cursor, and returns `total` and `counts`.
- [ ] AC10 `GET /v1/parse-reviews/{id}` returns the version's opportunity, blocking issues with `kind`, `allowed_actions` and candidate evidence, injection signals, questions and artifacts.
- [ ] AC11 Resolve validates every rule in Behaviour 11 and returns the exact error codes. A valid resolve sets `resolving` and writes `opportunity.parse_review_resolved` atomically with the update.
- [ ] AC12 Resolve or discard with an old `version_hash` returns 409 `stale_artifact` with `current_hash`. On a closed review it returns 409 `review_closed`.
- [ ] AC13 Users without a `PARSE_REVIEW_ROLES` role get 403 on resolve and discard. Users without a `SOURCE_ADMIN_ROLES` role get 403 on schedule PUT.
- [ ] AC14 The resolver applies `pick` (re-parsed, original evidence kept), `enter` (human evidence, `time_stated=false` -> 23:59 + 72 h buffer) and `acknowledge`. It saves a new version with `"human"` in `pipeline_path`, marks the review `resolved` and publishes `opportunity.normalized`, caused by the resolved event.
- [ ] AC15 The resolver is idempotent on redelivery. It marks the review `superseded` when a newer version exists.
- [ ] AC16 Discard sets `discarded` without a new version, and the opportunity shows as `discarded` in `opportunity_parse_status`.
- [ ] AC17 `GET/PUT /v1/sources/schedules` return and update schedules with the documented validation. Enabling a schedule makes it due within one tick. An unknown source returns 404 `unknown_source`.
- [ ] AC18 `hope_app` cannot insert into or delete from `parse_reviews`, `source_schedules` or `discovery_runs`, and can update only the granted columns.
- [ ] AC19 `python -m hope_ingestion.worker --once` runs one tick and one consumer poll against fakes, and exits 0.
- [ ] AC20 The OpenAPI snapshots for `parse_reviews` and `sources` match. SC12's acceptance criteria pass (see `screens/SC12-parse-review.md`).

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/ingestion/tests/test_review_db.py::test_schedule_lease_is_exclusive` (two connections, `SKIP LOCKED`) | db |
| AC2 | `services/ingestion/tests/test_scheduler.py::test_disabled_and_not_due_are_skipped` | unit |
| AC3 | `test_scheduler.py::test_cursor_saved_per_record_and_resumed`, `::test_cursor_reset_after_success` | unit |
| AC4 | `test_scheduler.py::test_source_failure_backs_off`, `::test_record_failure_makes_run_partial` | unit |
| AC5 | `test_scheduler.py::test_not_configured_is_skipped_without_backoff` | unit |
| AC6 | `test_scheduler.py::test_run_counts_match_results` (Grants.gov fixtures via `httpx.MockTransport`) | unit |
| AC7 | `services/ingestion/tests/test_parse_review.py::test_blocking_ingest_opens_review`, `::test_clean_version_supersedes_review`, `::test_unchanged_reingest_keeps_review` | unit |
| AC8 | `services/ingestion/tests/test_policy.py::test_internal_due_and_time_assumed` | unit |
| AC9 | `services/pillar/tests/test_parse_reviews_api.py::test_list_filters_sort_paging_counts` | api + db |
| AC10 | `test_parse_reviews_api.py::test_detail_shape` | api + db |
| AC11 | `test_parse_reviews_api.py::test_resolve_validation_errors` (parametrized, one case per code), `::test_resolve_writes_event_atomically` | api + db |
| AC12 | `test_parse_reviews_api.py::test_stale_hash_and_closed_review` | api + db |
| AC13 | `test_parse_reviews_api.py::test_roles`, `services/pillar/tests/test_sources_api.py::test_put_requires_admin` | api |
| AC14 | `test_parse_review.py::test_resolver_pick_conflict`, `::test_resolver_enter_date_only_deadline`, `::test_resolver_acknowledge_injection` | unit |
| AC15 | `test_parse_review.py::test_resolver_idempotent`, `::test_resolver_superseded_by_newer_version` | unit |
| AC16 | `test_review_db.py::test_discard_reflected_in_parse_status_view` | db |
| AC17 | `test_sources_api.py::test_get_and_put_schedule`, `::test_enable_makes_due`, `::test_unknown_source` | api + db |
| AC18 | `test_review_db.py::test_hope_app_column_grants` | db |
| AC19 | `services/ingestion/tests/test_worker.py::test_worker_once_with_fakes` | unit |
| AC20 | `services/pillar/tests/test_openapi.py::test_router_snapshots` (existing, S00) + SC12 tests | api / web |

Commands: the CI commands in `AGENTS.md`. Regenerate the snapshots with
`UPDATE_SNAPSHOTS=1 uv run pytest services/pillar/tests/test_openapi.py`.

## Out of scope

- The OCR engine (S11).
- Foundation and portal connectors (S27). S27 adds rows to `source_schedules` and entries to `CONNECTORS`.
- The SC17 schedule UI (S01).
- Notifying reviewers about new reviews (S12 can consume `opportunity.parse_incomplete`).
- A "Run now" button.
- Template-memory learning from conflicts (blueprint 8.5).
- Per-tenant saved searches. The MVP has one global search per source.

## Decisions needed

1. **Who may resolve public opportunities once there are many tenants?** Recommended
   default: for the MVP (one tenant), any role in `PARSE_REVIEW_ROLES`. Before
   multi-tenant, move resolution to a platform "parse reviewer" role.
2. **Role names.** S01 owns the final list. Recommended default: the
   `PARSE_REVIEW_ROLES` and `SOURCE_ADMIN_ROLES` above. S01 renames them in one place if
   needed.
3. **Model provider in the worker.** Recommended default:
   - the worker builds its `ModelGateway` from S16's provider factory when `HOPE_MODEL_PROVIDER != "mock"`
   - otherwise it uses `MockProvider` plus `parsing.rule_responder.register`, the offline
     deterministic extractor that is already on `main`
4. **Run now.** Recommended default: not in this spec. If wanted, add
   `POST /v1/sources/schedules/{source}/run` (sets `next_run_at = now()`).
5. **Default search.** Recommended default: the seeded Grants.gov schedule is disabled
   until an admin sets keywords and eligibilities in SC17. The example search above uses eligibility code `"12"`, which
   is meant to be "Nonprofits having a 501(c)(3) status with the IRS, other than institutions
   of higher education". Check it against the Grants.gov eligibility code list before
   seeding any default.

## References

- `services/ingestion/src/hope_ingestion/pipeline.py`, `policy.py`, `repository.py`,
  `connectors/grants_gov.py`, `connectors/base.py`
- `db/migrations/0001_core.sql` (`opportunities`, `opportunity_versions`, `artifacts`),
  `db/migrations/0200_ingestion.sql`
- `services/pillar/src/hope_pillar/api/routes.py`: idempotency and `_one` patterns
- `docs/architecture/blueprint.md` 2.2 (A1, A2), 4.3, 6.1, 8.5
- Grants.gov `search2` / `fetchOpportunity`: https://www.grants.gov/api/common/search2 and https://www.grants.gov/api/common/fetchopportunity
