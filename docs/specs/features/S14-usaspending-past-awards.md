# S14: USAspending past-awards signal

| | |
|---|---|
| Wave | 2 |
| Depends on | S05, S10 (and S08, see Decisions / Catalog changes) |
| Screens | - (the signal appears in SC03 through existing matrix fields) |
| Migrations | `db/migrations/0220_past_awards.sql` (ingestion), `db/migrations/0430_past_award_stats.sql` (matching) |
| Blueprint | 2.2 A5/A6 inputs ("grantor history ... USAspending"), 5.3, 6.1 (USAspending row) |
| Status | Draft |

## Goal

For federal opportunities, use public USAspending.gov award history under the
opportunity's Assistance Listing Number (ALN) to ground two matrix dimensions in real data:

- **win probability**: how open the program is to new recipients
- **funder relationship**: whether this agency has already won under that ALN

Today both are fixed priors. With this change, a director can see "48 awards a year, 22 %
to first-time recipients, you won in FY2024" instead of an unexplained number.

## Current state

- `hope_matching.recommender`:
  - `win_probability(profile, opportunity, alignment)` is `BASE_WIN_RATE[funder.type] * (0.5 + A/100)`, times 1.5 if the profile's `grant_history` has an `awarded` item for the same funder, clamped to [0.01, 0.9].
  - `funder_relationship(profile, opportunity)` is the best `RELATIONSHIP_SCORE` over `grant_history` items whose `funder_id` matches `funder.funder_id` or `funder.name`.
  - `MODEL_VERSION = "a6-heuristic-v1"`.
- `GrantOpportunity.funder.aln: list[str]` (for example `"93.243"`) is filled by the Grants.gov connector. `AgencyProfile.legal.uei` holds the agency UEI.
- `hope_ingestion.http.PoliteClient`, `RateLimitPolicy` and `RetryPolicy` are the polite HTTP stack. The connectors live in `hope_ingestion/connectors/` (`grants_gov.py`, `sam_gov.py`).
- `connector_cursors (source_system, search_key, cursor)` holds incremental state. Ingestion tables are public, written only by `hope_system` (`0200_ingestion.sql`).
- No USAspending client or past-award data exists.

## Behaviour

### Ingestion: `connectors/usaspending.py`

1. **Client.** `UsaSpendingClient(settings: IngestionSettings, http: PoliteClient | None = None)`:
   - Base URL `HOPE_USASPENDING_BASE_URL` (default `https://api.usaspending.gov`).
   - Rate limit `HOPE_USASPENDING_RATE_PER_SEC` (default 1.0, burst 1). Retries use the default `RetryPolicy`.
   - No API key is needed.
   - These two settings are added in this spec's own `UsaSpendingSettings(BaseSettings)` in the same module, not in `IngestionSettings`. That keeps `settings.py` out of this spec's Owns.
2. **Search.** `search_awards(aln: str, start: date, end: date, page: int) -> AwardPage` sends `POST /api/v2/search/spending_by_award/` with:

   ```json
   {
     "filters": {
       "award_type_codes": ["02", "03", "04", "05"],
       "program_numbers": ["93.243"],
       "time_period": [{"start_date": "2021-10-01", "end_date": "2026-09-30"}]
     },
     "fields": ["Award ID", "Recipient Name", "Recipient UEI", "Award Amount", "Start Date",
                "End Date", "Awarding Agency", "Awarding Sub Agency", "generated_internal_id"],
     "page": 1, "limit": 100, "sort": "Award Amount", "order": "desc", "subawards": false
   }
   ```

   The response is read from `results[]` and `page_metadata.hasNext`. Codes 02-05 are block, formula and project grants and cooperative agreements, which are the award types nonprofits apply for.
3. **Parsing** (`past_award_from_api(row, aln) -> PastAward`) is pure code, never a model:
   - `award_key = generated_internal_id`, which is required; a row without it is skipped and counted as `skipped_no_key`.
   - `amount` = `Money.from_decimal(Decimal(str(row["Award Amount"])))` in USD. A negative amount (a de-obligation) keeps its sign, and is excluded from the stats in step 8.
   - `fiscal_year` is derived from `Start Date` using the federal FY (Oct-Sep).
   - `recipient_uei` is upper-cased and stripped. Empty means NULL.
