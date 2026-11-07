# S05: Matrix explainability and disposition

> **Out of scope for the hackathon. Don't build this.** This spec belongs to the earlier design (the Phase 1 pipeline and the M0-M7 / S-spec roadmap). Hackathon agents build only H0-H5 (see [`README.md`](../README.md)). Keep this file for after the hackathon.

| | |
|---|---|
| Wave | 1 |
| Depends on | S00 |
| Screens | SC03 (`screens/SC03-opportunity-matrix.md`) |
| Migrations | `db/migrations/0410_matrix_explain.sql` |
| Blueprint | 2.2 A4/A5/A6, 5.3, 7.4 |
| Status | Draft |

## Goal

Turn the matrix from a ranked list into a decision tool. Every row carries its full scores,
eligibility and capacity. Each row can be explained term by term, with the profile and RFP
evidence behind each number. Users can mark rows **Watch** or **Skip**, and that choice
persists. SC03 (the reference screen spec) is built on exactly this API.

## Current state

- **Matching computes everything but the API can't see it.**
  - `hope_matching.agents.MatchingAgent` builds an `OpportunityMatrix` and publishes it as `recommendation.updated`. Profiles, opportunities and A4/A5 results are kept only in memory (`self.profiles`, `self.opportunities`, `self._cache`).
  - `hope_matching.repository.save_matrix` / `latest_matrix` write and read `opportunity_matrices` (`0400_matching.sql`, append-only), but nothing calls them. `EligibilityResult` / `AlignmentAssessment` (S00 moves them to `hope_core.schemas.matching`) are never stored.
  - `MatrixRow.top_matched_programs` holds program **ids** (`AlignmentAssessment.matched_programs`).
- **The pillar returns a summary only.**
  - `GET /v1/agencies/{agency_id}/matrix` (S00 moves it to `services/pillar/src/hope_pillar/api/matrix.py`) reads `tenant_opportunity JOIN opportunities` and returns `MatrixPage{items: MatrixItem[], next_cursor}`.
  - Each `MatrixItem` has `opportunity_id, title, state, composite_score, recommendation, internal_deadline, application_due, workflow_id`. Paging is keyset (`cursor`, `limit`), and the filters are `state`, `min_score`, `due_before`.
  - `tenant_opportunity` only has rows for opportunities the workflow projection knows about, so freshly scored opportunities don't show up at all.
- **The web maps around the gap.**
  - `apps/web/src/api/http.ts` (S00 splits it into `api/matrix/http.ts`) maps `items` to fake `MatrixRow`s through `summaryRow()` (all scores 0, `eligibility: "needs_review"`, `detail: "summary"`).
  - `features/matrix/MatrixScreen.tsx` filters client-side. `OpportunityDrawer.tsx` shows only clause and deadline evidence from the opportunity.
- **There are no disposition, explanation or "hidden ineligible" concepts yet.**
- S00 adds `MATRIX_DISPOSITION_SET = "recommendation.disposition_set"`, `hope_core.outbox.write_event`, `hope_core.errors` (`Problem`, `NotFound`, `Forbidden`, `ConcurrencyError`), `hope_core.auth.require_roles`, and makes `MatrixRow.dimension_scores`, `eligibility` and `evidence_ids` always present. It also makes `MatchingConfig` a single global config.

## Behaviour

### Persisting what matching computes (`services/matching`)

1. **Store port.** Add a `MatchingStore` protocol in `repository.py` with these methods:
   - `save_run(tenant_id, assessments: list[StoredAssessment], matrix: OpportunityMatrix) -> str`, which returns the matrix hash.
   - `assessment(tenant_id, agency_id, opportunity_id) -> StoredAssessment | None`.

   There are two implementations: `PostgresMatchingStore(url)` and `InMemoryMatchingStore` (in `testing.py`). `StoredAssessment` (service-private) holds `profile_hash`, `opportunity_hash`, `EligibilityResult`, `AlignmentAssessment | None`, and `passages: dict[str, str]`. `passages` contains only the evidence IDs that were actually cited, mapped to the passage text the judge saw.
