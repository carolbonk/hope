# S07: Wire real agents into the lifecycle workflow

> **Out of scope for the hackathon. Don't build this.** This spec belongs to the earlier design (the Phase 1 pipeline and the M0-M7 / S-spec roadmap). Hackathon agents build only H0-H5 (see [`README.md`](../README.md)). Keep this file for after the hackathon.

| | |
|---|---|
| Wave | 1 |
| Depends on | S00 |
| Screens | - |
| Migrations | - |
| Blueprint | 2.2 (A0, A4-A7), 4.2, 4.3, Appendix B |
| Status | Draft |

## Goal

Replace the workflow's stub agents with adapters that call the real matching (A4/A5/A6) and
budget (A7) code, load real profile and opportunity context, and turn real
`profile.updated` / `opportunity.amended` events into workflow signals. After this, a pursued
opportunity reaches HITL-1 with a real matrix row and HITL-2 with a real, sealed budget ledger.
Narrative, compliance, packaging and submission stay stubbed until S17, S19, S21 and S22.

## Current state

- `hope_workflow.agents.AgentRegistry` holds nine typed agents (`eligibility`, `alignment`,
  `recommend`, `budget`, `verify`, `narrative`, `compliance`, `package`, `submit`);
  `AgentActivities.by_queue()` registers one activity per `TaskQueue` (`q.eligibility`,
  `q.align`, `q.recommend`, `q.budget`, `q.verify`, `q.draft`, `q.compliance`, `q.package`,
  `q.submit`).
- `hope_workflow.stubs.StubAgents.registry()` is the only registry; `hope_workflow.worker.serve`
  always uses it.
- `platform.load_context` uses `hope_workflow.ports.InMemoryContextSource`, which falls back to
  `hope_core.testing.factories` for unknown keys.
- Real code that exists:
  - `hope_matching.eligibility.evaluate_eligibility(profile, opportunity, today, monthly_hours)
    -> EligibilityResult` (status `eligible | needs_review | ineligible`, `failed_rules`,
    `review_rules`, `outcomes`, `evidence`, `effort: EffortEstimate`).
  - `hope_matching.alignment.assess_alignment(gateway, profile, opportunity, config, budget)
    -> AlignmentAssessment` (`score`, `dimension_scores`, `matched_programs`, `gaps`,
    `low_confidence`, ...).
  - `hope_matching.recommender.build_matrix(profile, [Assessed], config, today, generated_at)
    -> OpportunityMatrix` with `MatrixRow`s.
  - `hope_budget.framework.FrameworkGenerator(gateway, resolver, policy).draft(opportunity,
    profile, framework_id=...) -> FrameworkDraft` (`framework`, `solution`, `structure`,
    `attempts`, `needs_review`); raises `MissingCeilingError`, `FrameworkNeedsReviewError`.
    `hope_budget.framework.framework_hash`, `drafted_envelope`; `hope_budget.store.save_ledger`;
    `hope_budget.engine.is_sealed`; `hope_budget.resolver.InMemoryCostBasisResolver`.
  - `hope_profile.repository.ProfileRepository.current(tenant_id, agency_id) -> ProfileVersion`.
  - Opportunities: `opportunities` + `opportunity_versions.normalized` (`GrantOpportunity` JSON).
- `hope_workflow.client.revalidate_signal` assumes a `profile.updated` payload of
  `{version, changed_paths}`, but the real payload is `ProfileUpdated` (`agency_id`, `version`,
  `previous_version`, `changes: list[FieldChange]`, `protected_changed`, ...).
  `amendment_signal` assumes `{amendment_seq, affected}`, but the real payload is
  `OpportunityAmended` (`opportunity_id`, `from_version`, `to_version`, `amendment_seq`,
  `changes: list[FieldChange]`). Nothing consumes either event to signal workflows.
- After S00, the workflow contracts live in `hope_core.schemas.workflow` and the matching ones in
  `hope_core.schemas.matching`.

## Behaviour

