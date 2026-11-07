# M1: Opportunities (live Grants.gov pull, search API, detail page)

> **Out of scope for the hackathon. Don't build this.** This spec belongs to the earlier design (the Phase 1 pipeline and the M0-M7 / S-spec roadmap). Hackathon agents build only H0-H5 (see [`README.md`](../README.md)). Keep this file for after the hackathon.

| | |
|---|---|
| Wave | MVP (runs in parallel with M2-M7 after M0) |
| Depends on | M0 |
| Screens | [SC04](../screens/SC04-opportunity-detail.md) (plus the small `/opportunities` list in SC04 section 3) |
| Migrations | `db/migrations/0210_artifact_metadata.sql` (range 0210-0219) |
| Blueprint | 5.2 (normalized opportunity + provenance), 6.1 (Grants.gov), 7.4 (`GET /v1/opportunities/{id}`) |
| Replaces for the MVP | S03 and the discovery part of S10 (full versions stay Draft on `specs/pillar`) |
| Status | Draft |

## Goal

The demo runs on **real federal opportunities**. One command pulls live opportunities from
Grants.gov, parses them into `GrantOpportunity` rows, and stores their documents. The pillar
API lets the web app search them and open one, and SC04 shows a polished detail page with the
key facts, eligibility, requirements and source documents. `make demo` works offline, because
the seed loads a recorded set of real opportunities.

## Current state

On `main` after M0:

- `hope_ingestion.connectors.grants_gov.GrantsGovConnector` (`search` = `search2`,
  `fetch_opportunity` = `fetchOpportunity`, `discover`, `fetch_artifacts`, `download`, `facts`,
  `health`) works against the public API. `facts_from_detail` maps the detail JSON to
  `SourceFacts` (title, agency, ALN, summary, `responseDateStr` due date, award ceiling/floor,
  estimated funding, number of awards, cost sharing, applicant types).
- `hope_ingestion.pipeline.IngestionPipeline.run(connector, query, cursor)` downloads documents,
  stores them through `ArtifactStore` (`blob_key(sha256) = "sha256/<aa>/<sha256>"`), stores the
  detail JSON itself as an `application/json` artifact (`_store_metadata`), parses the documents
  with `SectionExtractor` (via `ModelGateway`), applies `policy.apply_policy`, saves a version with
  `OpportunityRepository.save`, and publishes `opportunity.raw_ingested`, then
  `opportunity.normalized` or `opportunity.parse_incomplete` (and `opportunity.amended`) to a `PillarPort`.
