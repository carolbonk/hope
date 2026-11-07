# S08: Persistent matching state and rule approval

| | |
|---|---|
| Wave | 2 |
| Depends on | S05 |
| Screens | SC14 (`screens/SC14-eligibility-rule-review.md`) |
| Migrations | `db/migrations/0420_matching_state_and_rules.sql` |
| Blueprint | 2.2 A4 ("A human or the verifier must approve a new rule before it is used"), 7.3, 8.5 |
| Status | Draft |

## Goal

Make matching a durable service and let humans approve the eligibility rules an LLM drafts.

- **Durable service.** Matching survives restarts and processes each event exactly once. It re-scores daily, as deadlines move.
- **Rule approval.** Until a person approves a drafted rule, the clause stays "Needs review" on every matrix row. Once approved, the rule decides that clause automatically on the next re-score.

## Current state

- `MatchingAgent` (`hope_matching/agents.py`) keeps `profiles`, `opportunities` and `_cache` in memory. `run()` pulls from `PillarPort.subscribe(...)`. There is no worker process, and no idempotency beyond the in-memory cache. After S05 it saves assessments and matrices through `MatchingStore`.
- `hope_matching.eligibility`:
  - `draft_clause_rule(gateway, clause, budget)` returns the clause with `rule_status="draft"` and the LLM `compiled_rule`. If the rule fails `jsonlogic.validate` or uses variables outside `CLAUSE_VARIABLES`, it returns `rule_status="needs_review"` with no rule.
  - `evaluate_clause` passes or fails a clause only when `rule_status == "approved"`. **Nothing calls `draft_clause_rule` in production, and nothing can approve.**
- Clauses arrive inside `GrantOpportunity.eligibility.clauses[]` as `EligibilityClause{text, compiled_rule, rule_status, evidence}` from A2. A2 may already set `compiled_rule` and `rule_status`.
- `processed_events (consumer, event_id)` exists in `0001_core.sql`. `hope_pillar.pillar.KafkaPostgresPillar` implements `PillarPort` over Kafka and the outbox, and `hope-pillar-relay` / `hope-pillar-projector` are existing worker entry points.
- `services/pillar/src/hope_pillar/api/rules.py` is an empty mounted router (S00).

## Behaviour

### Durable matching