4. **Sync.** `sync_past_awards(client, store, alns: list[str], today: date, years: int = 5) -> SyncReport`:
   - The window is the last `years` complete federal fiscal years plus the current FY to date.
   - For each ALN it pages until `hasNext` is false or `HOPE_USASPENDING_MAX_PAGES` (default 50) is reached. Hitting that limit is logged, `truncated` is set, and `last_status = 'truncated'`.
   - Rows are upserted by `award_key`, updating only when `raw_hash` changes.
   - `past_award_sync_state(aln)` gets `synced_at` and `last_status` (`ok`, `truncated`, or `error:<class>`).
   - An error on one ALN doesn't stop the others.
   - Idempotent: running twice in a row inserts nothing new.
5. **Which ALNs.** `alns_to_sync(store, today)` returns the distinct `funder.aln[]` values from the current version of every opportunity whose `application_due` is in the future or NULL, plus any ALN whose sync is older than 7 days.
   - The query reads `opportunities` / `opportunity_versions.normalized->'funder'->'aln'`.
   - ALNs are validated against `^\d{2}\.\d{3}[A-Z]?$`; anything else is skipped.
6. **Running it.** `python -m hope_ingestion.connectors.usaspending --once` syncs all ALNs and exits 0, or 1 if every ALN failed. The blueprint cadence is weekly; scheduling it is the job of S10's scheduler (see Decisions).
7. **Health.** `health()` sends `GET /api/v2/references/toptier_agencies/` with a 10 s timeout and returns `ConnectorHealth(source_system="usaspending", ok=...)`.

### Matching: `features/past_awards.py` and `recommender.py`

8. **Stats** (`0430` view `aln_award_stats`, one row per ALN over the last 5 complete FYs):
   - `awards`: count of rows with amount > 0.
   - `awards_per_year`: `awards / fiscal_years_covered`.
   - `recipients`: distinct non-null `recipient_uei`.
   - `median_award_minor`.
   - `new_recipient_share`: among recipients awarded in the latest complete FY, the share with no award under that ALN in the previous 4 FYs.
   - `latest_fy` and `synced_at`.
9. **Signal.** `load_signals(conn, opportunities, agency_uei, today) -> dict[UUID, PastAwardSignal]` does one query for every federal opportunity with at least one ALN. If an opportunity has several ALNs, the ALN with the most awards is used. The returned `PastAwardSignal` holds:
   - `aln`
   - `awards_per_year`, `recipients`, `new_recipient_share`, `median_award` (`Money`), `latest_fy`
   - `agency_awards`: rows where `recipient_uei = agency_uei` in the window
   - `agency_last_fy`
   - `stale`: `synced_at` older than 30 days
10. **Win probability** (a pure function, `adjust_win_probability(base: float, signal) -> float`). The signal is used only when `signal.awards >= HOPE_MATCHING_MIN_AWARDS_FOR_SIGNAL` (default 10) and `not signal.stale`:

    ```text
    openness  = 0.5 + new_recipient_share          # 0.5 .. 1.5
    incumbent = 1.5 if agency_awards > 0 else 1.0
    p_win     = clamp(BASE_WIN_RATE["federal"] * (0.5 + A/100) * openness * incumbent, 0.01, 0.9)
    ```

    This replaces the `grant_history` 1.5× boost for federal rows, so the boost is never applied twice. Non-federal rows, and rows without a usable signal, keep today's formula exactly.
11. **Funder relationship.** For federal rows with a signal, the value is `max(today's value, 100 if agency_awards > 0 and agency_last_fy >= latest_fy - 4 else today's value)`.
12. **Explanation and risks** use only the signal's numbers:
    - `explain()` appends: `"USAspending ALN 93.243: 48 awards/yr, 22% to new recipients; your agency: 2 awards (last FY2024)"`.
    - `risks()` adds `"ALN 93.243 mostly re-awards incumbents (12% new recipients)"` when `new_recipient_share < 0.15` and `agency_awards == 0`.
    - `risks()` adds `"USAspending data for ALN 93.243 is stale (synced 2026-09-01)"` when `stale`.
