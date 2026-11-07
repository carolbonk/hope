# M2: Opportunity matrix: score breakdown, evidence, Watch/Skip (hackathon)

| | |
|---|---|
| Wave | MVP (runs in parallel with M1, M3-M7 after M0) |
| Depends on | M0 |
| Screens | SC03 (`screens/SC03-opportunity-matrix.md`) |
| Migrations | `db/migrations/0410_matrix_mvp.sql` (range 0410-0419) |
| Blueprint | 2.2 A4/A5/A6, 5.3 |
| Replaces for the MVP | S05 (full version kept for later; the WIP is on `specs/matching`) |
| Status | Draft |

## Goal

For the demo agency, show a ranked matrix of real opportunities that stays up to date. Each
row can be explained term by term, with the profile and RFP evidence behind every number,
and it can be marked Watch or Skip. This is the "why should we apply?" moment of the demo.
It must never show an empty or broken screen: scoring is automatic, cached, and works
without an OpenAI key.

## Current state (after M0)

- `hope_matching` already has the pure A4/A5/A6 engine:
  - `evaluate_eligibility`, `assess_alignment` (BM25 + embeddings + RRF, a 3-sample judge with median), `build_matrix`, `composite_score` and `select_portfolio`.
  - `MatchingAgent` is an event wrapper that keeps everything in memory.
  - `repository.save_matrix` / `latest_matrix` write to `opportunity_matrices` (`0400`, append-only), but nothing calls them.
- `EligibilityResult` / `AlignmentAssessment` are in `hope_core.schemas.matching` (M0 step 1). `MatrixRow.eligibility`, `scores` and `evidence_ids` are always present.
- `MockProvider` raises `LookupError` for any schema it has no responder for. So `default_gateway()` without a key **can't run A5 today**, because there's no `JudgeSample` responder outside the tests.
- `services/pillar/src/hope_pillar/api/matrix.py` (M0 split) serves `GET /v1/agencies/{agency_id}/matrix` from `tenant_opportunity` as a summary (`MatrixPage{items, next_cursor}`). There's no explanation or disposition endpoint.
- The web `api/matrix/` client (M0 split) maps summary items to fake rows (`summaryRow()`). `features/matrix/` filters client-side.
- Inputs live in tables owned by others:
  - the profile in `agency_profile_versions` (current = `valid_to IS NULL`, highest `version`)
  - opportunities in `opportunities` + `opportunity_versions` (M1 fills them from Grants.gov)
  - pursuits in `tenant_opportunity.workflow_id` / `state` (M4 writes them)

## Behaviour

### Recompute (`hope_matching/service.py`)

1. **`recompute(agency_id, *, gateway=None, today=None, url=None) -> RecomputeResult`** (`matrix_id`, `inputs_hash`, `rows`, `new_assessments`, `reused_assessments`, `skipped: bool`). It runs these steps in order:
   1. Loads the current profile (`AgencyProfile.model_validate(profile)`).
   2. Loads every opportunity whose current version has `application_due` > now or no due date (`GrantOpportunity.model_validate(normalized)`).
   3. Computes `inputs_hash = content_hash({"profile": [agency_id, version, content_hash(profile)], "opps": sorted([id, version] ...), "date": today.isoformat(), "engine": MODEL_VERSION})`.
   4. If the latest `matrix_inputs` row for the agency has the same hash, returns `skipped=True` and writes nothing.
   5. Otherwise, for each opportunity, reuses the stored assessment for `(profile_hash, opportunity_hash)` from `matching_assessments`, or runs `evaluate_eligibility` and then, unless the result is ineligible, `assess_alignment`, and stores it.
   6. Builds the matrix with `build_matrix(profile, assessed, MatchingConfig(), today=today)` and saves it (`repository.save_matrix` plus a `matrix_inputs` row) in one `tenant_tx`.

   A profile that doesn't exist yet raises `ProfileMissing`, and the API turns that into an `empty_reason`. A single opportunity that fails to validate or score is logged and left out; it never fails the whole run. A judge failure for one opportunity (all providers failed, or a budget was exceeded) stores eligibility only: the alignment is `None`, A = 0, and the risk says "alignment could not be scored".