2. **The agent saves every re-score.** `MatchingAgent(..., store: MatchingStore | None = None)`. After `_rescore`, the agent calls `store.save_run(...)` once, in one `tenant_tx`:
   - It inserts new assessments with `ON CONFLICT DO NOTHING` on `(tenant_id, agency_id, opportunity_id, profile_hash, opportunity_hash)`.
   - It appends the matrix to `opportunity_matrices` (existing `save_matrix`).

   It does this before publishing events. If the store raises, no event is published and the handler raises, so the consumer redelivers. Event delivery through the outbox and durable consumption are S08. With `store=None`, behaviour is the same as today.
3. **Rows always carry full detail.** `build_matrix` fills the fields S00 makes always present:
   - `eligibility`: the A4 status.
   - `dimension_scores`: the A5 `DimensionScore[]`, or `[]` when the row is ineligible and A5 wasn't run.
   - `evidence_ids`: the union of A5-cited IDs and `"rfp:{artifact_id}:{page}:{char_start}"` keys for A4 evidence.

   `top_matched_programs` changes from ids to **program names**, looked up in `profile.programs` in the order they were cited. Unknown ids are dropped.
4. **Score terms (pure).** Add `score_terms(scores, eligibility, weights) -> list[ScoreTerm]` to `recommender.py`. A `ScoreTerm` is `(key, value, scale, weight, contribution)`:
   - `scale` is 1 for `win_probability` and 100 for everything else.
   - `contribution = round(gate * weight * value * (100 if key == "win_probability" else 1), 2)`.

   The contributions sum to `composite_score` within 0.01 (property-tested).
5. **Rule labels (pure).** Add `rule_label(rule_id, clause_text=None) -> str` to `eligibility.py`. The labels are:

   | Rule id | Label |
   |---|---|
   | `applicant_type` | Applicant type |
   | `geography` | Geography |
   | `budget_band` | Budget band |
   | `registration.sam` | SAM.gov registration |
   | `registration.uei` | UEI |
   | `registration.<x>` | Registration: `<x>` |
   | `cost_share` | Cost share |
   | `clause.<i>` | The clause text, cut to 120 characters with "…" |

   Add `rule_summary(outcome, facts) -> str`, a one-line deterministic sentence such as "Your tax status 501(c)(3) is accepted" or "SAM.gov registration expires before the deadline". `RuleOutcome.detail` stays as-is for audit.

### Reading the matrix (`services/pillar/.../api/matrix.py`)

6. **`GET /v1/agencies/{agency_id}/matrix`** reads the latest `opportunity_matrices` row for the agency. Rows come from `matrix->'rows'`, joined with:
   - `opportunities` and `opportunity_versions` (current version) for title, funder, award and due date
   - `matrix_dispositions`
   - `tenant_opportunity` for `workflow_id` and `lifecycle_state`, as a LEFT JOIN

   Then:
   - Rows whose `application_due` is in the past (at request time) are dropped. They're never shown, as SC03 requires.
   - Filters apply in this order: `eligibility`, then `show_skipped`, then `recommendation`, `due_within_days` and `q`. Then sort and paging.
   - `rank` is always the snapshot's rank. Re-sorting never renumbers rows.
   - `agency_id` other than the principal's agency gives 404 `not_found`.
7. **Counts.** The response also includes:
   - `total`: rows after every filter.
   - `hidden_ineligible`: rows removed only by the eligibility filter.
   - `hidden_skipped`: rows removed only because they're skipped.
   - `summary`: computed over rows that pass the eligibility and skip filters only, independent of the other filters, so the summary strip is stable while the user filters:
     - `open`: number of rows
     - `pursue`: rows with recommendation `pursue`
     - `due_within_14_days`: rows with `days_to_internal_deadline <= 14` or `application_due` within 14 days
8. **Empty states.** If there's no matrix yet, the response is 200 with `generated_at: null`, `rows: []` and an `empty_reason`:
   - `profile_incomplete`: no `agency_profile_versions` row for the agency.
   - `not_scored_yet`: a profile exists but no matrix does.

   If a matrix exists with zero open rows, `empty_reason` is `no_opportunities`. Otherwise it's `null`.