1. **Registry.** `hope_workflow.adapters.real_registry(deps: AdapterDeps) -> AgentRegistry`
   builds the registry from real adapters for `eligibility`, `alignment`, `recommend`, `budget`,
   `verify`, and from `StubAgents` for `narrative`, `compliance`, `package`, `submit`.
   `AdapterDeps` holds `gateway: ModelGateway`, `resolver: CostBasisResolver`,
   `database_url: str`, `pillar: PillarPort`, `clock: Callable[[], datetime]`.
2. **Worker flag.** `python -m hope_workflow.worker --agents real|stub` (default `stub` until
   S28 sets `real` in deployed environments; also `HOPE_WORKFLOW_AGENTS`). `--agents real`
   implies `--postgres` for approvals and projection. The gateway comes from
   `hope_core.model_gateway` with `HOPE_MODEL_PROVIDER` (`mock` in tests; S16 adds real
   providers).
3. **Context.** `adapters.context.PostgresContextSource.load(tenant_id, agency_id,
   opportunity_id)` reads the current profile via `ProfileRepository.current` and the current
   opportunity version (`opportunities.current_version` -> `opportunity_versions.normalized`),
   validates both models, and raises `ApplicationError(non_retryable=True, type="not_found")`
   when either is missing, so the workflow fails fast instead of retrying for 8 attempts.
4. **Eligibility (A4).** Calls `evaluate_eligibility(profile, opportunity, today=clock().date())`
   and maps the result to the workflow's eligibility contract: `status` unchanged;
   `reasons = failed_rules + review_rules` (rule ids, in that order); `effort_hours =
   effort.hours`. The full matching result is published as
   `opportunity.eligibility_evaluated` with `trace.correlation_id = workflow_id`, using
   `hope_matching.agents.SCHEMA_REFS` and `PRODUCERS`. No LLM call.