2. **Gateway without a key.** `matching_gateway()` returns `default_gateway()`. When that is a `MockProvider`, it registers `hope_matching.mock_judge.respond` for `JudgeSample`. The mock judge is deterministic and so it is demo-quality:
   - For each rubric dimension, it takes the retrieved passages (the IDs in the prompt) and scores `40 + 60 × overlap`.
   - `overlap` is the share of distinct opportunity-query tokens (title, summary, priorities, criteria) that appear in that dimension's best passage. Dimension keywords pick the passage: `population` → program and outcome passages, `geography` → program passages, `theory_of_change` → `theory_of_change`/`mission`, `outcomes` → `outcome:*`, `capacity` → `capacity`, `relationship` → `history:*`.
   - It cites that passage's ID. If there's no matching passage, it scores 30 and cites the first retrieved ID.
   - It returns the same scores for all 3 samples, so there's no low confidence.

   With `HOPE_OPENAI_API_KEY` set, the real model judges and M2 code doesn't change.
3. **Concurrency.** The run holds `pg_try_advisory_xact_lock(hashtext('hope_matching:' || agency_id))`. If another run holds the lock, the call returns `skipped=True` straight away. `RUNNING` is an in-process `set[UUID]` of agencies being recomputed.
4. **When it runs.** Nothing is event-driven for the MVP:
   - `demo.seed()` runs it synchronously, after M1's seed has loaded opportunities.
   - `GET .../matrix` runs it **in the background** (FastAPI `BackgroundTasks`) whenever the current `inputs_hash` differs from the stored one, so profile edits, new opportunities and a new day are picked up on the next view.
   - The response returns the latest stored matrix right away, with `rescoring: true`. SC03 polls while `rescoring` is true.
   - Working out the current `inputs_hash` is a cheap query of ids and versions, about 5 ms for 100 opportunities.
5. **Rows.** `build_matrix` changes:
   - `top_matched_programs` holds program **names**, not ids, looked up in `profile.programs`.
   - `evidence_ids` holds the A5-cited passage IDs plus `rfp:{artifact_id}:{page}:{char_start}` keys for every eligibility, funding and deadline evidence item.
   - A pure `score_terms(scores, eligibility, weights) -> list[ScoreTerm]` returns `(key, label, value, scale, weight, contribution)`, where `contribution = round(gate × weight × value × (100 if key == "win_probability" else 1), 2)`. The contributions sum to `composite_score` within 0.01.
6. **Rule labels.** A pure `eligibility.rule_label(rule_id, clause_text)` maps rule ids to labels:

   | Rule id | Label |
   |---|---|
   | `applicant_type` | Applicant type |
   | `geography` | Geography |
   | `budget_band` | Budget band |
   | `registration.sam` | SAM.gov registration |
   | `registration.uei` | UEI |
   | `registration.<x>` | Registration: `<x>` |
   | `cost_share` | Cost share |
   | `clause.<i>` | The clause text, cut to 120 characters |

   A pure `rule_summary(outcome, facts)` returns a one-line sentence, for example "Your tax status 501(c)(3) is accepted", "SAM.gov registration expires 2026-12-01, before the deadline", or "Not checked automatically yet: needs a person to review".

### API (`services/pillar/src/hope_pillar/api/matrix.py`)

7. **`GET /v1/agencies/{agency_id}/matrix`** works like this:
   1. Reads the latest matrix for the agency. A different `agency_id` than `HOPE_AGENCY_ID` gives 404 `not_found`.
   2. Drops rows whose opportunity is now past due.
   3. Joins `matrix_dispositions`, and LEFT JOINs `tenant_opportunity` for `workflow_id` / `state`.
   4. Filters, in this order:
      - `eligibility`, counting what it removes as `hidden_ineligible`
      - skipped rows, unless `show_skipped`, counting what it removes as `hidden_skipped`
      - `recommendation`, `due_within_days` and `q`
   5. Sorts and pages. `rank` stays the snapshot rank.
   6. Computes `summary` from the rows left after the eligibility and skip filters.
   7. Schedules a background recompute if needed (step 4).
