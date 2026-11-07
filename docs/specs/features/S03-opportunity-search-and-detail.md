# S03: Opportunity search and detail

| | |
|---|---|
| Wave | 1 |
| Depends on | S00 |
| Screens | [SC04](../screens/SC04-opportunity-detail.md); also serves SC02 (`deadline_before`) and SC03 (`ids=` batch) |
| Migrations | - (none reserved; see Decision 1) |
| Blueprint | 5.2 (normalized opportunity + provenance), 6.1 (sources), 7.4 (`GET /v1/opportunities/{id}`), 8.4 (classification, audit) |
| Status | Draft |

## Goal

Staff can find any opportunity Hope has ingested (not only the ones the matrix ranks), read the
whole normalized RFP with the evidence behind every extracted field, see what changed between
amendments, and open the source documents. This is the screen people use to check Hope's work
before they trust a recommendation.

## Current state

- `GET /v1/opportunities/{opportunity_id}` (`get_opportunity`, moved to
  `services/pillar/src/hope_pillar/api/opportunities.py` by S00) joins `opportunities` with the
  current `opportunity_versions` row and returns `OpportunityView`
  (`opportunity_id`, `title`, `application_due`, `normalized` = the `GrantOpportunity` JSON,
  `provenance` = `OpportunityProvenance{source_system, source_id, version, amendment_seq, content_hash, recorded_at}`).
  It returns no tenant context (is this already pursued? what's its score?).
- Opportunities are public data shared by all tenants (`opportunities`, `opportunity_versions`,
  no RLS; `hope_app` may only SELECT). Every version keeps its full `normalized` JSON.
- Source documents are rows in `artifacts` (`artifact_id`, `tenant_id` NULL for public,
  `sha256`, `storage_uri`, `media_type`, `classification`, `created_at`). The ingestion pipeline
  (`hope_ingestion.pipeline`, `hope_ingestion.artifacts.ArtifactStore.put`) stores blobs at
  `blob_key(sha256) = "sha256/<aa>/<sha256>"` and records each version's documents in
  `normalized.source.artifact_ids`. `artifacts` has no filename or size column, although
  `StoredArtifact.filename` / `.size` exist in memory (see shared addition C1).
- Evidence on every extracted field is `hope_core.schemas.common.Evidence`
  (`artifact_id`, `page`, `char_start`, `char_end`, `quote`).
- There is no list or search endpoint, no documents endpoint and no download endpoint.
  `Services.presign` (`api/deps.py`) only makes pre-signed **PUT** URLs.

## Behaviour

### Search (`GET /v1/opportunities`)

1. Any signed-in user. Reads `opportunities` joined to the current version, LEFT JOINed to
   `tenant_opportunity` for the tenant's one agency (`agency_id` from the `agencies` row, as in
   S01 `GET /v1/me`). RLS on `tenant_opportunity` keeps it to `HOPE_TENANT_ID`.
2. Query params (all optional, ANDed):
   - `q`: 2-200 chars; case-insensitive substring match on `title`, `normalized->'funder'->>'name'`,
     and `normalized->'source'->>'source_id'`, plus any value of `normalized->'funder'->'aln'`.
     Fewer than 2 non-space chars -> 422 `query_too_short`. `%` and `_` are escaped.
   - `ids`: comma-separated UUIDs, 1-100. When present, every other filter, `sort` and `cursor`
     are ignored and items come back in the order given; unknown ids are left out (no error).
     More than 100 -> 422 `too_many_ids`. (SC03 batch-loads titles this way.)
   - `funder_type`: repeatable, values of `FunderType`.
   - `source_system`: repeatable, values of `SourceSystem`.
   - `deadline_before`, `deadline_after`: ISO 8601 with offset, compared to `opportunities.application_due`.
   - `include_closed`: default `false`, which drops rows whose `application_due < now()`.
     Rows with no deadline (rolling or unknown) are always included.
   - `min_award_minor`, `max_award_minor`: integers in minor units, compared with
     `(normalized->'funding'->'award_ceiling'->>'amount_minor')::bigint`. Rows with no ceiling are excluded
     when either bound is set.
   - `tracked`: `true` = only rows with a `tenant_opportunity` row, `false` = only untracked rows.
   - `state`: repeatable `OpportunityState` values (implies `tracked=true`).
   - `sort`: `due` (default: `application_due ASC NULLS LAST, opportunity_id`), `recent`
     (`current version recorded_at DESC`), `award` (ceiling `DESC NULLS LAST`), `score`
     (`tenant_opportunity.composite_score DESC NULLS LAST`).
   - `limit` 1-100 (default 25), `cursor` (opaque base64url JSON of the sort key + `opportunity_id`;
     a cursor made for another `sort` -> 422 `invalid_cursor`).