5. **Alignment (A5).** Calls `assess_alignment(gateway, profile, opportunity)` with a
   `RunBudget` from `MatchingConfig` defaults and maps `score`, `rationale` (from the matching
   result's `gaps`/dimension summaries; never generated text containing money) and `evidence`.
   Publishes `opportunity.alignment_scored`. Gateway errors that are transient
   (`ModelGatewayError` subclasses marked retryable) re-raise so Temporal retries; schema
   violations after the gateway's own retries raise `ApplicationError(non_retryable=True,
   type="model_output_invalid")`.
6. **Recommend (A6).** Calls `build_matrix(profile, [Assessed(opportunity, eligibility,
   alignment)], today=clock().date())` with the full matching models (not the mapped ones) and
   returns its single `MatrixRow`. Rank is always 1 for a single-row matrix; the portfolio rank is
   S05's job and is not overwritten here. Publishes `recommendation.updated`.
7. **Budget (A7).** Calls `FrameworkGenerator(gateway, resolver).draft(opportunity, profile,
   framework_id=uuid5(workflow_id + attempt))`, then in one tenant transaction inserts the
   `frameworks` row (`status = 'draft'`, next `version` for the opportunity and agency) and the
   sealed ledger (`save_ledger`), and writes `framework.drafted` (`drafted_envelope`) through the
   outbox. Returns the workflow's `BudgetDraft` with `drafted_by` set to the HITL-1 GO decider
   (`BudgetRequest.go.decided_by`; see Decisions needed). Revision feedback
   (`AgentContext.feedback`) is passed into the generator's prompt as untrusted text
   (`hope_core.untrusted`). `MissingCeilingError` -> non-retryable `ApplicationError(type=
   "missing_ceiling")`, which the workflow surfaces as a failed verify (see step 8).
   Money only comes from the budget engine; the LLM proposes structure only (S06/A7 rules).
8. **Verify (framework).** Deterministic, no LLM: passes when the ledger is sealed
   (`is_sealed`), its `content_hash` matches, every `cap_checks[].ok` is true, and
   `FrameworkDraft.needs_review` is false. `issues` lists each failing check id
   (`"cap:indirect_rate"`, `"ledger:unsealed"`, ...). Narrative verification stays stubbed until
   S18. The workflow's existing revision loop (`MAX_REVISIONS`) is unchanged.
9. **Signal bridge.** `adapters.signals.SignalBridge` (consumer group `workflow-signals`)
   subscribes to `profile.updated` and `opportunity.amended`:
   - `profile.updated` with `protected_changed = true`: `changed_paths = [c.path for c in changes]`
     filtered to `PROTECTED_PROFILE_PATHS`; signal `revalidate(RevalidateSignal(profile_version=
     version, changed_paths))` to every non-terminal workflow of that agency
     (`tenant_opportunity` rows with a `workflow_id`).
   - `opportunity.amended`: map each changed path to an area with `AMENDMENT_AREAS`
     (`eligibility.*` -> eligibility; `funding.*`, `budget.*`, `cost_share.*` -> budget;
     `requirements.sections*`, `requirements.attachments*` -> required_sections;
     `deadlines.*` -> deadline); paths that map to nothing are ignored; signal
     `opportunity_amended(AmendmentSignal(amendment_seq, affected))` to every non-terminal
     workflow for that opportunity, only when `affected` is non-empty.
   - A workflow that is already closed (`RPCError` NOT_FOUND / already completed) is skipped
     and logged. Each event is processed once (`processed_events`, consumer `workflow-signals`).
   - `client.revalidate_signal` and `client.amendment_signal` are rewritten to parse the real
     payload models and are what the bridge calls.
   - Runs as `python -m hope_workflow.adapters.signals`.
10. **Tenant.** Every adapter uses `tenant_tx(conn, HOPE_TENANT_ID)` via the `tenant_id` already in
    the activity input; nothing reads a tenant from elsewhere.

## Contracts

- **Shared models used:** `AgencyProfile`, `GrantOpportunity`, `MatrixRow`, `OpportunityMatrix`,
  `ProposalFramework`, `BudgetLedger`, `HitlDecision`, the S00-promoted
  `hope_core.schemas.workflow` models (`AgentContext`, `BudgetRequest`, `BudgetDraft`,
  `VerifyRequest`, `VerificationReport`, `RevalidateSignal`, `AmendmentSignal`, `ProfileArea`),
  `hope_core.schemas.matching` (`EligibilityResult`, `AlignmentAssessment`),
  `hope_core.schemas.profile_events` (`ProfileUpdated`, `FieldChange`),
  `hope_core.schemas.ingest` (`OpportunityAmended`).
- **Shared contract additions** (S00 or C2):
  - S00 promotes both `hope_matching.contracts.EligibilityResult`/`AlignmentAssessment` and
    `hope_workflow.contracts.EligibilityResult`/`AlignmentAssessment`. The names collide in the
    exported JSON Schema and TS types. Rename the workflow ones to `EligibilityVerdict` and
    `AlignmentSummary` in `hope_core.schemas.workflow` (S07 maps matching -> workflow models).
  - `hope_core.schemas.workflow.ProfileArea` gains nothing; `AMENDMENT_AREAS:
    dict[str, ProfileArea]` (path prefix -> area) moves next to `ROLLBACK_ON` in
    `hope_core.schemas.lifecycle` so the workflow and ingestion agree on it.
- **Events:** consumes `profile.updated`, `opportunity.amended`; produces
  `opportunity.eligibility_evaluated`, `opportunity.alignment_scored`, `recommendation.updated`,
  `framework.drafted` (all with `trace.correlation_id = workflow_id`).
- **Endpoints:** none.
- **Database:** no new tables. Writes `frameworks`, `budget_ledgers`, `outbox`,
  `processed_events`; reads `agency_profile_versions`, `opportunities`, `opportunity_versions`,
  `tenant_opportunity`.

## Owns

```text
services/workflow/src/hope_workflow/adapters/**
services/workflow/src/hope_workflow/worker.py
services/workflow/src/hope_workflow/client.py
services/workflow/pyproject.toml (adds hope-matching, hope-budget, hope-profile)
services/workflow/tests/test_adapters.py
services/workflow/tests/test_signal_bridge.py
services/workflow/tests/test_lifecycle_real_agents.py
uv.lock (regenerated only)
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 `real_registry` returns real adapters for eligibility, alignment, recommend, budget and verify, and stubs for the other four; the worker's `--agents` flag selects it.
- [ ] AC2 `PostgresContextSource` loads the current profile and opportunity, and a missing one fails the activity as non-retryable `not_found`.
- [ ] AC3 The eligibility adapter maps `failed_rules`/`review_rules`/`effort.hours` exactly and publishes `opportunity.eligibility_evaluated` with the workflow's correlation id.
- [ ] AC4 The alignment adapter calls the gateway only through `ModelGateway.structured` (MockProvider in tests) and maps the score; invalid model output fails non-retryably.
- [ ] AC5 The recommend adapter returns the `MatrixRow` from `build_matrix` for the single opportunity.
- [ ] AC6 The budget adapter persists the framework and sealed ledger and the `framework.drafted` event in one transaction (rollback test), and sets `drafted_by` to the GO decider.
- [ ] AC7 Framework verification fails with named issues for an unsealed ledger, a hash mismatch and a failing cap check, and passes for a clean ledger.
- [ ] AC8 With the time-skipping environment and real adapters (mock LLM), a pursued opportunity reaches `AwaitingGoNoGo` with a real matrix row and, after GO, `AwaitingBudgetSignoff` with a real framework hash in the HITL-2 request.
- [ ] AC9 The signal bridge sends `revalidate` for protected profile changes only, `opportunity_amended` only with a non-empty mapped `affected`, skips closed workflows, and processes each event once.
- [ ] AC10 No adapter produces a money amount from LLM output (`hope_budget.numeric.find_raw_figures` over any text the adapters return is empty).

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/workflow/tests/test_adapters.py::test_real_registry_composition`, `::test_worker_agents_flag` | unit |
| AC2 | `test_adapters.py::test_context_loads_current_versions`, `::test_context_missing_is_non_retryable` | db |
| AC3 | `test_adapters.py::test_eligibility_mapping_and_event` | unit |
| AC4 | `test_adapters.py::test_alignment_uses_gateway`, `::test_alignment_invalid_output` | unit |
| AC5 | `test_adapters.py::test_recommend_single_row` | unit |
| AC6 | `test_adapters.py::test_budget_persists_atomically`, `::test_budget_drafted_by_go_decider` | db |
| AC7 | `test_adapters.py::test_verify_framework_checks` (parametrized) | unit |
| AC8 | `services/workflow/tests/test_lifecycle_real_agents.py::test_reaches_budget_signoff_with_real_agents` | unit (time-skipping) |
| AC9 | `services/workflow/tests/test_signal_bridge.py::test_profile_updated_protected_only`, `::test_amendment_area_mapping`, `::test_closed_workflow_skipped`, `::test_idempotent` | unit |
| AC10 | `test_adapters.py::test_no_llm_money` | unit |

Fixtures: `hope_core.testing.factories.agency_profile()` and `grant_opportunity()` with a
`funding.award_ceiling`; `hope_budget.testing.sample_context()` and
`InMemoryCostBasisResolver`; the MockProvider scripted with the matching judge and A7 structure
responses already used by `services/matching/tests` and `services/budget/tests`; an
`InMemoryPillar`. Commands: the CI commands in `AGENTS.md`.

## Out of scope

Real narrative, compliance, packaging and submission (S17, S19, S21, S22); portfolio re-ranking
(S05); real LLM providers (S16); deployment of the workers (S28).

## Decisions needed

- **Who is the budget "drafter" for separation of duties?** A7 drafts, but blueprint 4.4 means
  the person who owns the draft. Recommended: the HITL-1 GO decider (they own the pursuit),
  replaced by the last human editor once S06's line edits exist.
- **Default for `--agents`.** Recommended: `stub` locally and in CI, `real` in deployed
  environments via `HOPE_WORKFLOW_AGENTS=real` (S28).

## References

- `services/workflow/src/hope_workflow/{agents,stubs,worker,client,ports,activities}.py`
- `services/matching/src/hope_matching/{eligibility,alignment,recommender,agents}.py`
- `services/budget/src/hope_budget/{framework,engine,store,resolver,numeric}.py`
- `services/profile/src/hope_profile/{repository,contracts}.py`, `services/ingestion/src/hope_ingestion/contracts.py`
- Blueprint 2.2, 4.3 (global guards), 8.1 (no LLM money).