8. **`GET .../matrix/{opportunity_id}/explanation`** returns the 7 score terms with weights, contributions and evidence, the eligibility rules (fail, then review, then pass), the A5 rubric (median plus the three samples), effort drivers, risks, the explanation text and matched programs. Evidence is mapped as follows:
   - **Profile passages** become `kind: "profile"`. `source_label` is one of "Profile: Mission", "Profile: Theory of change", "Profile: Focus areas", "Profile: Programs · {name}", "Profile: Outcomes · {program}", "Profile: Grant history" or "Profile: Capacity". `quote` is the passage text, at most 300 characters.
   - **RFP evidence** becomes `kind: "rfp"`, with `source_label: "RFP p. {page}"` and the span. Funding fit evidence comes from `funding.evidence`, deadline evidence from `deadlines.application_due.evidence`, and eligibility evidence from the rule outcomes.
9. **`PUT .../matrix/{opportunity_id}/disposition`** upserts or clears one row in `matrix_dispositions`. Any role can do it. It never changes the score, rank or recommendation. An identical repeat is a no-op (200). `"none"` deletes the row, which is how SC03's Undo works.
10. **Pursue** is M4's endpoint. M2 exports `hope_matching.service.latest_row(agency_id, opportunity_id) -> MatrixRow | None`, so M4 can return 422 `ineligible` without reading matching tables.

## Contracts