1. **Persisted inputs.** Each handled `profile.updated` or `opportunity.normalized` upserts `matching_inputs (kind, subject_id)` with the body, version, `content_hash` and source event ID.
   - Profiles: a lower `AgencyProfile.version` than the stored one is ignored (as in today's agent).
   - Opportunities: a lower `source.amendment_seq` is ignored.

   On start, the agent loads every input into memory and warms `_cache` from `matching_assessments` (S05), keyed by the hash pair. Only changed pairs call the judge.
2. **Exactly-once effects.** Each event is handled in one `tenant_tx`, which:
   - inserts `processed_events('matching', event_id)` with `ON CONFLICT DO NOTHING RETURNING`. If no row comes back, the event is a duplicate: skip it and ack.
   - upserts the inputs
   - saves the S05 run
   - writes the emitted events with `hope_core.outbox.write_event`, instead of `pillar.publish`

   Any exception rolls back everything and the event is redelivered. After `HOPE_MATCHING_MAX_ATTEMPTS` (default 5), the pillar's DLQ takes it (existing router behaviour).
3. **Consumed events.**
   - `opportunity.normalized` and `opportunity.amended`: amended is handled as normalized with the new body.
   - `profile.updated`.
   - `eligibility.rule_decided` (new, below): re-score only the rule's opportunity.
4. **Daily re-score.** The worker re-scores every agency at `HOPE_MATCHING_DAILY_RESCORE_UTC` (default `06:00`), because `deadline_feasibility` and `days_to_internal_deadline` change with the date and closed opportunities must drop out. It runs as a synthetic cause envelope with `event_type=recommendation.updated`, `producer=matching` and `subject_id=agency_id`, which is never published itself; only the outputs are.
   - It uses a Postgres advisory lock (`pg_try_advisory_lock(hashtext('hope_matching_daily'))`), so only one worker runs it.
   - It is skipped if a matrix newer than 20 h already exists.
5. **Worker.** `hope_matching.worker:main` (script `hope-matching-worker` in `services/matching/pyproject.toml`) builds:
   - a `KafkaPostgresPillar` (from the `hope-pillar` workspace dependency)
   - `build_gateway()` (S16, mock by default)
   - a `PostgresMatchingStore`

   It then loops `agent.run()`. On SIGTERM it finishes the current event and exits 0. `MatchingSettings` (`hope_matching/settings.py`, prefix `HOPE_`) holds `matching_max_attempts`, `matching_daily_rescore_utc`, `matching_max_rule_drafts_per_opportunity` (default 20) and `matching_run_max_calls` (default 60).
6. **`rescoring` flag (for SC03).** `GET /v1/agencies/{agency_id}/matrix` sets `rescoring: true` when `max(matching_inputs.updated_at)` is later than the latest matrix's `generated_at` and the input is less than 15 minutes old. That means an input change is waiting to be scored. After 15 minutes the flag clears even if nothing was scored, so a stuck consumer doesn't look busy forever.

### Rule drafting (LLM suggests)

7. On each opportunity version, for each clause `i`:
   - Compute `clause_hash = content_hash({"opportunity_id": id, "text": normalize_ws(clause.text)})`.
   - If a rule row with that hash already has `status` in `draft`, `needs_review` or `approved`, reuse it and skip drafting.
   - Otherwise draft it:
     - If A2 supplied a `compiled_rule`, re-validate it with `jsonlogic.validate` and the `CLAUSE_VARIABLES` allow-list. Store it as `draft` with `drafted_by = "A2"`, or as `needs_review` if it fails. **Upstream `rule_status` is ignored. Only S08 approval counts.**
     - Else call `draft_clause_rule(gateway, clause, budget)` (SMALL tier, `untrusted()` clause text, `RuleDraft` schema). Store a `draft` or `needs_review` row with `drafted_by = "A4:<model_version>"` and the model's `rationale`.
   - Drafting stops after `matching_max_rule_drafts_per_opportunity`, or on `BudgetExceededError`. The remaining clauses get a `needs_review` row with `rationale = "drafting skipped: budget"`.
   - Each new row emits `eligibility.rule_drafted`.
8. When a new opportunity version drops a clause, or changes its text (a new hash), the older rows with the old hash and `status` in `draft`, `needs_review` or `approved` become `superseded`, and `superseded_by` points to the new row if there is one.
9. **Evaluation overlay (pure).** `rules.apply_rules(opportunity, rules) -> GrantOpportunity` returns a copy where:
   - Every clause whose hash has an `approved` row gets `compiled_rule = row.compiled_rule` and `rule_status = "approved"`.
   - **Every other clause** gets `compiled_rule = None` and `rule_status` equal to the row's status, or `needs_review`.

   The agent always evaluates the overlaid opportunity. So an LLM rule never decides a clause until a human approves it (blueprint 2.2), and an A2-provided `rule_status="approved"` can't bypass approval.

### Rule approval (humans decide)

10. **Approve.** `POST /v1/rules/{rule_id}/approve` with body `{"rule_hash": "...", "comment": null}`:
    1. Requires role `program_director`, `development_director` or `org_admin` (see Decisions). Otherwise 403 `forbidden`.
    2. Locks the row `FOR UPDATE`.
    3. If `status != 'draft'`, returns 409 `invalid_state` with `status`.
    4. If `rule_hash` doesn't match, returns 409 `stale_artifact` with `current_hash`.
    5. Re-validates the rule (`jsonlogic.validate`, the allow-list and `MAX_NODES`). On failure, returns 422 `invalid_rule`, which shouldn't happen but is defence in depth.
    6. Sets `approved`, `decided_by`, `decided_role`, `decided_at` and `decision_comment`. Appends to `eligibility_rule_decisions` and writes `eligibility.rule_decided` with `write_event`, all in one transaction.
    7. The matching worker re-scores that opportunity, so the matrix updates within one consumer cycle (usually seconds).
11. **Reject.** `POST /v1/rules/{rule_id}/reject` with body `{"rule_hash": "...", "reason": "wrong_logic" | "wrong_variables" | "clause_not_applicable" | "other", "comment": "..."}`.
    - `comment` is required (3-1000 characters) when `reason = other`; otherwise it's optional. A missing comment gives 422 `comment_required`.
    - The checks are the same as approve. The status becomes `rejected`.
    - The clause stays `needs_review` on matrix rows, permanently, until a new opportunity version produces a new hash.
12. **Read.** `GET /v1/rules` lists rules and `GET /v1/rules/{rule_id}` returns one. Both include:
    - the opportunity's title and due date
    - a deterministic plain-language rendering, `rules.describe_rule(rule) -> str`. For example, `{"in":[{"var":"applicant.tax_status"},["501c3"]]}` becomes "Applicant tax status is one of: 501(c)(3)". The renderer supports every operator in `jsonlogic.OPS`; anything else becomes "Complex rule (see JSON)".
    - a **preview**: the rule evaluated with `_run` against the facts of the single agency's current profile (`eligibility.facts`). The preview reports the outcome, and the facts it used with their values, so the reviewer sees what approving would do. If there's no profile, `preview` is null with `preview_unavailable: "no_profile"`.
13. There is no in-place editing of a rule (see Decisions). A wrong draft is rejected.

## Contracts

- **Shared models used:** `EligibilityClause`, `Evidence`, `GrantOpportunity`, `AgencyProfile`, `PillarEnvelope`, `EventType`, `Topic`, `ModelGateway`, `RunBudget`, `content_hash`, `hope_core.outbox.write_event`, `hope_core.errors`, `hope_core.auth.require_roles`, and S16's `build_gateway`.
- **Shared contract additions** (C2):
  - `EventType.ELIGIBILITY_RULE_DRAFTED = "eligibility.rule_drafted"` and `EventType.ELIGIBILITY_RULE_DECIDED = "eligibility.rule_decided"`, both on `Topic.OPPORTUNITY_EVENTS`.
  - `hope_core.schemas.matching.EligibilityRuleDrafted`: `rule_id: UUID`, `opportunity_id: UUID`, `clause_index: int`, `clause_hash: str`, `rule_hash: str | None`, `status: Literal["draft","needs_review"]`, `drafted_by: str`.
  - `EligibilityRuleDecided`: `rule_id`, `opportunity_id`, `clause_hash`, `rule_hash`, `decision: Literal["approved","rejected"]`, `reason: str | None`, `decided_by: str`, `decided_role: str`, `decided_at: datetime`.
  - `EligibilityRuleView`: the item shape in the JSON example below.
  - `RulePreview`: `outcome: Literal["pass","fail","review"]`, `summary: str`, `facts_used: dict[str, str | int | bool | None]`.
  - `RuleListPage`: `items`, `total`, `page`, `page_size`, `counts: dict[str, int]`.
  - `ApproveRuleBody`, `RejectRuleBody`.
  - `hope_core.schemas.matching.RuleStatus = Literal["draft","needs_review","approved","rejected","superseded"]`.
- **Events:**

  | Event | Producer | Consumers |
  |---|---|---|
  | `eligibility.rule_drafted` | matching worker, `agent_id="A4"` | S12 (notify reviewers; later) |
  | `eligibility.rule_decided` | pillar API | matching (re-score), S13 (audit) |

  Both use `data_classification="internal"` and `subject_id = opportunity_id`.
- **Endpoints.** All need a signed-in principal. Errors are problem+json.

  **`GET /v1/rules`**

  | Query | Type | Default | Rule |
  |---|---|---|---|
  | `status` | comma list of `RuleStatus` | `draft` | |
  | `opportunity_id` | uuid | none | |
  | `q` | string, 1-100 chars | none | Case-insensitive match on clause text and opportunity title |
  | `sort` | `due` or `drafted` | `due` | `due` is the opportunity's `application_due` ascending, nulls last, then `drafted_at`. `drafted` is newest first |
  | `page` | int ≥ 1 | 1 | |
  | `page_size` | int 1-100 | 25 | |

  Unknown values return 422 `invalid_query`. `counts` covers every status for the current `opportunity_id`/`q` filter, regardless of `status`. Response 200:

  ```json
  {
    "items": [{
      "rule_id": "8c0f…", "opportunity_id": "5d1e…", "opportunity_title": "Youth Mentoring Expansion",
      "funder_name": "Office of Juvenile Justice and Delinquency Prevention", "application_due": "2026-11-19T21:00:00Z",
      "clause_index": 2, "clause_text": "Applicants must be nonprofit organizations serving youth in Maryland.",
      "evidence": [{"artifact_id": "art_7f3", "page": 6, "char_start": 410, "char_end": 482, "quote": "Applicants must be nonprofit…"}],
      "compiled_rule": {"and": [{"in": [{"var": "applicant.tax_status"}, ["501c3"]]}, {"in": ["US-MD", {"var": "applicant.geo_scopes"}]}]},
      "plain_text": "Applicant tax status is one of: 501(c)(3), AND applicant serves US-MD",
      "variables": ["applicant.geo_scopes", "applicant.tax_status"],
      "rationale": "Clause restricts applicant type and state.", "status": "draft", "rule_hash": "sha256:41a…",
      "drafted_by": "A4:a6-heuristic-v1", "drafted_at": "2026-11-07T14:40:00Z",
      "decided_by": null, "decided_role": null, "decided_at": null, "decision_reason": null, "decision_comment": null,
      "preview": {"outcome": "pass", "summary": "Your agency passes this rule",
                  "facts_used": {"applicant.tax_status": "501c3", "applicant.geo_scopes": "US, US-MD, 24510"}},
      "preview_unavailable": null, "superseded_by": null
    }],
    "total": 3, "page": 1, "page_size": 25, "counts": {"draft": 3, "needs_review": 1, "approved": 12, "rejected": 2, "superseded": 0}
  }
  ```

  **`GET /v1/rules/{rule_id}`** returns 200 with one item in the same shape, or 404 `not_found`.

  **`POST /v1/rules/{rule_id}/approve`** and **`POST /v1/rules/{rule_id}/reject`** return 200 with the updated item. Errors:
  - 403 `forbidden`
  - 404 `not_found`
  - 409 `stale_artifact` (body includes `current_hash`)
  - 409 `invalid_state` (body includes `status`)
  - 422 `invalid_rule` (approve)
  - 422 `comment_required` (reject)
  - 422 `invalid_body`

- **Database** (`0420_matching_state_and_rules.sql`). Every table has tenant RLS like `0400`, with grants to `hope_app` and `hope_system`.

  ```sql
  CREATE TABLE matching_inputs (
    tenant_id uuid NOT NULL REFERENCES tenants, kind text NOT NULL CHECK (kind IN ('profile','opportunity')),
    subject_id uuid NOT NULL, version int NOT NULL, content_hash text NOT NULL, body jsonb NOT NULL,
    source_event_id uuid NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, kind, subject_id));
  CREATE TABLE eligibility_rules (
    rule_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES tenants,
    opportunity_id uuid NOT NULL REFERENCES opportunities, clause_index int NOT NULL,
    clause_hash text NOT NULL, clause_text text NOT NULL, evidence jsonb NOT NULL DEFAULT '[]',
    compiled_rule jsonb, variables text[] NOT NULL DEFAULT '{}', rationale text,
    status text NOT NULL CHECK (status IN ('draft','needs_review','approved','rejected','superseded')),
    rule_hash text, drafted_by text NOT NULL, drafted_at timestamptz NOT NULL DEFAULT now(),
    decided_by text, decided_role text, decided_at timestamptz, decision_reason text, decision_comment text,
    superseded_by uuid REFERENCES eligibility_rules,
    CHECK ((status = 'draft') = (compiled_rule IS NOT NULL AND rule_hash IS NOT NULL) OR status <> 'draft'),
    CHECK (status <> 'approved' OR (compiled_rule IS NOT NULL AND decided_by IS NOT NULL)));
  CREATE UNIQUE INDEX eligibility_rules_active ON eligibility_rules (tenant_id, clause_hash)
    WHERE status IN ('draft','needs_review','approved');
  CREATE INDEX eligibility_rules_status ON eligibility_rules (tenant_id, status, drafted_at DESC);
  CREATE TABLE eligibility_rule_decisions (
    decision_id bigserial PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants,
    rule_id uuid NOT NULL REFERENCES eligibility_rules, rule_hash text NOT NULL,
    decision text NOT NULL CHECK (decision IN ('approved','rejected')), reason text, comment text,
    decided_by text NOT NULL, decided_role text NOT NULL, decided_at timestamptz NOT NULL DEFAULT now());
  -- forbid_mutation trigger on eligibility_rule_decisions
  ```

  `rule_hash = content_hash({"clause_hash": …, "compiled_rule": …})`.

## Owns

Matching files are listed one by one, because S14 (also wave 2) owns `features/**` and `recommender.py`.

```text
services/matching/pyproject.toml
services/matching/src/hope_matching/agents.py
services/matching/src/hope_matching/eligibility.py
services/matching/src/hope_matching/repository.py
services/matching/src/hope_matching/rules.py
services/matching/src/hope_matching/settings.py
services/matching/src/hope_matching/worker.py
services/matching/src/hope_matching/testing.py
services/matching/tests/test_agent.py
services/matching/tests/test_durable.py
services/matching/tests/test_rules.py
services/matching/tests/test_worker.py
services/pillar/src/hope_pillar/api/rules.py
services/pillar/src/hope_pillar/api/matrix.py       (the `rescoring` flag only)
services/pillar/tests/test_rules_api.py
services/pillar/tests/snapshots/openapi/rules.json
services/pillar/tests/snapshots/openapi/matrix.json
apps/web/src/features/rules/**
apps/web/src/api/rules/**
apps/web/src/app/rules/page.tsx
db/migrations/0420_matching_state_and_rules.sql
uv.lock
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 After a restart, the agent reloads its inputs from `matching_inputs` and doesn't call the judge for unchanged (profile, opportunity) pairs.
- [ ] AC2 Delivering the same event twice produces one set of outputs. A failure mid-handler leaves no inputs, matrix, assessments or outbox rows behind.
- [ ] AC3 Stale profile versions and lower amendment sequences are ignored.
- [ ] AC4 The daily re-score runs once across two workers (advisory lock), drops past-due opportunities, and is skipped when a matrix less than 20 h old exists.
- [ ] AC5 Drafting reuses the existing rule for an unchanged clause hash, stores A2 rules as drafts after re-validation, stores invalid drafts as `needs_review`, and stops at the per-opportunity cap or on budget exhaustion.
- [ ] AC6 `apply_rules` lets only `approved` rules evaluate. An upstream `rule_status="approved"` without an approved row still gives `review` (property test over random statuses).
- [ ] AC7 Changing a clause's text in a new opportunity version supersedes the old rule and creates a new draft.
- [ ] AC8 Approve: wrong role returns 403, wrong hash 409 `stale_artifact` with `current_hash`, a non-draft 409 `invalid_state`, an invalid rule 422 `invalid_rule`. Success writes the row, the decision history and `eligibility.rule_decided` atomically.
- [ ] AC9 After approval, the next re-score turns that clause into `pass` or `fail`, and the matrix row's eligibility changes accordingly.
- [ ] AC10 Reject requires a comment for `other`, keeps the clause in review, and records the decision.
- [ ] AC11 `GET /v1/rules` filters, sorts, paginates and counts as specified. `plain_text` and `preview` are deterministic.
- [ ] AC12 `rescoring` is true only while an input is newer than the matrix and less than 15 minutes old.
- [ ] AC13 `hope-matching-worker` exits 0 on SIGTERM after finishing the current event.
- [ ] AC14 SC14 acceptance criteria pass.
- [ ] AC15 All CI commands in `AGENTS.md` pass.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/matching/tests/test_durable.py::test_restart_reloads_inputs_and_cache` | db |
| AC2 | `test_durable.py::test_duplicate_event_idempotent`, `::test_failure_rolls_back_everything` | db |
| AC3 | `test_agent.py::test_stale_profile_versions_and_cross_tenant_payloads_are_ignored` (extended), `test_durable.py::test_lower_amendment_ignored` | unit/db |
| AC4 | `test_worker.py::test_daily_rescore_lock_and_skip` | db |
| AC5 | `test_rules.py::test_drafting_reuse_validation_and_caps` | unit |
| AC6 | `test_rules.py::test_only_approved_rules_decide` (Hypothesis) | property |
| AC7 | `test_rules.py::test_clause_change_supersedes` | db |
| AC8 | `services/pillar/tests/test_rules_api.py::test_approve_guards`, `::test_approve_atomic_event` | api |
| AC9 | `test_durable.py::test_approval_changes_eligibility_on_rescore` | db |
| AC10 | `test_rules_api.py::test_reject_comment_rules` | api |
| AC11 | `test_rules_api.py::test_list_filters_sort_counts`, `test_rules.py::test_describe_rule_golden` | api/unit |
| AC12 | `services/pillar/tests/test_matrix_api.py::test_rescoring_flag` | api |
| AC13 | `test_worker.py::test_sigterm_graceful` | unit |
| AC14 | `apps/web/src/features/rules/*.test.tsx` (SC14 14) | unit (web) |
| AC15 | CI | ci |

## Out of scope

- Manual rule authoring and editing.
- Verifier (A11) auto-approval.
- Reusing approved rules across opportunities with identical clause text.
- OPA/Rego.
- Notifying reviewers of new drafts (S12 can subscribe to `eligibility.rule_drafted`).

## Decisions needed

1. **Approver roles.** Recommended default: `program_director`, `development_director` and `org_admin`. S01 owns the role catalog; the role names here must match it.
2. **Rule editing.** Recommended default: none for the MVP. Reject with a reason, and the clause stays in manual review. Editing would need a second approver (an LLM drafted it, a human edited it, and someone else approves), which is more than the MVP needs.
3. **Cross-opportunity reuse.** Recommended default: off. The same boilerplate clause in two NOFOs is approved twice. Revisit once there's data on how often clauses repeat.
4. **The matching dependency on `hope-pillar`.** Recommended default: the matching worker depends on the `hope-pillar` workspace package to get `KafkaPostgresPillar`. The alternative is C2 moving the Kafka adapter into `hope_core`.

## Catalog changes

- API.md: add `GET /v1/rules/{rule_id}` (owned by S08, called by SC14 for deep links).
- FOLDERS.md: matching in wave 2 is split between S08 (the files listed above) and S14 (`features/**`, `recommender.py`). Add `hope-matching-worker` as a process (S28 deploys it).

## References

- `services/matching/src/hope_matching/{agents,eligibility,jsonlogic,repository}.py`, `db/migrations/0001_core.sql` (`processed_events`, `outbox`), `services/pillar/src/hope_pillar/{pillar,workers,router}.py`.
- Blueprint 2.2 A4, 7.3, 8.5; S05; S16.