3. `total` counts all rows matching the filters (no `limit`); it is computed with a second
   `count(*)` query and capped at 10,000 (`total_capped: true` beyond that).
4. Each item is an `OpportunitySummary` built only from stored data (no LLM): `summary` is
   `normalized.summary` truncated to 280 chars on a word boundary with `…`.

### Detail (`GET /v1/opportunities/{opportunity_id}`)

5. Unchanged fields plus two additive fields: `tenant` (the `tenant_opportunity` row for the
   agency, or `null`) and `version_count`. Optional `?version=n` returns that version's `normalized`
   and provenance instead of the current one (404 `not_found` for an unknown version). The response model
   stays `OpportunityView`, extended (the S00 route-inventory test still passes because method, path and
   model name don't change).

### Documents and versions (`GET /v1/opportunities/{opportunity_id}/documents`)

6. Returns every version, newest first. For each version: `version`, `amendment_seq`,
   `recorded_at`, `content_hash`, `changes` and `documents`.
7. `changes` lists the dotted paths whose value differs from the previous version. The diff is
   deterministic and covers this fixed list (in order): `title`, `summary`, `deadlines.application_due`,
   `deadlines.loi_due`, `deadlines.questions_due`, `funding.award_ceiling`, `funding.award_floor`,
   `funding.total_program_funding`, `funding.cost_share`, `funding.indirect_cost_policy`,
   `eligibility.applicant_types`, `eligibility.geographic_restrictions`, `eligibility.required_registrations`,
   `eligibility.clauses`, `requirements.sections`, `requirements.forms`, `requirements.attachments`,
   `requirements.submission_channel`. For a value path the item includes `before` and `after` (the JSON values; for
   `deadlines.*` only `.value`); for list paths it includes only `path` (the UI says "changed"). The first version has `changes: []`.
8. `documents` are the artifacts named in that version's `normalized.source.artifact_ids`, joined to
   `artifacts` by `artifact_id` (RLS lets the tenant see public rows and its own). An id with no visible
   row appears with `"available": false` and nulls (it was quarantined or belongs to another tenant).
   `status` is `added` (not in the previous version), `unchanged`, or `removed`. Removed artifacts are
   listed once in the version that dropped them.
9. `filename` and `size_bytes` come from the columns added by C1; if they are null the API returns
   `filename = "<first 12 hex of sha256>.<ext>"` (`.pdf`, `.docx`, `.xlsx`, `.zip`, `.txt`, `.html`, else `.bin`)
   and `size_bytes = null`.

### Download (`GET /v1/artifacts/{sha256}/download`)

10. `sha256` must match `^[a-f0-9]{64}$` (else 422 `validation_error`). Optional `artifact_id`
    picks one row when several share the hash. Otherwise the tenant's own row wins over the public row.
    No visible row -> 404 `not_found` (never 403, so existence of other tenants' files isn't revealed).
11. Classification rules: `public` and `internal` any signed-in user; `confidential` any signed-in user,
    audited; `restricted` only `org_admin`, `finance_director` or `compliance_officer`, audited, others
    403 `forbidden`.
12. For `confidential` and `restricted`, write `artifact.downloaded` via `write_audit`
    (`subject = "artifact:<artifact_id>"`, `detail = {sha256, classification, disposition}`) in the request
    transaction, before returning the URL.
13. `disposition`: `inline` (default for `application/pdf`, `text/plain`) or `attachment` (default
    otherwise). The URL is a pre-signed S3 **GET** for the bucket and key parsed from `storage_uri`
    (`s3://<bucket>/<key>`; any other scheme -> 409 `unsupported_storage`), with
    `ResponseContentDisposition` set from the filename and `ResponseContentType` = `media_type`,
    valid for 300 s.
14. The presigner is the FastAPI dependency `hope_pillar.storage.get_download_presigner`
    (boto3 client built from `HopeSettings.s3_*`), overridden in tests with a fake.

## Contracts

- **Shared models used:** `GrantOpportunity`, `Source`, `Funder`, `FunderType`, `SourceSystem`,
  `Funding`, `Deadlines`, `Evidence` (`hope_core.schemas.grant_opportunity`, `common`), `Money`,
  `OpportunityState`, `Principal`, `Problem`.
- **Shared contract additions:**
  - **C1** (S00 migration `0002_shared.sql` + import-level change in `hope_ingestion.repository`):
    `ALTER TABLE artifacts ADD COLUMN filename text, ADD COLUMN size_bytes bigint;` and
    `PostgresArtifactIndex.insert` writes `StoredArtifact.filename` / `.size`. Without it, every document
    shows the generated name from step 9.
  - **C2** `hope_core.audit.write_audit` (same as S01 A3 / S13 B1).
  - **C3** Web `nav.ts`: `/opportunities` list entry (label "Opportunities") if the list route in
    the catalog changes is accepted.
- **Events:** none produced or consumed.
- **Endpoints** (router `services/pillar/src/hope_pillar/api/opportunities.py`):

  `GET /v1/opportunities?q=mentoring&sort=due&limit=2` -> 200:
  ```json
  {
    "items": [{
      "opportunity_id": "3f6c1d2e-9a7b-4c1d-8e2f-1a2b3c4d5e6f",
      "title": "Youth Mentoring Expansion",
      "summary": "Funds community-based mentoring for youth at risk of justice involvement…",
      "funder": {"name": "Office of Juvenile Justice and Delinquency Prevention", "type": "federal", "aln": ["16.726"]},
      "source": {"system": "grants_gov", "source_id": "O-OJJDP-2026-0042", "url": "https://www.grants.gov/search-results-detail/356789"},
      "funding": {"award_ceiling": {"amount_minor": 25000000, "currency": "USD"},
                  "award_floor": {"amount_minor": 5000000, "currency": "USD"}, "cost_share_required": true},
      "deadlines": {"application_due": {"value": "2026-11-19T23:59:00-05:00", "timezone": "America/New_York"}, "rolling": false},
      "parse_confidence": 0.93,
      "version": 2,
      "amendment_seq": 1,
      "recorded_at": "2026-11-05T11:20:00Z",
      "tenant": {"state": "AwaitingGoNoGo", "workflow_id": "wf-7f3a", "composite_score": 87.0, "recommendation": "pursue"}
    }],
    "total": 14,
    "total_capped": false,
    "next_cursor": "eyJzIjoiZHVlIiwiayI6WyIyMDI2LTExLTE5VDA0OjU5OjAwWiIsIjNmNmMxZDJlLi4uIl19"
  }
  ```
  `tenant` is `null` for untracked rows. 422 `query_too_short` | `too_many_ids` | `invalid_cursor` | `validation_error`.

  `GET /v1/opportunities/{opportunity_id}[?version=n]` -> 200: today's `OpportunityView` plus
  `"tenant": {...} | null` and `"version_count": 2`. 404 `not_found`.

  `GET /v1/opportunities/{opportunity_id}/documents` -> 200:
  ```json
  {
    "opportunity_id": "3f6c1d2e-9a7b-4c1d-8e2f-1a2b3c4d5e6f",
    "versions": [
      {
        "version": 2, "amendment_seq": 1, "recorded_at": "2026-11-05T11:20:00Z", "content_hash": "sha256:5d1e…",
        "changes": [
          {"path": "deadlines.application_due", "before": "2026-11-12T23:59:00-05:00", "after": "2026-11-19T23:59:00-05:00"},
          {"path": "requirements.attachments"}
        ],
        "documents": [
          {"artifact_id": "a1…", "sha256": "9f2c…", "media_type": "application/pdf", "filename": "NOFO-amendment-1.pdf",
           "size_bytes": 1843200, "classification": "public", "status": "added", "available": true},
          {"artifact_id": "b2…", "sha256": "77c0…", "media_type": "application/pdf", "filename": "NOFO.pdf",
           "size_bytes": 2211840, "classification": "public", "status": "unchanged", "available": true}
        ]
      },
      {"version": 1, "amendment_seq": 0, "recorded_at": "2026-10-20T08:00:00Z", "content_hash": "sha256:01aa…",
       "changes": [], "documents": [ "…" ]}
    ]
  }
  ```
  404 `not_found`.

  `GET /v1/artifacts/{sha256}/download?disposition=inline` -> 200:
  ```json
  {"url": "https://s3.example/hope-artifacts/sha256/9f/9f2c…?X-Amz-Expires=300&…", "expires_in": 300,
   "media_type": "application/pdf", "filename": "NOFO-amendment-1.pdf", "size_bytes": 1843200}
  ```
  403 `forbidden`; 404 `not_found`; 409 `unsupported_storage`; 422 `validation_error`.

- **Database:** no migration. Queries use the existing PK and `UNIQUE (source_system, source_id)`;
  search is a sequential scan, which is fine below about 50,000 opportunities (Decision 1).

## Owns

```text
services/pillar/src/hope_pillar/api/opportunities.py (not the ingest routes, which stay in api/ingest.py)
services/pillar/src/hope_pillar/storage.py
services/pillar/src/hope_pillar/opportunity_diff.py
services/pillar/tests/test_opportunities_api.py
services/pillar/tests/test_opportunity_diff.py
services/pillar/tests/snapshots/openapi/opportunities.json
apps/web/src/features/opportunities/**
apps/web/src/api/opportunities/**
apps/web/src/app/opportunities/page.tsx
apps/web/src/app/opportunities/[opportunityId]/page.tsx
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 `q` matches title, funder name, source id and ALN case-insensitively, escapes `%`/`_`, and rejects 1-char queries with `query_too_short`.
- [ ] AC2 Every filter (`funder_type`, `source_system`, deadline range, `include_closed`, award bounds, `tracked`, `state`) narrows results correctly; rolling rows survive the closed filter.
- [ ] AC3 Each `sort` orders correctly, the cursor walks every row exactly once, and a cursor from another sort is 422.
- [ ] AC4 `ids=` returns items in the given order, skips unknown ids, and rejects more than 100.
- [ ] AC5 `total` matches the filtered count, and `tenant` is filled only for the tenant's own tracked rows.
- [ ] AC6 Detail returns `tenant`, `version_count`, and `?version=n`; an unknown version is 404.
- [ ] AC7 The documents endpoint lists versions newest first, with `changes` from the fixed path list (`before`/`after` for value paths) and per-document `status` `added`/`unchanged`/`removed`.
- [ ] AC8 A document whose artifact isn't visible shows `available: false`; a missing filename falls back to the generated name.
- [ ] AC9 Download returns a 300 s pre-signed GET with the right disposition; another tenant's artifact is 404; `restricted` is 403 for other roles.
- [ ] AC10 Downloading a `confidential` or `restricted` artifact writes one `artifact.downloaded` audit row; `public` writes none.
- [ ] AC11 The `opportunities.json` snapshot matches.
- [ ] AC12 SC04 meets its screen acceptance criteria.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/pillar/tests/test_opportunities_api.py::test_search_q` | db |
| AC2 | `services/pillar/tests/test_opportunities_api.py::test_search_filters` (parametrized) | db |
| AC3 | `services/pillar/tests/test_opportunities_api.py::test_sorts_and_cursor` | db |
| AC4 | `services/pillar/tests/test_opportunities_api.py::test_batch_ids` | db |
| AC5 | `services/pillar/tests/test_opportunities_api.py::test_total_and_tenant_context` | db |
| AC6 | `services/pillar/tests/test_opportunities_api.py::test_detail_tenant_and_version` | db |
| AC7 | `services/pillar/tests/test_opportunity_diff.py::test_changes_between_versions` (unit), `test_opportunities_api.py::test_documents_versions` (db) | unit, db |
| AC8 | `services/pillar/tests/test_opportunities_api.py::test_unavailable_and_fallback_filename` | db |
| AC9 | `services/pillar/tests/test_opportunities_api.py::test_download_presign_and_access` | db |
| AC10 | `services/pillar/tests/test_opportunities_api.py::test_download_audited_by_classification` | db |
| AC11 | `services/pillar/tests/test_openapi.py::test_router_snapshots` | api |
| AC12 | see SC04 | unit |

Fixtures: `hope_core.testing.factories.grant_opportunity()` inserted as admin into
`opportunities`/`opportunity_versions` (two versions for one opportunity), with `artifacts` rows for
public, tenant-A and tenant-B documents.

## Out of scope

Full-text ranking and saved searches (S10), the pursue endpoint (S04), matrix scores (S05), parse
corrections (S10), an in-app PDF viewer, and virus re-scanning on download (S30).

## Decisions needed

1. **Search index.** Recommended: no index for MVP (sequential scan with `ILIKE`). When the
   catalogue passes about 50,000 opportunities, add a `pg_trgm` GIN index; that needs a reserved
   migration number (proposed: `0130` for this spec).
2. **Search scope.** Recommended: search all opportunities, not only tracked ones (Hope's job is
   discovery). `tracked=true` gives the narrower view.
3. **Restricted downloads.** Recommended: `org_admin`, `finance_director`, `compliance_officer`.
   Opportunity documents are almost always public; restricted files are the agency's own uploads.
4. **Pursue roles on SC04.** SC03 uses `program_director` and `executive_director`, but today's
   workflow routes HITL-1 to `development_director`. Recommended: S04 accepts `development_director`,
   `program_director` and `executive_director`, and S01's `Role` list includes `program_director`.

## References

- `services/pillar/src/hope_pillar/api/routes.py::get_opportunity` (today), `api/models.py::OpportunityView`
- `services/ingestion/src/hope_ingestion/artifacts.py::ArtifactStore`, `blob_key`; `services/ingestion/src/hope_ingestion/repository.py`
- `packages/core/src/hope_core/schemas/grant_opportunity.py`, `schemas/common.py::Evidence`
- Blueprint 5.2, 6.1, 7.4, 8.4