- **Shared models used:** `OpportunityMatrix`, `MatrixRow`, `DimensionScores`, `Estimates`, `EligibilityResult`, `RuleOutcome`, `EffortEstimate`, `DimensionScore`, `AlignmentAssessment`, `AgencyProfile`, `GrantOpportunity`, `Evidence`, `Money`, `content_hash`, `tenant_tx`, `default_gateway`, `MockProvider`, `get_principal`, `Role`, `lib/problem.ts`.
- **Endpoint models** are defined in `api/matrix.py`, because they're endpoint shapes and not shared contracts. TS types are hand-written in `apps/web/src/api/matrix/types.ts`, matching the JSON below. The OpenAPI snapshot keeps the two in step. They are: `MatrixPage`, `MatrixListRow`, `MatrixSummary`, `MatrixDisposition`, `DispositionBody`, `MatrixExplanation`, `ScoreTermView`, `ExplanationEvidence`, `EligibilityRuleView` and `MatchedProgram`.
- **Events:** none for the MVP. Dispositions are plain rows.
- **Endpoints.** Every role in M0's `Role` enum can call them, with no extra role check. The tenant always comes from `HOPE_TENANT_ID`. Errors are problem+json with `code`.

  **`GET /v1/agencies/{agency_id}/matrix`**

  | Query | Type | Default | Rule |
  |---|---|---|---|
  | `recommendation` | comma list of `pursue,consider,watch,skip` | all | |
  | `eligibility` | comma list of `eligible,needs_review,ineligible` | `eligible,needs_review` | |
  | `due_within_days` | int 1-365 | none | Uses `application_due`. Rolling rows are excluded when this is set |
  | `q` | string, 1-100 chars | none | Case-insensitive match on title, `funder.name` and `source.source_id` |
  | `sort` | `rank`, `due`, `award` | `rank` | `due`: soonest first, rolling last. `award`: highest `award_ceiling` first, unknown last. Ties fall back to rank |
  | `show_skipped` | bool | `false` | |
  | `page` | int ≥ 1 | 1 | |
  | `page_size` | int 1-100 | 25 | `limit` is accepted as an alias (M7's dashboard uses `?limit=5`) |

  The old `cursor`, `state`, `min_score` and `due_before` parameters are removed. A bad value gives 422 `invalid_query`, and `detail` names the parameter.

  Response 200:

  ```json
  {
    "agency_id": "00000000-0000-4000-8000-0000000000a1",
    "generated_at": "2026-11-07T14:48:00Z",
    "model_version": "a6-heuristic-v1",
    "weights_profile": "heuristic-v1",
    "rescoring": false,
    "empty_reason": null,
    "total": 18, "hidden_ineligible": 4, "hidden_skipped": 1,
    "summary": {"open": 18, "pursue": 5, "due_within_14_days": 3},
    "page": 1, "page_size": 25, "page_count": 1,
    "rows": [{
      "opportunity_id": "5d1e2c8a-7a0e-4a52-9a43-3f1d2b8c9e01",
      "rank": 1, "composite_score": 87.2, "eligibility": "eligible", "recommendation": "pursue",
      "scores": {"mission_alignment": 91.0, "funding_fit": 80.0, "effort_to_funding": 78.0, "win_probability": 0.34,
                 "deadline_feasibility": 70.0, "funder_relationship": 0.0, "strategic_priority_boost": 100.0},
      "evidence_ids": ["program:mentor-futures", "theory_of_change", "rfp:art_7f3:4:120"],
      "estimates": {"expected_hours": 60.0, "expected_value": {"amount_minor": 8500000, "currency": "USD"}, "days_to_internal_deadline": 7},
      "capacity_fit": "fits",
      "explanation": "pursue (composite 87.2, eligibility eligible, capacity fits); mission alignment 91; funding fit 80; effort-to-funding 78; win probability 34%; deadline feasibility 70; relationship 0; strategic boost 100; about 60 staff hours; matched programs: Mentor Futures.",
      "top_matched_programs": ["Mentor Futures"],
      "risks": ["requires 20% cost share"],
      "disposition": null,
      "workflow_id": null,
      "lifecycle_state": null
    }]
  }
  ```

  The three empty cases each return 200 with `rows: []` and `total: 0`:

  | `empty_reason` | When | `rescoring` |
  |---|---|---|
  | `profile_incomplete` | No current profile row | false |
  | `not_scored_yet` | A profile exists but no matrix yet | true; a recompute is scheduled |
  | `no_opportunities` | A matrix exists with no open rows | |

  Errors: 404 `not_found`, 422 `invalid_query`.

  **`GET /v1/agencies/{agency_id}/matrix/{opportunity_id}/explanation`** returns 200:

  ```json
  {
    "opportunity_id": "5d1e2c8a-7a0e-4a52-9a43-3f1d2b8c9e01",
    "generated_at": "2026-11-07T14:48:00Z",
    "rank": 1, "composite_score": 87.2, "recommendation": "pursue", "gate": 1,
    "dimensions": [
      {"key": "mission_alignment", "label": "Mission alignment", "value": 91.0, "scale": 100, "weight": 0.35, "contribution": 31.85,
       "low_confidence": false,
       "rubric": [{"dimension": "population", "score": 92.0, "samples": [90.0, 92.0, 95.0], "rejected_samples": 0,
                   "evidence_ids": ["program:mentor-futures"], "rationale": "Serves youth 12-18, the NOFO's target population.", "low_confidence": false}],
       "evidence": [{"evidence_id": "program:mentor-futures", "kind": "profile", "source_label": "Profile: Programs · Mentor Futures",
                     "quote": "Mentor Futures. Weekly one-to-one mentoring for youth 12-18 in Baltimore City…",
                     "artifact_id": null, "page": null, "char_start": null, "char_end": null}]},
      {"key": "funding_fit", "label": "Funding fit", "value": 80.0, "scale": 100, "weight": 0.15, "contribution": 12.0, "low_confidence": false, "rubric": [],
       "evidence": [{"evidence_id": "rfp:art_7f3:4:120", "kind": "rfp", "source_label": "RFP p. 4",
                     "quote": "Awards of up to $250,000 for a 24-month period of performance.",
                     "artifact_id": "art_7f3", "page": 4, "char_start": 120, "char_end": 181}]},
      {"key": "effort_to_funding", "label": "Effort to funding", "value": 78.0, "scale": 100, "weight": 0.15, "contribution": 11.7, "low_confidence": false, "rubric": [], "evidence": []},
      {"key": "win_probability", "label": "Win probability", "value": 0.34, "scale": 1, "weight": 0.15, "contribution": 5.1, "low_confidence": false, "rubric": [], "evidence": []},
      {"key": "deadline_feasibility", "label": "Deadline feasibility", "value": 70.0, "scale": 100, "weight": 0.10, "contribution": 7.0, "low_confidence": false, "rubric": [], "evidence": []},
      {"key": "funder_relationship", "label": "Funder relationship", "value": 0.0, "scale": 100, "weight": 0.05, "contribution": 0.0, "low_confidence": false, "rubric": [], "evidence": []},
      {"key": "strategic_priority_boost", "label": "Strategic priority", "value": 100.0, "scale": 100, "weight": 0.05, "contribution": 5.0, "low_confidence": false, "rubric": [], "evidence": []}
    ],
    "eligibility": {"status": "eligible", "passed": 5, "failed": 0, "open": 0, "rules": [
      {"rule_id": "applicant_type", "label": "Applicant type", "outcome": "pass", "summary": "Your tax status 501(c)(3) is accepted", "evidence": []},
      {"rule_id": "registration.sam", "label": "SAM.gov registration", "outcome": "pass", "summary": "SAM.gov registration is active until 2027-06-30", "evidence": []}]},
    "effort": {"expected_hours": 60.0, "drivers": {"base": 8.0, "per_section": 16.0, "per_page": 22.5, "federal": 12.0, "per_form": 1.5}, "model": "heuristic-v1"},
    "estimates": {"expected_hours": 60.0, "expected_value": {"amount_minor": 8500000, "currency": "USD"}, "days_to_internal_deadline": 7},
    "capacity_fit": "fits",
    "risks": ["requires 20% cost share"],
    "explanation": "pursue (composite 87.2, …).",
    "matched_programs": [{"program_id": "mentor-futures", "name": "Mentor Futures"}]
  }
  ```

  Errors: 404 `not_found` (unknown agency, or the opportunity isn't in the latest matrix, or it is past due).

  **`PUT /v1/agencies/{agency_id}/matrix/{opportunity_id}/disposition`**

  Request body (`reason` only with `skip`; `reason_text` only with `reason: "other"`, at most 500 characters):
  `{"disposition": "skip", "reason": "too_much_effort", "reason_text": null}`.

  - `disposition`: `"watch"`, `"skip"` or `"none"`.
  - `reason`: `not_mission_fit`, `too_much_effort`, `deadline_too_soon`, `other`, or `null`.

  Response 200: `{"opportunity_id": "5d1e…", "disposition": {"disposition": "skip", "reason": "too_much_effort", "reason_text": null, "set_by": "demo", "set_at": "2026-11-07T15:02:11Z"}}`. After `"none"`, `disposition` is `null`. Errors: 404 `not_found`, 422 `invalid_disposition`.

- **Database** (`0410_matrix_mvp.sql`). Tenant RLS on every table, following `0400`:

  ```sql
  CREATE TABLE matching_assessments (
    tenant_id uuid NOT NULL REFERENCES tenants, agency_id uuid NOT NULL REFERENCES agencies,
    opportunity_id uuid NOT NULL REFERENCES opportunities,
    profile_hash text NOT NULL, opportunity_hash text NOT NULL,
    eligibility jsonb NOT NULL, alignment jsonb, passages jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agency_id, opportunity_id, profile_hash, opportunity_hash));
  CREATE TABLE matrix_inputs (
    matrix_id bigint PRIMARY KEY REFERENCES opportunity_matrices, tenant_id uuid NOT NULL REFERENCES tenants,
    agency_id uuid NOT NULL, inputs_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
  CREATE INDEX matrix_inputs_latest ON matrix_inputs (tenant_id, agency_id, matrix_id DESC);
  CREATE TABLE matrix_dispositions (
    tenant_id uuid NOT NULL REFERENCES tenants, agency_id uuid NOT NULL REFERENCES agencies,
    opportunity_id uuid NOT NULL REFERENCES opportunities,
    disposition text NOT NULL CHECK (disposition IN ('watch','skip')),
    reason text CHECK (reason IN ('not_mission_fit','too_much_effort','deadline_too_soon','other')),
    reason_text text CHECK (char_length(reason_text) <= 500),
    set_by text NOT NULL, set_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agency_id, opportunity_id),
    CHECK (reason IS NULL OR disposition = 'skip'), CHECK (reason_text IS NULL OR reason = 'other'));
  ```

  `passages` maps the cited evidence ID to the passage text the judge saw, so explanations still show the right quote after the profile changes.

## Demo seed (`hope_matching/demo.py:seed()`)

- It runs after M1's seed (see Requests to M0) and calls `recompute(HOPE_AGENCY_ID)` with `matching_gateway()`. It's idempotent: a second run returns `skipped=True` and writes no new matrix.
- It seeds no dispositions, so Watch/Skip are shown live in the demo.
- It prints `matrix: 18 rows (5 pursue, 4 ineligible hidden), 18 new assessments`.
- If M1 loaded no opportunities, the seed prints a warning and the matrix shows the `no_opportunities` state.

Test fixtures (offline) build on `hope_core.testing.factories` and `hope_matching.testing`:

| Fixture | Content |
|---|---|
| Demo profile | `profile()` with programs "Mentor Futures" (youth mentoring, Baltimore City) and "Family Food Access" |
| `opportunity(1)` | Eligible, pursue |
| `opportunity(2, days=20)` | Tight deadline |
| `opportunity(3)` | 25 % cost share, so needs review |
| `opportunity(4)` | Applicant type `"x"`, so ineligible |
| `opportunity(5, days=-1)` | Past due, never shown |
| `opportunity(6)` | Rolling, no deadline |

## Owns

```text
services/matching/**                              (incl. src/hope_matching/demo.py and tests)
services/pillar/src/hope_pillar/api/matrix.py
services/pillar/tests/snapshots/openapi/matrix.json
apps/web/src/features/matrix/**
apps/web/src/api/matrix/**
apps/web/src/app/matrix/**
db/migrations/0410_matrix_mvp.sql
```

API tests live in `services/matching/tests/test_matrix_api.py`, using `hope_pillar.api.create_app` with `migrated_db`, so they stay inside the Owns list.

## Acceptance criteria

- [ ] AC1 `recompute` stores the assessments, the matrix and `matrix_inputs` in one transaction. A second call with unchanged inputs is `skipped` and writes nothing. A profile edit or a new opportunity version re-scores only the changed pairs; the rest are reused.
- [ ] AC2 Without an OpenAI key, `matching_gateway()` scores alignment with the deterministic mock judge. Each dimension cites a retrieved passage ID, and the same inputs always give the same matrix.
- [ ] AC3 A failure to score one opportunity leaves it out (validation) or stores eligibility-only with the "alignment could not be scored" risk (judge). The run still succeeds.
- [ ] AC4 Two concurrent recomputes produce one matrix (advisory lock).
- [ ] AC5 `score_terms` contributions sum to `composite_score` within 0.01, and every contribution is 0 when the gate is 0 (Hypothesis).
- [ ] AC6 `GET matrix` returns rows in snapshot rank order with disposition and pursuit fields, and never returns past-due rows.
- [ ] AC7 Default filters hide ineligible and skipped rows. `hidden_ineligible`, `hidden_skipped`, `total` and `summary` match the rules above, and `summary` doesn't depend on `recommendation`, `due_within_days` or `q`.
- [ ] AC8 Every query parameter (filters, `q`, all three sorts, `page`, `page_size`, the `limit` alias) works as specified. A bad value gives 422 `invalid_query`.
- [ ] AC9 Each empty case returns the right `empty_reason`. Stale inputs schedule a background recompute and return `rescoring: true`, and the next GET after it finishes returns the new matrix with `rescoring: false`.
- [ ] AC10 The explanation returns all 7 terms in order, profile and RFP evidence with labels and spans, rules ordered fail/review/pass with labels and summaries, the rubric with samples, and matched programs with names. An unknown or past-due opportunity returns 404.
- [ ] AC11 The disposition PUT upserts, clears with `"none"`, is a no-op on repeat, and rejects invalid combinations with 422 `invalid_disposition`. A disposition never changes the rank or score.
- [ ] AC12 `latest_row` returns the row M4 needs, and `None` for unknown opportunities.
- [ ] AC13 `demo.seed()` is idempotent and prints the summary line.
- [ ] AC14 SC03 AC1-AC13 pass.
- [ ] AC15 Only `openapi/matrix.json` changes in the snapshots, and all CI commands in `AGENTS.md` pass offline.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/matching/tests/test_service.py::test_recompute_persists_and_skips_unchanged`, `::test_recompute_reuses_unchanged_pairs` | db |
| AC2 | `test_mock_judge.py::test_mock_judge_cites_retrieved_and_is_deterministic` | unit |
| AC3 | `test_service.py::test_one_bad_opportunity_does_not_fail_run`, `::test_judge_failure_stores_eligibility_only` | db |
| AC4 | `test_service.py::test_concurrent_recompute_single_matrix` | db |
| AC5 | `test_properties.py::test_score_terms_sum_to_composite` | property |
| AC6 | `test_matrix_api.py::test_rank_order_pursuit_and_past_due_dropped` | api (db) |
| AC7 | `test_matrix_api.py::test_hidden_counts_and_summary` | api |
| AC8 | `test_matrix_api.py::test_query_params` (parametrized), `::test_invalid_query` | api |
| AC9 | `test_matrix_api.py::test_empty_reasons`, `::test_background_rescore_flag` | api |
| AC10 | `test_matrix_api.py::test_explanation`, `::test_explanation_not_found` | api |
| AC11 | `test_matrix_api.py::test_disposition_upsert_clear_noop_validation` | api |
| AC12 | `test_service.py::test_latest_row` | db |
| AC13 | `test_demo.py::test_seed_idempotent` | db |
| AC14 | the tests in SC03 section 14 | web unit |
| AC15 | `services/pillar/tests/test_openapi.py::test_router_snapshots` + CI | ci |

## Out of scope

- Event-driven re-scoring and a worker (S08).
- LLM rule drafting and approval (S08).
- USAspending (S14).
- Weight tuning.
- Disposition history and events.
- Learned ranking.

## Requests to M0

1. Add `hope-matching` to `services/pillar/pyproject.toml` dependencies, so `api/matrix.py` can call `hope_matching.service`.
2. Make `hope-demo-seed` call seeds in dependency order: profile → `hope_ingestion` (M1) → `hope_matching` (M2) → the rest. Today the order is unspecified.
3. Confirm the `lib/problem.ts` export M2's client relies on: `class ProblemError extends Error { status: number; code: string; detail?: string; extras: Record<string, unknown> }`, thrown by every per-feature `http.ts`.
4. Confirm `components/ui` exports `Drawer` (`open`, `title`, `onClose`, `children`, `footer`) and `Toast` (`useToast().show({ message, action?: { label, href | onClick }, durationMs })`). SC03 uses both.

## Requests to M4

- Web client function in `apps/web/src/api/workflow/`: `pursue(opportunityId: string, body: { agency_id: string }): Promise<{ workflow_id: string; state: OpportunityState }>`, sending `POST /v1/opportunities/{opportunity_id}/pursue`. On failure it throws `ProblemError`:
  - 409 `already_pursuing` with `extras.workflow_id`
  - 422 `ineligible`
  - 403 `forbidden`
- The server returns 201 on success, and checks eligibility with `hope_matching.service.latest_row(...)`. The allowed roles are `development_director` and `executive_director` (SC03 "Can act").
- Pursue writes `tenant_opportunity.workflow_id` and `state`, so M2's matrix shows the "Pursuing" chip on the next fetch.

## Requests to M1

- `GET /v1/opportunities?ids=<uuid>,<uuid>…` (up to 100 ids) returns `{"items": [GrantOpportunity…]}` with the full normalized objects. Unknown ids are left out, with no error. The matching web client function in `apps/web/src/api/opportunities/` is `getMany(ids: string[]): Promise<GrantOpportunity[]>`. SC03 uses it for titles, funder line, award and due date.

## Decisions needed (recommended defaults)

1. **Re-scoring trigger.** Recommended default: a background recompute when `GET matrix` sees changed inputs, with a derived `rescoring` flag that SC03 polls every 3 s. No event consumer for the MVP.
2. **Judge samples with OpenAI.** Recommended default: keep 3 (it's the "LLM-as-judge" story). The first full scoring of about 20 opportunities is about 60 calls, which is why the seed runs before the demo.
3. **Skip semantics.** Recommended default: a skipped row is hidden until "Show them" is clicked (`show_skipped=true`). It's separate from the "Skip" *recommendation* filter.
4. **Roles.** Recommended default: any role can view and Watch/Skip. M4 enforces who can Pursue.

## References

- `services/matching/src/hope_matching/{service (new),agents,recommender,eligibility,alignment,repository,testing}.py`, `db/migrations/0400_matching.sql`, `services/pillar/src/hope_pillar/api/routes.py:get_matrix` (before the M0 split), `apps/web/src/features/matrix/*`.
- `docs/specs/features/S05-matrix-explainability-and-disposition.md` (full version), `docs/specs/screens/SC03-opportunity-matrix.md`.