- `hope_ingestion.repository.PostgresIngestionStore` implements the repository and the artifact index on
  `HOPE_DATABASE_SYSTEM_URL` (`hope_app` can't write `opportunities`). `artifacts` has no `filename` or
  size column, so `StoredArtifact.filename` is lost on insert.
- Blobs: `InMemoryBlobStore` and `S3BlobStore` (MinIO). MinIO may not start locally (the
  `minio/minio` image pull has been denied on dev VMs), so the demo can't rely on it.
- The only live entry point is `services/ingestion/scripts/grants_gov_smoke.py`, which uses
  `testing.offline_pipeline()` (in-memory everything). Nothing persists a live pull.
- Recorded fixtures: `services/ingestion/tests/fixtures/grants_gov/search2_youth_mentoring.json`
  (98 hits) and `fetch_opportunity_364058.json` (`O-OJJDP-2026-172743`, "OJJDP FY 2026 Mentoring for
  Youth Impacted by Opioids and Other Substance Use", due 2026-11-16, ceiling $2,000,000, ALN 16.726).
- Pillar: M0 moved `get_opportunity` into `services/pillar/src/hope_pillar/api/opportunities.py` and
  created the `opportunities.json` snapshot. It returns `OpportunityView` (`opportunity_id`, `title`,
  `application_due`, `normalized`, `provenance`). There is no list, documents or download endpoint.
- Web: M0 created `apps/web/src/api/opportunities/` (with today's `getOpportunity`) and a `ComingSoon`
  placeholder at `apps/web/src/app/opportunities/[opportunityId]/page.tsx`.

## Behaviour

### Ingestion: live pull and recorded loads

1. **Blob store.** New `hope_ingestion.artifacts.LocalBlobStore(root: Path)`: writes
   `<root>/<blob_key>` once (it skips the write if the file exists) and returns `file://<absolute path>`.
   `blob_store_from_settings()` picks it from `IngestionSettings.blob_store: Literal["local", "s3"] = "local"`
   and `blob_dir: Path = Path(".hope/blobs")` (env `HOPE_BLOB_STORE`, `HOPE_BLOB_DIR`). `s3` keeps
   `S3BlobStore`.
2. **Artifact metadata.** `PostgresIngestionStore.insert` also writes `filename` and `size_bytes`
   (columns added by `0210`). `find` returns them. Filenames are sanitized: basename only, at most 200 chars,
   control characters removed.
3. **Outbox publisher.** New `hope_ingestion.outbox.OutboxPublisher(url)`, a publish-only `PillarPort`:
   `publish(envelope)` inserts into `outbox` (`event_id`, `tenant_id` = NULL, which is platform data, `topic`
   from `EVENT_TOPIC`, `partition_key = subject_id`, `envelope`) with `ON CONFLICT (event_id) DO NOTHING`.
   The other `PillarPort` methods raise `NotImplementedError`. Events reach Kafka whenever the pillar
   relay runs; nothing in the MVP demo needs them to arrive (Decision 3).
4. **Command `hope-ingest`** (`hope_ingestion.cli:main`, a console script in
   `services/ingestion/pyproject.toml`):
   - `hope-ingest grants-gov [KEYWORDS...] --rows N (default 10, max 50) [--aln 16.726] [--no-documents] [--record DIR]`
     builds `IngestionPipeline(pillar=OutboxPublisher, gateway=default_gateway(), artifacts=ArtifactStore(blob_store_from_settings(), store),
     repository=store)` with `store = PostgresIngestionStore()` and runs `GrantsGovConnector` with
     `SavedSearch(keywords, aln, statuses=["posted"], page_size=N, max_records=N)`.
     `--no-documents` skips downloads (facts from the detail JSON only). `--record DIR` also writes each
     `fetchOpportunity` response to `DIR/<opportunityId>.json` and each downloaded document to
     `DIR/docs/<sha256>` with its filename in `DIR/docs/index.json`, which is how the seed data is made.
   - `hope-ingest load DIR [--no-documents]` replays a recorded directory through the same pipeline with a
     `RecordedGrantsGovConnector` (new, in `connectors/recorded.py`) that serves the JSON and docs from disk.
     No network.
   - Each run prints one line per opportunity (`normalized | O-OJJDP-2026-172743 | OJJDP FY 2026 Mentoring… | due 2026-11-16`,
     or `parse_incomplete | <id> | <title> | missing: deadlines.application_due`, or `unchanged | …`) and a summary
     `10 pulled: 8 normalized, 1 parse_incomplete, 1 unchanged`. Exit code 0 unless the connector fails.
   - Errors: Grants.gov unreachable or `errorcode != 0` -> stderr `Grants.gov is unavailable: <reason>` and exit 2,
     nothing written for the failing record (earlier records stay committed). A document download failure
     is logged as a warning and the opportunity is still ingested from its facts. A document rejected by
     `ArtifactStore` (wrong type, active content) is quarantined as today.
5. **LLM.** Extraction runs through `default_gateway()` (OpenAI when `HOPE_OPENAI_API_KEY` is set, otherwise
   `MockProvider` + `rule_responder`, which still produces deterministic findings). Ingested text is wrapped in
   `untrusted()` as today. The LLM never produces money amounts: ceilings, floors and totals come from the
   detail JSON (`facts_from_detail`) only.
6. **Parse incomplete.** Opportunities with blocking issues are still saved (as today) and still appear in the
   API, with `parse_quality.missing_critical_fields` filled; SC04 explains what's missing. There is no review queue in the MVP.
7. **Idempotency.** Re-running a pull or load for unchanged opportunities returns `unchanged` and writes nothing
   (the existing artifact-id comparison). A new Grants.gov revision with different documents becomes a new version
   (`amendment_seq + 1`).

### Demo seed

8. `hope_ingestion.demo.seed()` (called by M0's `hope-demo-seed`) runs `hope-ingest load` on the package data
   directory `services/ingestion/src/hope_ingestion/demo_data/grants_gov/`, with `--no-documents` **off**. It is
   idempotent (step 7) and makes no network calls.
9. The directory holds **6 real Grants.gov opportunities**, recorded once with
   `hope-ingest grants-gov --record` during implementation, chosen so the demo matrix has variety:

   | # | Recorded from | Why it's in the demo |
   |---|---|---|
   | 1 | `364058` / `O-OJJDP-2026-172743` (already in `tests/fixtures/grants_gov/`) | The hero opportunity: youth mentoring, $2M ceiling, a clear deadline |
   | 2 | keyword `after school` (a posted ED or HHS youth program) | Strong mission fit for the demo agency |
   | 3 | keyword `food security` (a posted USDA program) | A second fit, different funder |
   | 4 | keyword `workforce development` (a posted DOL program) | A medium fit |
   | 5 | keyword `diabetes research` (`359145` / `RFA-DK-26-310` is in the recorded search) | A clear mismatch (research centres), so the matrix can show "Skip" |
   | 6 | any posted opportunity with no award ceiling | Shows the "Not stated" state and a parse-incomplete banner |

   Rules for choosing: status `posted`, application due at least 30 days after the planned demo date, and at least
   one with a PDF NOFO under 3 MB (stored under `demo_data/grants_gov/docs/`; the directory stays under 10 MB in total).
   Others get `--no-documents` recordings. `demo_data/grants_gov/README.md` lists the recording command, date and ids.
10. The seed prints `Seeded 6 Grants.gov opportunities (5 open)` and warns `Only N seeded opportunities are still open`
    if fewer than 3 have a future due date (the recordings need refreshing before the demo).

### Pillar API (`services/pillar/src/hope_pillar/api/opportunities.py`)

11. Every endpoint works for any signed-in user (any M0 `Role`; with M0's demo defaults, any request). Data is
    public opportunities joined, where it exists, to the tenant's `tenant_opportunity` row for `HOPE_AGENCY_ID`.
12. `GET /v1/opportunities`:
    - `q` (optional, 2-100 chars after trimming, else 422 `query_too_short` / `validation_error`): case-insensitive
      substring match on `opportunities.title`, `normalized->'funder'->>'name'` and `source_id`. `%` and `_` are escaped.
    - `ids` (optional, comma-separated UUIDs, 1-50, else 422 `too_many_ids`): returns those rows in the order given and
      ignores every other parameter. Unknown ids are skipped. (SC03 batch-loads titles this way.)
    - `include_closed` (default `false`): hides rows whose `application_due` is in the past. Rows with no due date stay.
    - `sort`: `due` (default: `application_due ASC NULLS LAST, opportunity_id`) or `recent`
      (current version `recorded_at DESC, opportunity_id`).
    - `limit` 1-50 (default 20), `cursor` (opaque base64url JSON `{"s": sort, "k": [key, id]}`; a bad cursor or one
      from the other sort -> 422 `invalid_cursor`).
    - `total` is the filtered count (no limit).
13. `GET /v1/opportunities/{opportunity_id}` keeps today's fields and adds `tenant` (see the JSON) and
    `documents_count`. Unknown id -> 404 `not_found`.
14. `GET /v1/opportunities/{opportunity_id}/documents` lists the documents of the **current** version:
    the artifacts in `normalized.source.artifact_ids` joined to `artifacts`, excluding `media_type = 'application/json'`
    (the stored detail JSON), ordered by filename. A listed id with no visible `artifacts` row is returned with
    `available: false`. A missing filename becomes `"<first 12 hex of sha256>.<ext>"` (`.pdf`, `.docx`, `.html`,
    `.txt`, else `.bin`).
15. `GET /v1/artifacts/{sha256}/download?disposition=inline|attachment` **streams the file** (no pre-signed URL, so
    it works without MinIO). It finds the artifact row by `sha256` (the tenant's own row first, then the public one),
    reads `storage_uri` (`file://` from disk; `s3://bucket/key` with boto3 using `HopeSettings.s3_*`), and returns it with
    `Content-Type` = `media_type`, `Content-Length`, `Content-Disposition: inline|attachment; filename="<filename>"`
    (RFC 6266 `filename*` for non-ASCII), `Cache-Control: private, max-age=300`, and `X-Content-Type-Options: nosniff`.
    Default disposition: `inline` for PDF and plain text, otherwise `attachment`. HTML is always sent as `attachment`
    (it's untrusted source content). `sha256` not matching `^[a-f0-9]{64}$` -> 422 `validation_error`; no visible row,
    or a missing blob -> 404 `not_found`; `classification = 'restricted'` and the principal lacks `admin` -> 403 `forbidden`.
16. All errors use M0's `application/problem+json` (`lib/problem.ts` maps them on the web).

### Web

17. `apps/web/src/api/opportunities/`: `types.ts` (`OpportunitySummary`, `OpportunityPage`, `OpportunityDetail`,
    `OpportunityDocument`), `http.ts` (`searchOpportunities(query)`, `getOpportunity(id)`, `listDocuments(id)`,
    `downloadUrl(sha256, disposition)`, which only builds the URL), `fixture.ts` (SC04 section 11), and `index.ts`.
    Pursue goes through M4's `api/workflow` client (`pursue(opportunityId)`); M1 doesn't define it.
18. `apps/web/src/features/opportunities/`: `OpportunityDetail.tsx`, `KeyFacts.tsx`, `DocumentsPanel.tsx`,
    `OpportunityList.tsx`, and their tests. `apps/web/src/app/opportunities/[opportunityId]/page.tsx` and
    `apps/web/src/app/opportunities/page.tsx` render them.

## Contracts

- **Shared models used:** `GrantOpportunity`, `Source`, `Funder`, `Funding`, `Deadlines`, `Eligibility`,
  `Requirements`, `ParseQuality`, `Evidence` (`hope_core.schemas`), `Money`, `PillarEnvelope`, `EVENT_TOPIC`,
  `EventType`, `ModelGateway` / `default_gateway()` (M0), `Principal` / `Role` (M0), the M0 Problem model.
- **Requests to M0** (see the end of this spec).
- **Events:** produces `opportunity.raw_ingested` (`gop.ingest.raw`), `opportunity.normalized`,
  `opportunity.parse_incomplete` and `opportunity.amended` (`gop.opportunity.events`) through the outbox,
  with today's payload models. Consumes none.
- **Endpoints:**

  `GET /v1/opportunities?q=mentoring&limit=2` -> 200
  ```json
  {
    "items": [
      {
        "opportunity_id": "3f6c1d2e-9a7b-4c1d-8e2f-1a2b3c4d5e6f",
        "title": "OJJDP FY 2026 Mentoring for Youth Impacted by Opioids and Other Substance Use",
        "funder": {"name": "Office of Juvenile Justice Delinquency Prevention", "type": "federal", "aln": ["16.726"]},
        "source": {"system": "grants_gov", "source_id": "O-OJJDP-2026-172743",
                   "url": "https://www.grants.gov/search-results-detail/364058"},
        "summary": "OJJDP seeks applications for mentoring services for youth impacted by opioids and other substance use…",
        "award_ceiling": {"amount_minor": 200000000, "currency": "USD"},
        "award_floor": null,
        "application_due": "2026-11-16T00:00:00-05:00",
        "due_timezone": "America/New_York",
        "rolling": false,
        "parse_confidence": 0.91,
        "missing_critical_fields": [],
        "recorded_at": "2026-11-08T14:05:12Z",
        "tenant": {"state": "Recommended", "workflow_id": null, "composite_score": 87.0, "recommendation": "pursue"}
      }
    ],
    "total": 1,
    "next_cursor": null
  }
  ```
  `summary` is `normalized.summary` cut to 280 chars on a word boundary with `…`. `tenant` is `null` when
  the agency has no `tenant_opportunity` row. Errors: 422 `query_too_short`, `too_many_ids`, `invalid_cursor`,
  `validation_error`.

  `GET /v1/opportunities/3f6c1d2e-9a7b-4c1d-8e2f-1a2b3c4d5e6f` -> 200
  ```json
  {
    "opportunity_id": "3f6c1d2e-9a7b-4c1d-8e2f-1a2b3c4d5e6f",
    "title": "OJJDP FY 2026 Mentoring for Youth Impacted by Opioids and Other Substance Use",
    "application_due": "2026-11-16T00:00:00-05:00",
    "normalized": {"opportunity_id": "3f6c1d2e-…", "source": {"system": "grants_gov", "source_id": "O-OJJDP-2026-172743", "url": "https://www.grants.gov/search-results-detail/364058", "artifact_ids": ["…"], "amendment_seq": 0},
                   "title": "…", "funder": {"name": "Office of Juvenile Justice Delinquency Prevention", "type": "federal", "aln": ["16.726"]},
                   "summary": "…", "deadlines": {"application_due": {"value": "2026-11-16T00:00:00-05:00", "timezone": "America/New_York", "confidence": 1.0, "evidence": [{"artifact_id": "…", "page": 1, "quote": "responseDate: Nov 16, 2026"}]}, "rolling": false},
                   "funding": {"award_ceiling": {"amount_minor": 200000000, "currency": "USD"}, "expected_awards": 10, "evidence": ["…"]},
                   "eligibility": {"applicant_types": ["Nonprofits having a 501(c)(3) status with the IRS, other than institutions of higher education"], "clauses": ["…"]},
                   "requirements": {"sections": ["…"], "forms": ["SF-424", "SF-424A", "SF-LLL"], "submission_channel": "grants_gov"},
                   "parse_quality": {"overall_confidence": 0.91, "missing_critical_fields": [], "warnings": [], "injection_suspected": false, "pipeline_path": ["native_text"]}},
    "provenance": {"source_system": "grants_gov", "source_id": "O-OJJDP-2026-172743", "version": 1, "amendment_seq": 0,
                   "content_hash": "sha256:5d1e…", "recorded_at": "2026-11-08T14:05:12Z"},
    "tenant": {"state": "Recommended", "workflow_id": null, "composite_score": 87.0, "recommendation": "pursue"},
    "documents_count": 2
  }
  ```
  (`normalized` is the full `GrantOpportunity`; it's abbreviated here.) Errors: 404 `not_found`, 422 `validation_error`.

  `GET /v1/opportunities/3f6c1d2e-…/documents` -> 200
  ```json
  {
    "opportunity_id": "3f6c1d2e-9a7b-4c1d-8e2f-1a2b3c4d5e6f",
    "version": 1,
    "documents": [
      {"artifact_id": "8a0f…", "sha256": "9f2c4b…e01a", "filename": "ojjdp-2026-172743.pdf",
       "media_type": "application/pdf", "size_bytes": 1843200, "available": true},
      {"artifact_id": "b71d…", "sha256": "77c01d…3f9b", "filename": "77c01d3f9b2a.html",
       "media_type": "text/html", "size_bytes": null, "available": true}
    ]
  }
  ```
  Errors: 404 `not_found`.

  `GET /v1/artifacts/9f2c4b…e01a/download` -> 200, body = the file bytes, headers
  `Content-Type: application/pdf`, `Content-Disposition: inline; filename="ojjdp-2026-172743.pdf"`.
  Errors: 403 `forbidden`, 404 `not_found`, 422 `validation_error` (problem+json bodies).

- **Database** (`db/migrations/0210_artifact_metadata.sql`):
  ```sql
  ALTER TABLE artifacts ADD COLUMN filename text, ADD COLUMN size_bytes bigint CHECK (size_bytes >= 0);
  ```
  No new tables. Search uses a sequential scan; that's fine for the demo's dozens of rows.

## Owns

```text
services/ingestion/**   (incl. src/hope_ingestion/{cli.py,outbox.py,demo.py,connectors/recorded.py,demo_data/**}, pyproject.toml script entry, tests/**)
services/pillar/src/hope_pillar/api/opportunities.py
services/pillar/tests/test_opportunities_api.py
services/pillar/tests/snapshots/openapi/opportunities.json
apps/web/src/features/opportunities/**
apps/web/src/api/opportunities/**
apps/web/src/app/opportunities/**
db/migrations/0210_artifact_metadata.sql
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 `hope-ingest grants-gov` against a recorded HTTP transport persists normalized opportunities, versions and artifacts (with filename and size) to Postgres, writes outbox events, and prints the per-opportunity lines and summary.
- [ ] AC2 `--record DIR` writes the detail JSON and documents, and `hope-ingest load DIR` replays them into an identical result with no network.
- [ ] AC3 Re-running a pull or load on unchanged data reports `unchanged` and writes no new versions, artifacts or outbox rows.
- [ ] AC4 Grants.gov failures exit 2 with the message; a failed document download still ingests the opportunity from its facts.
- [ ] AC5 Money fields come only from the detail JSON (a MockProvider that returns an amount doesn't change `award_ceiling`).
- [ ] AC6 `LocalBlobStore` writes each blob once under `HOPE_BLOB_DIR` and returns a `file://` URI.
- [ ] AC7 `demo.seed()` loads the 6 recorded opportunities offline, is idempotent, and warns when fewer than 3 are open.
- [ ] AC8 `GET /v1/opportunities`: `q` matches title, funder and source id; closed rows are hidden by default; both sorts and the cursor walk all rows once; `total` is right; `ids` keeps order and skips unknown ids; each 422 code fires.
- [ ] AC9 Detail returns `tenant` and `documents_count`; an unknown id is 404 problem+json.
- [ ] AC10 Documents lists the current version's files without the JSON metadata artifact, with `available: false` and the fallback filename where needed.
- [ ] AC11 Download streams `file://` and `s3://` blobs with the right headers (HTML forced to attachment), returns 404 for a missing blob or another tenant's artifact, and 403 for restricted without `admin`.
- [ ] AC12 The `opportunities.json` snapshot matches.
- [ ] AC13 SC04 meets its acceptance criteria.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/ingestion/tests/test_cli.py::test_grants_gov_pull_persists` | db |
| AC2 | `services/ingestion/tests/test_cli.py::test_record_then_load_roundtrip` | db |
| AC3 | `services/ingestion/tests/test_cli.py::test_rerun_is_unchanged` | db |
| AC4 | `services/ingestion/tests/test_cli.py::test_grants_gov_down_exits_2`, `::test_document_failure_keeps_opportunity` | unit |
| AC5 | `services/ingestion/tests/test_pipeline.py::test_money_never_from_llm` | unit |
| AC6 | `services/ingestion/tests/test_artifacts_dedup.py::test_local_blob_store` | unit |
| AC7 | `services/ingestion/tests/test_demo.py::test_seed_offline_and_idempotent`, `::test_seed_warns_when_stale` | db |
| AC8 | `services/pillar/tests/test_opportunities_api.py::test_search` (parametrized: q, closed, sorts, cursor, total, ids, errors) | db |
| AC9 | `services/pillar/tests/test_opportunities_api.py::test_detail_tenant_and_404` | db |
| AC10 | `services/pillar/tests/test_opportunities_api.py::test_documents_current_version` | db |
| AC11 | `services/pillar/tests/test_opportunities_api.py::test_download_stream_and_access` | db |
| AC12 | `services/pillar/tests/test_openapi.py::test_router_snapshots` (M0) | api |
| AC13 | see SC04 | unit |

All tests are offline: `httpx.MockTransport` serves the recorded Grants.gov JSON, the gateway is
`testing.offline_gateway()` (MockProvider + `rule_responder`), and blobs go to `tmp_path`.
Manual check (noted in the PR): `uv run hope-ingest grants-gov "youth mentoring" --rows 5` against the live API.

## Out of scope

Scheduled polling, saved searches, the parse-review queue, OCR, SAM.gov checks, other sources
(Candid, state portals), amendment diffs, full-text ranking, virus scanning beyond today's
`ArtifactStore` checks, pre-signed URLs.

## Requests to M0

1. **Nav:** add an "Opportunities" entry for `/opportunities` in `apps/web/src/nav.ts` (all roles), so the list
   page is reachable. Without it, the list is only reachable from links.
2. **Placeholder:** create `apps/web/src/app/opportunities/page.tsx` as a `ComingSoon` placeholder too, so M1 replaces
   it rather than adding a route M0 doesn't know about.
3. **`HOPE_AGENCY_ID` in settings:** expose it on `HopeSettings` (M0 step 3 names the env var) so the pillar router can
   join `tenant_opportunity` without reading the environment itself.
4. **Demo runner:** `make demo` should not require MinIO. M1 defaults to `HOPE_BLOB_STORE=local`; please leave MinIO out
   of the `make demo` service list, or make it optional.
5. **Pursue client:** SC04 calls `pursue(opportunityId)` from M4's `api/workflow` client. Please make sure the M0
   placeholder client already exports that method signature (returning `{workflow_id}`), so M1 can compile against it
   before M4 lands.

## Decisions needed (each with a recommended default)

1. **Streaming vs. pre-signed download.** Recommended: stream through the API (works without MinIO, one request, simple
   `<a href>`). Pre-signed URLs come back with S03 after the hackathon.
2. **Seed documents.** Recommended: commit at most one real NOFO PDF (under 3 MB) plus the recorded detail JSON for all 6;
   the others show their Grants.gov synopsis only. The live pull downloads every document.
3. **Event delivery.** Recommended: write events to the outbox only. M2 (matrix) should read new opportunities from the
   `opportunities` table during the demo rather than depend on Kafka, which keeps `make demo` free of Redpanda.
4. **Opportunity freshness at demo time.** Recommended: re-record the seed (one command) the day before the demo, and
   don't shift dates in real data.
5. **Search across closed opportunities.** Recommended: hidden by default, with an "Include closed" toggle on the list page.

## References

- `services/ingestion/src/hope_ingestion/{pipeline.py,connectors/grants_gov.py,artifacts.py,repository.py,testing.py}`
- `services/ingestion/tests/fixtures/grants_gov/`, `services/ingestion/scripts/grants_gov_smoke.py`
- WIP full version: `docs/specs/features/S03-opportunity-search-and-detail.md` on `specs/pillar`
- Grants.gov API: https://www.grants.gov/api/common/search2, https://www.grants.gov/api/common/fetchopportunity