13. **Wiring.**
    - `compute_features(..., signal: PastAwardSignal | None = None)` and `build_matrix(..., signals: Mapping[UUID, PastAwardSignal] | None = None)`. With `None`, the output is byte-identical to today, so the existing golden test is unchanged.
    - The S08 worker calls `load_signals` before each re-score.
    - When any signal is used, `OpportunityMatrix.weights_profile` becomes `"heuristic-v1+usaspending"` and `MODEL_VERSION` becomes `"a6-heuristic-v2"`.
14. **Privacy.** Only public USAspending data is stored. Agency UEI matching happens at read time and is never written to the public tables.

## Contracts

- **Shared models used:** `Money`, `GrantOpportunity.funder.aln`, `AgencyProfile.legal.uei`, `OpportunityMatrix` / `MatrixRow` / `DimensionScores`, `content_hash`.
- **Shared contract additions** (C2):
  - `hope_core.schemas.past_awards.PastAward` with fields `award_key: str`, `aln: str`, `recipient_name: str`, `recipient_uei: str | None`, `awarding_agency: str | None`, `awarding_sub_agency: str | None`, `amount: Money`, `start_date: date | None`, `end_date: date | None`, `fiscal_year: int`, `source_url: str` (`https://www.usaspending.gov/award/{award_key}`).
  - `"usaspending"` added to `hope_core.schemas.grant_opportunity.SourceSystem`, so `ConnectorHealth` and `connector_cursors` can name it.
- **Events:** none. This is a batch sync into public tables, and matching reads it at re-score time. A daily re-score (S08) picks up new data.
- **Endpoints:** none.
- **Database:**

  `0220_past_awards.sql` (public, cross-tenant, no RLS, written by `hope_system` only, like `0200`):

  ```sql
  CREATE TABLE past_awards (
    award_key            text PRIMARY KEY,
    aln                  text NOT NULL,
    recipient_name       text NOT NULL,
    recipient_uei        text,
    awarding_agency      text,
    awarding_sub_agency  text,
    amount_minor         bigint NOT NULL,
    currency             char(3) NOT NULL DEFAULT 'USD',
    start_date           date,
    end_date             date,
    fiscal_year          int  NOT NULL,
    raw_hash             text NOT NULL,
    fetched_at           timestamptz NOT NULL DEFAULT now()
  );
  CREATE INDEX past_awards_aln_fy ON past_awards (aln, fiscal_year);
  CREATE INDEX past_awards_uei ON past_awards (recipient_uei) WHERE recipient_uei IS NOT NULL;
  CREATE TABLE past_award_sync_state (
    aln          text PRIMARY KEY,
    synced_at    timestamptz NOT NULL,
    last_status  text NOT NULL,
    rows_seen    int  NOT NULL DEFAULT 0
  );
  GRANT SELECT ON past_awards, past_award_sync_state TO hope_app;
  GRANT SELECT, INSERT, UPDATE ON past_awards, past_award_sync_state TO hope_system;
  ```

  `0430_past_award_stats.sql` (matching): `CREATE VIEW aln_award_stats AS ...` computing the step 8 columns from `past_awards` joined with `past_award_sync_state`, with `GRANT SELECT ... TO hope_app, hope_system`. It's a plain view, not a materialized one; at MVP volume (a few hundred ALNs, at most about 50k rows) it's fast enough and needs no refresh job.

## Owns