9. **Explanation endpoint.** `GET .../matrix/{opportunity_id}/explanation` loads the row from the latest matrix and the stored assessment that matches the row. It returns:
   - every `ScoreTerm` with its evidence
   - the eligibility rules with labels, summaries and RFP evidence
   - the A5 rubric dimensions (median, samples, low confidence, advisory rationale) and cited passages
   - effort drivers, estimates, capacity, risks and explanation
   - matched programs as `{program_id, name}`

   Evidence mapping:
   - **Profile passages** (`evidence_id` without the `rfp:` prefix) become `{kind: "profile", source_label, quote}`. `source_label` is `"Profile: Mission"`, `"Profile: Theory of change"`, `"Profile: Focus areas"`, `"Profile: Programs · {name}"`, `"Profile: Outcomes · {program}"`, `"Profile: Grant history"` or `"Profile: Capacity"`, based on the id prefixes in `alignment.profile_passages`. `quote` is the passage text, truncated to 300 characters.
   - **RFP evidence** becomes `{kind: "rfp", source_label: "RFP p. {page}", quote, artifact_id, page, char_start, char_end}`.
   - Funding fit evidence comes from `opportunity.funding.evidence`. Deadline evidence comes from `deadlines.application_due.evidence`.

   If the opportunity isn't in the latest matrix, or is past its deadline, the response is 404 `not_found`.

### Disposition

10. **Setting it.** `PUT .../matrix/{opportunity_id}/disposition` takes `{"disposition": "watch" | "skip" | "none", "reason": <optional>}`. `reason` is one of `not_mission_fit`, `too_much_effort`, `deadline_too_soon` or `other`, and is only allowed with `skip`. `reason_text` (at most 500 characters) is only allowed with `reason = other`. Any signed-in user may set it (SC03). The endpoint:
    - upserts `matrix_dispositions`
    - appends to `matrix_disposition_history`
    - writes `recommendation.disposition_set` with `write_event`, in one transaction

    `"none"` deletes the current row (and is recorded in history), which is how Undo works. The same disposition sent twice is a no-op: 200, no new history row and no event.
11. **Effect.** A disposition never changes the score, rank or recommendation, because code decides those. Skipped rows are hidden unless `show_skipped=true`. Rows show `disposition` and `disposition_changed: true` when the opportunity's content hash has changed since the disposition was set (for example after an amendment).
12. **Pursue** (`POST /v1/opportunities/{id}/pursue`) is owned by S04. S05 gives S04 the two facts SC03 relies on, through a read-only SQL view `matrix_latest_rows (tenant_id, agency_id, opportunity_id, eligibility, recommendation, composite_score, generated_at)` in `0410`:
    - S04 returns 422 `ineligible` when the latest row's eligibility is `ineligible`.
    - S04 returns 409 `already_pursuing` (with `workflow_id`) when `tenant_opportunity.workflow_id` is set.

    S04 and S31 read the view instead of the matching tables.

## Contracts