```text
services/ingestion/src/hope_ingestion/connectors/usaspending.py
services/ingestion/tests/test_usaspending.py
services/ingestion/tests/fixtures/usaspending/**
services/matching/src/hope_matching/features/__init__.py
services/matching/src/hope_matching/features/past_awards.py
services/matching/src/hope_matching/recommender.py
services/matching/src/hope_matching/worker.py (one call to load_signals; file created by S08)
services/matching/tests/test_past_awards.py
services/matching/tests/test_past_awards_db.py
db/migrations/0220_past_awards.sql
db/migrations/0430_past_award_stats.sql
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 `search_awards` sends the exact request body above (ALN filter, grant award types, window) and follows `hasNext` paging up to the page limit.
- [ ] AC2 `past_award_from_api` turns amounts into `Money` with `Decimal` (no float drift), derives the federal fiscal year (an award starting 2025-10-01 is FY2026), normalises the UEI, and skips rows without `generated_internal_id`.
- [ ] AC3 `sync_past_awards` is idempotent: a second run with the same fixtures inserts and updates 0 rows. A 5xx on one ALN is recorded as `error:` and the other ALNs still sync.
- [ ] AC4 `alns_to_sync` returns only valid ALNs from open opportunities, plus ALNs whose sync is stale.
- [ ] AC5 `aln_award_stats` computes `awards_per_year`, `recipients`, `median_award_minor` and `new_recipient_share` correctly for a seeded fixture, ignoring negative amounts.
- [ ] AC6 `adjust_win_probability` follows the formula, stays within [0.01, 0.9] for all inputs, and is never applied together with the `grant_history` boost.
- [ ] AC7 Below `min_awards`, or with stale data, the matrix row is identical to the row without a signal.
- [ ] AC8 Agency incumbency (a UEI match within 5 FYs) sets `funder_relationship` to 100 and is reflected in the explanation text.
- [ ] AC9 Explanation and risk strings are built only from signal numbers, and the existing golden matrix is unchanged when `signals=None`.
- [ ] AC10 Public tables can't be written by `hope_app`.
- [ ] AC11 All CI commands pass offline. HTTP uses recorded fixtures.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/ingestion/tests/test_usaspending.py::test_request_body_and_paging` (`httpx.MockTransport`) | unit |
| AC2 | `test_usaspending.py::test_parse_money_fy_and_uei` | unit |
| AC3 | `test_usaspending.py::test_sync_idempotent_and_partial_failure` (db) | db |
| AC4 | `test_usaspending.py::test_alns_to_sync` (db) | db |
| AC5 | `services/matching/tests/test_past_awards_db.py::test_aln_award_stats_view` | db |
| AC6 | `services/matching/tests/test_past_awards.py::test_win_probability_formula`, `::test_win_probability_bounds` (Hypothesis) | unit/property |
| AC7 | `test_past_awards.py::test_no_signal_below_threshold_or_stale` | unit |
| AC8 | `test_past_awards.py::test_incumbent_relationship_and_explanation` | unit |
| AC9 | `test_past_awards.py::test_explanations_from_numbers_only`, existing `test_golden.py::test_golden_matrix` | unit |
| AC10 | `test_usaspending.py::test_app_role_cannot_write` (db) | db |
| AC11 | CI | ci |

Fixtures: `fixtures/usaspending/spending_by_award_93.243_p1.json` and `_p2.json` (recorded,
then trimmed to 5 rows each, with one row missing `generated_internal_id` and one negative
amount), plus `spending_by_award_empty.json` and `toptier_agencies.json`.

## Out of scope

- 990-PF / private-foundation history (S15).
- A funder knowledge graph.
- Sub-awards.
- A learned win-probability model (LambdaMART, after S23 collects outcomes).
- Showing raw award lists in the UI (SC04 could add a "Past awards" tab later).

## Decisions needed

1. **Ordering with S08.** S14 changes `recommender.py` and adds one call in S08's `worker.py`. Recommended default: S14 depends on S08 (sequential within wave 2), or moves to wave 3. See Catalog changes.
2. **Scheduling.** Recommended default: S10's scheduler gets a `usaspending` source with a weekly cadence (Mon 06:00 UTC) that runs `sync_past_awards`. Until then, run the module command from cron in S28.
3. **API field names.** The `fields` list and the `program_numbers` filter match the public v2 docs as I understand them. Verify them against https://api.usaspending.gov/docs/endpoints when recording fixtures; if a field name differs, only `past_award_from_api` changes.
4. **Signal threshold.** Recommended default: at least 10 awards in 5 FYs, otherwise no signal. Revisit when there's outcome data (S23).
5. **Agency UEI source.** Recommended default: `AgencyProfile.legal.uei` only. Earlier UEIs or DUNS numbers aren't matched.

## References

- `services/matching/src/hope_matching/recommender.py` (`win_probability`, `funder_relationship`, `explain`, `risks`, `build_matrix`), `services/ingestion/src/hope_ingestion/http.py`, `services/ingestion/src/hope_ingestion/connectors/sam_gov.py`, `db/migrations/0200_ingestion.sql`.
- Blueprint 2.2 (A5/A6 inputs), 5.3, 6.1.
- USAspending API: https://api.usaspending.gov/docs/endpoints (`/api/v2/search/spending_by_award/`).