- **Shared models used:** `OpportunityMatrix`, `MatrixRow`, `DimensionScores`, `Estimates`; `EligibilityResult`, `RuleOutcome`, `EffortEstimate`, `DimensionScore`, `AlignmentAssessment` (after S00's move); `Evidence`, `Money`, `GrantOpportunity`, `AgencyProfile`; `PillarEnvelope`, `EventType.MATRIX_DISPOSITION_SET`; `hope_core.outbox.write_event`, `hope_core.errors`, `hope_core.auth.get_principal`.
- **Shared contract additions** (S00, so `@hope/schemas` generates TS for the web). Add these to `hope_core/schemas/matching.py`:
  - `MatrixDisposition`: `disposition: Literal["watch","skip"]`, `reason: Literal["not_mission_fit","too_much_effort","deadline_too_soon","other"] | None`, `reason_text: str | None` (max length 500), `set_by: str`, `set_at: datetime`, `changed_since: bool = False` (serialized as `disposition_changed` on the row).
  - `MatrixListRow(MatrixRow)`: `disposition: MatrixDisposition | None`, `workflow_id: str | None`, `lifecycle_state: OpportunityState | None`.
  - `MatrixSummary`: `open: int`, `pursue: int`, `due_within_14_days: int`.
  - `MatrixPage`: `agency_id: UUID`, `generated_at: datetime | None`, `model_version: str | None`, `weights_profile: str | None`, `matrix_hash: str | None`, `empty_reason: Literal["profile_incomplete","not_scored_yet","no_opportunities"] | None`, `rescoring: bool = False`, `total: int`, `hidden_ineligible: int`, `hidden_skipped: int`, `summary: MatrixSummary`, `page: int`, `page_size: int`, `page_count: int`, `rows: list[MatrixListRow]`.
  - `ExplanationEvidence`: `evidence_id: str`, `kind: Literal["profile","rfp"]`, `source_label: str`, `quote: str | None`, `artifact_id: str | None`, `page: int | None`, `char_start: int | None`, `char_end: int | None`.
  - `ScoreTermView`: `key: Literal[<the 7 DimensionScores keys>]`, `label: str`, `value: float`, `scale: Literal[1, 100]`, `weight: float`, `contribution: float`, `low_confidence: bool = False`, `evidence: list[ExplanationEvidence] = []`, `rubric: list[DimensionScore] = []` (only for `mission_alignment`), `inputs: dict[str, float | int | None] = {}` (for example `{"expected_hours": 60, "efr": 0.0012}`).
  - `EligibilityRuleView`: `rule_id: str`, `label: str`, `outcome: Literal["pass","fail","review"]`, `summary: str`, `evidence: list[ExplanationEvidence]`.
  - `EligibilityExplanation`: `status`, `passed: int`, `failed: int`, `open: int`, `rules: list[EligibilityRuleView]` (ordered fail, review, pass; then by label).
  - `MatchedProgram`: `program_id: str`, `name: str`.
  - `MatrixExplanation`: `opportunity_id`, `agency_id`, `generated_at`, `matrix_hash`, `rank`, `composite_score`, `recommendation`, `gate: Literal[0, 1]`, `weights_profile`, `dimensions: list[ScoreTermView]` (the 7 keys, in `DimensionScores` field order), `eligibility: EligibilityExplanation`, `effort: EffortEstimate | None`, `estimates: Estimates`, `capacity_fit`, `risks: list[str]`, `explanation: str | None`, `matched_programs: list[MatchedProgram]`, `gaps: list[str]`, `alignment_low_confidence: bool`.
  - `DispositionBody`: `disposition: Literal["watch","skip","none"]`, `reason`, `reason_text`.
  - `MatrixDispositionSet` (payload of `recommendation.disposition_set`): `agency_id`, `opportunity_id`, `disposition: Literal["watch","skip","none"]`, `reason`, `set_by`, `set_at`, `opportunity_hash`.

- **Events.**
  - `recommendation.disposition_set`, on topic `gop.opportunity.events`, schema `matrix-disposition-set/1.0.0`. Producer: pillar (`service="pillar"`, `agent_id=None`), `data_classification="confidential"`, `subject_id = opportunity_id`. Consumers: S12 (watch notifications, later) and S23 (skip reasons as training labels).
  - The matching agent keeps emitting `opportunity.eligibility_evaluated`, `opportunity.alignment_scored` and `recommendation.updated`, unchanged.

- **Endpoints.** All endpoints need a signed-in principal (S00 `get_principal`), and the tenant is always `HOPE_TENANT_ID`. Errors are `application/problem+json`.

  **`GET /v1/agencies/{agency_id}/matrix`**

  | Query | Type | Default | Rule |
  |---|---|---|---|
  | `recommendation` | comma list of `pursue,consider,watch,skip` | all | Unknown value gives 422 `invalid_query` |
  | `eligibility` | comma list of `eligible,needs_review,ineligible` | `eligible,needs_review` | SC03 "Eligible + Review" |
  | `due_within_days` | int 1-365 | none | Uses `application_due` (UTC) minus now. Rolling rows are excluded when it's set |
  | `q` | string, 1-100 chars | none | Case-insensitive substring on title, funder name and `source.source_id` |
  | `sort` | `rank`, `due`, `award` | `rank` | `due` is soonest first with rolling last. `award` is highest `award_ceiling` first, with unknowns last. Ties fall back to rank |
  | `show_skipped` | bool | `false` | SC03 sets it when its "Skip" filter is on |
  | `page` | int ≥ 1 | 1 | A page past the end returns `rows: []` with the correct `total` |
  | `page_size` | int 1-100 | 25 | `limit` is accepted as an alias (S31 uses `?limit=5`) |

  The old `cursor`, `state`, `min_score` and `due_before` parameters are removed; this is a breaking change in a router S05 owns. Response 200 (abridged):

  ```json
  {
    "agency_id": "0b7c…", "generated_at": "2026-11-07T14:48:00Z", "model_version": "a6-heuristic-v1",
    "weights_profile": "heuristic-v1", "matrix_hash": "sha256:9f2…", "empty_reason": null, "rescoring": false,
    "total": 42, "hidden_ineligible": 6, "hidden_skipped": 2,
    "summary": {"open": 42, "pursue": 9, "due_within_14_days": 3},
    "page": 1, "page_size": 25, "page_count": 2,
    "rows": [{
      "opportunity_id": "5d1e…", "rank": 1, "composite_score": 87.2, "eligibility": "eligible",
      "scores": {"mission_alignment": 91, "funding_fit": 80, "effort_to_funding": 78, "win_probability": 0.34,
                 "deadline_feasibility": 70, "funder_relationship": 0, "strategic_priority_boost": 100},
      "dimension_scores": [{"dimension": "population", "score": 92, "samples": [90, 92, 95], "rejected_samples": 0,
                            "evidence_ids": ["program:mentor-futures"], "rationale": "…", "low_confidence": false}],
      "evidence_ids": ["program:mentor-futures", "rfp:art_7f3:4:120"],
      "estimates": {"expected_hours": 60, "expected_value": {"amount_minor": 8500000, "currency": "USD"}, "days_to_internal_deadline": 7},
      "capacity_fit": "fits", "recommendation": "pursue",
      "explanation": "pursue (composite 87.2, eligibility eligible, capacity fits); mission alignment 91; …",
      "top_matched_programs": ["Mentor Futures"], "risks": ["requires 20% cost share"],
      "disposition": null, "disposition_changed": false, "workflow_id": null, "lifecycle_state": null
    }]
  }
  ```

  Errors: 404 `not_found` (unknown agency) and 422 `invalid_query` (any bad parameter, with `detail` naming it).

  **`GET /v1/agencies/{agency_id}/matrix/{opportunity_id}/explanation`** returns 200 `MatrixExplanation`:

  ```json
  {
    "opportunity_id": "5d1e…", "agency_id": "0b7c…", "generated_at": "2026-11-07T14:48:00Z", "matrix_hash": "sha256:9f2…",
    "rank": 1, "composite_score": 87.2, "recommendation": "pursue", "gate": 1, "weights_profile": "heuristic-v1",
    "dimensions": [
      {"key": "mission_alignment", "label": "Mission alignment", "value": 91, "scale": 100, "weight": 0.35, "contribution": 31.85,
       "low_confidence": false,
       "rubric": [{"dimension": "theory_of_change", "score": 90, "samples": [88, 90, 95], "rejected_samples": 0,
                   "evidence_ids": ["theory_of_change"], "rationale": "…", "low_confidence": false}],
       "evidence": [{"evidence_id": "program:mentor-futures", "kind": "profile", "source_label": "Profile: Programs · Mentor Futures",
                     "quote": "Mentor Futures. Weekly mentoring for youth 12-18…", "artifact_id": null, "page": null, "char_start": null, "char_end": null}]},
      {"key": "funding_fit", "label": "Funding fit", "value": 80, "scale": 100, "weight": 0.15, "contribution": 12.0,
       "evidence": [{"evidence_id": "rfp:art_7f3:4:120", "kind": "rfp", "source_label": "RFP p. 4", "quote": "Awards up to $250,000…",
                     "artifact_id": "art_7f3", "page": 4, "char_start": 120, "char_end": 168}]},
      {"key": "effort_to_funding", "label": "Effort to funding", "value": 78, "scale": 100, "weight": 0.15, "contribution": 11.7,
       "inputs": {"expected_hours": 60, "efr": 0.0012}},
      {"key": "win_probability", "label": "Win probability", "value": 0.34, "scale": 1, "weight": 0.15, "contribution": 5.1},
      {"key": "deadline_feasibility", "label": "Deadline feasibility", "value": 70, "scale": 100, "weight": 0.10, "contribution": 7.0},
      {"key": "funder_relationship", "label": "Funder relationship", "value": 0, "scale": 100, "weight": 0.05, "contribution": 0},
      {"key": "strategic_priority_boost", "label": "Strategic priority", "value": 100, "scale": 100, "weight": 0.05, "contribution": 5.0}
    ],
    "eligibility": {"status": "eligible", "passed": 6, "failed": 0, "open": 0, "rules": [
      {"rule_id": "applicant_type", "label": "Applicant type", "outcome": "pass", "summary": "Your tax status 501(c)(3) is accepted", "evidence": []}]},
    "effort": {"expected_hours": 60, "drivers": {"base": 8, "per_section": 16, "per_page": 22.5, "federal": 12}, "model": "heuristic-v1"},
    "estimates": {"expected_hours": 60, "expected_value": {"amount_minor": 8500000, "currency": "USD"}, "days_to_internal_deadline": 7},
    "capacity_fit": "fits", "risks": ["requires 20% cost share"], "explanation": "…",
    "matched_programs": [{"program_id": "mentor-futures", "name": "Mentor Futures"}], "gaps": [], "alignment_low_confidence": false
  }
  ```

  Errors: 404 `not_found` (agency, or opportunity not in the latest matrix, or past due).

  **`PUT /v1/agencies/{agency_id}/matrix/{opportunity_id}/disposition`** takes a body such as
  `{"disposition": "skip", "reason": "too_much_effort", "reason_text": null}`. It returns 200 with
  `{"opportunity_id": "5d1e…", "disposition": {"disposition": "skip", "reason": "too_much_effort", "reason_text": null, "set_by": "dd-1", "set_at": "2026-11-07T15:02:11Z"}}`,
  where `disposition` is `null` after `"none"`. Errors:
  - 404 `not_found`
  - 422 `invalid_disposition`: a reason given with `watch`/`none`, `reason_text` without `other`, `reason_text` over 500 characters, or an unknown value
  - 403 `forbidden`: the principal has no user id (anonymous)

- **Database** (`0410_matrix_explain.sql`). Every table is tenant-scoped with RLS (`tenant_id = current_tenant()`), following `0400`.

  ```sql
  CREATE TABLE matching_assessments (
    tenant_id uuid NOT NULL REFERENCES tenants, agency_id uuid NOT NULL REFERENCES agencies,
    opportunity_id uuid NOT NULL REFERENCES opportunities,
    profile_hash text NOT NULL, opportunity_hash text NOT NULL,
    eligibility jsonb NOT NULL, alignment jsonb, passages jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agency_id, opportunity_id, profile_hash, opportunity_hash));
  CREATE TABLE matrix_dispositions (
    tenant_id uuid NOT NULL REFERENCES tenants, agency_id uuid NOT NULL REFERENCES agencies,
    opportunity_id uuid NOT NULL REFERENCES opportunities,
    disposition text NOT NULL CHECK (disposition IN ('watch','skip')),
    reason text CHECK (reason IN ('not_mission_fit','too_much_effort','deadline_too_soon','other')),
    reason_text text CHECK (char_length(reason_text) <= 500),
    opportunity_hash text NOT NULL, set_by text NOT NULL, set_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agency_id, opportunity_id),
    CHECK (reason IS NULL OR disposition = 'skip'), CHECK (reason_text IS NULL OR reason = 'other'));
  CREATE TABLE matrix_disposition_history (
    history_id bigserial PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants,
    agency_id uuid NOT NULL, opportunity_id uuid NOT NULL,
    disposition text NOT NULL CHECK (disposition IN ('watch','skip','none')),
    reason text, reason_text text, set_by text NOT NULL, set_at timestamptz NOT NULL DEFAULT now());
  -- append-only trigger on history (forbid_mutation); RLS on all three; grants to hope_app, hope_system
  CREATE VIEW matrix_latest_rows WITH (security_invoker = true) AS
    SELECT DISTINCT ON (m.tenant_id, m.agency_id, (r->>'opportunity_id')::uuid)
           m.tenant_id, m.agency_id, (r->>'opportunity_id')::uuid AS opportunity_id,
           r->>'eligibility' AS eligibility, r->>'recommendation' AS recommendation,
           (r->>'composite_score')::numeric AS composite_score, m.generated_at
    FROM opportunity_matrices m, jsonb_array_elements(m.matrix->'rows') r
    ORDER BY m.tenant_id, m.agency_id, (r->>'opportunity_id')::uuid, m.generated_at DESC, m.matrix_id DESC;
  ```

  `matrix_latest_rows` must only take rows from each agency's **latest** matrix. The implementation filters `m.matrix_id = (SELECT max(matrix_id) … per agency)`; the sketch above shows the columns. The view uses `security_invoker` so RLS applies.

## Owns

```text
services/matching/src/hope_matching/**        (wave 1: S05 is the only matching spec)
services/matching/tests/**
services/pillar/src/hope_pillar/api/matrix.py
services/pillar/tests/test_matrix_api.py
services/pillar/tests/snapshots/openapi/matrix.json
apps/web/src/features/matrix/**
apps/web/src/api/matrix/**
apps/web/src/app/matrix/page.tsx
db/migrations/0410_matrix_explain.sql
docs/specs/README.md (this spec's status row only)
```

The current matrix assertions in `services/pillar/tests/test_api.py::test_matrix_and_opportunity`
(S00 moves them) are rewritten in `test_matrix_api.py`.

## Acceptance criteria

- [ ] AC1 After a re-score with a `PostgresMatchingStore`, the assessments and the matrix are stored in one transaction. If the store fails, no event is published.
- [ ] AC2 Matrix rows carry `eligibility`, `dimension_scores` and `evidence_ids`, and `top_matched_programs` holds program names.
- [ ] AC3 `score_terms` contributions sum to `composite_score` within 0.01 for any scores, weights and gate (property test). With gate 0, every contribution is 0.
- [ ] AC4 `GET matrix` returns full rows from the latest snapshot, ordered by snapshot rank, and never returns rows past their deadline.
- [ ] AC5 The default filter hides ineligible rows. `hidden_ineligible` and `hidden_skipped` count exactly the rows removed by those filters alone, and `total` is the count after every filter.
- [ ] AC6 `recommendation`, `eligibility`, `due_within_days`, `q`, `sort` (`rank`, `due`, `award`), `page`, `page_size` and the `limit` alias behave as in the table above. A bad value returns 422 `invalid_query`.
- [ ] AC7 `summary` doesn't depend on the `recommendation`, `due_within_days` or `q` filters.
- [ ] AC8 `empty_reason` is `profile_incomplete`, `not_scored_yet` or `no_opportunities` in the three empty cases, with 200 and `rows: []`.
- [ ] AC9 The explanation returns all 7 terms in order with weights and contributions, profile and RFP evidence mapped to `source_label` and spans, eligibility rules ordered fail/review/pass with labels and summaries, and matched programs with names. An opportunity that isn't in the matrix returns 404.
- [ ] AC10 The disposition PUT upserts, appends history and writes `recommendation.disposition_set` to the outbox atomically. `"none"` clears it; a repeated identical PUT is a no-op. Invalid combinations return 422 `invalid_disposition`.
- [ ] AC11 Skipped rows are hidden unless `show_skipped=true`, and `disposition_changed` is true after the opportunity's content hash changes.
- [ ] AC12 `matrix_latest_rows` returns exactly one row per opportunity from the latest matrix, and is RLS-scoped.
- [ ] AC13 SC03 acceptance criteria AC1-AC12 pass (see `screens/SC03-opportunity-matrix.md` 13).
- [ ] AC14 The matrix router's OpenAPI snapshot is updated, and only `openapi/matrix.json` changes.
- [ ] AC15 All CI commands in `AGENTS.md` pass.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/matching/tests/test_store.py::test_save_run_atomic`, `::test_store_failure_publishes_nothing` | db |
| AC2 | `services/matching/tests/test_recommender.py::test_rows_carry_detail_and_program_names` | unit |
| AC3 | `services/matching/tests/test_properties.py::test_score_terms_sum_to_composite` | property |
| AC4 | `services/pillar/tests/test_matrix_api.py::test_full_rows_rank_order_and_past_due_dropped` | api (db) |
| AC5 | `test_matrix_api.py::test_hidden_counts` | api |
| AC6 | `test_matrix_api.py::test_filters_sort_paging` (parametrized), `::test_invalid_query` | api |
| AC7 | `test_matrix_api.py::test_summary_independent_of_filters` | api |
| AC8 | `test_matrix_api.py::test_empty_reasons` | api |
| AC9 | `test_matrix_api.py::test_explanation_terms_evidence_rules`, `::test_explanation_not_found` | api |
| AC10 | `test_matrix_api.py::test_disposition_atomic_event_and_undo`, `::test_disposition_validation` | api |
| AC11 | `test_matrix_api.py::test_skip_hidden_and_changed_flag` | api |
| AC12 | `services/matching/tests/test_store.py::test_latest_rows_view` | db |
| AC13 | the tests in SC03 14 (`apps/web/src/features/matrix/*.test.tsx`) | unit (web) |
| AC14 | `services/pillar/tests/test_openapi.py::test_router_snapshots` | api |
| AC15 | CI | ci |

## Out of scope

- The pursue endpoint (S04).
- Durable event consumption, input persistence, the daily re-score and the `rescoring` flag (S08).
- Rule approval (S08).
- Weight tuning UI and LambdaMART.
- Personal ranking by disposition.

## Decisions needed

1. **Who hosts the matching consumer in wave 1?** Recommended default: S05 ships only the store and the agent changes; the long-running worker is S08. Until S08, `recommendation.updated` reaches the API only where a process runs `MatchingAgent` with `PostgresMatchingStore` (tests, and the dev script `python -m hope_matching.dev_rescore`, which S05 adds).
2. **The `rescoring` flag.** S05 always returns `false`. Recommended default: S08 sets it to true while an input change is newer than the latest matrix (S08 owns the input table).
3. **Search scope for `q`.** Recommended default: title, funder name and source ID only, not the summary, so the results stay predictable.

## Catalog changes / SC03 gaps (for the orchestrator)

- SC03's funder line uses `funder.agency_name`, `funder.sub_agency` and `source.external_id`, but **these fields don't exist**. `GrantOpportunity` has `funder.name`, `funder.funder_id`, `funder.type`, `funder.aln[]` and `source.source_id`. Recommended default: SC03 shows `funder.name · source.source_id`. A sub-agency would be a C2 field on `Funder` (ingestion fills it).
- SC03 batch-loads titles with `GET /v1/opportunities?ids=…` (S03). API.md doesn't list an `ids` parameter, so S03 must add it.
- SC03's "Complete your profile (63%)" needs `GET /v1/agencies/{id}/profile/completeness`, which isn't in SC03's data table. S05 provides only `empty_reason: "profile_incomplete"`.
- SC03's "Re-scoring…" header needs `rescoring`, which S05 can't compute (see Decisions 2). S08 provides it.
- SC03 says "Skipped rows are hidden unless the 'Skip' filter is on". The "Skip" chip there is the *recommendation* filter. S05 separates the two concepts: SC03 should send `show_skipped=true` when that chip is active (or add a separate "Show skipped" control).
- API.md describes the disposition as "Watch / skip / pursue-later". SC03 and S05 use `watch | skip | none`. Recommended: update API.md and drop pursue-later.
- SC03's Pursue role (`program_director`, `executive_director`) doesn't match role names used in code today (`development_director`, `program_lead`, `org_admin`). S01 should fix the role catalog.
- The pursue contract SC03 relies on (201 `{workflow_id}`, 409 `already_pursuing` with `workflow_id`, 422 `ineligible`, request body `{agency_id}`) belongs in S04's spec. S05 provides `matrix_latest_rows` for the ineligible check.

## References

- `services/matching/src/hope_matching/{agents,recommender,eligibility,alignment,repository}.py`, `db/migrations/0400_matching.sql`, `services/pillar/src/hope_pillar/api/routes.py` (`get_matrix`), `apps/web/src/api/http.ts` (`summaryRow`), `apps/web/src/features/matrix/*`.
- `docs/specs/screens/SC03-opportunity-matrix.md`; blueprint 2.2, 5.3, 7.4.
