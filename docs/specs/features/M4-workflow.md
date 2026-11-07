# M4: Workflow (hackathon)

| | |
|---|---|
| Wave | MVP (parallel with M1-M3, M5-M7, after M0) |
| Depends on | M0 |
| Screens | SC07 (workflows list), SC08 (workflow timeline); exports `pursue()` for SC03 (M2) |
| Migrations | `db/migrations/0610_workflow_runs.sql` (0610-0619 reserved) |
| Blueprint | 4.2, 4.3, 4.4, Appendix B |
| Replaces for the MVP | S04 + S07 (full drafts kept on `specs/workflow`) |
| Status | Draft |

## Goal

Pursue on the matrix starts a real, durable lifecycle workflow that drives one opportunity
from go/no-go to a downloadable package, using the real matching and budget code and the M0
ports for drafting and packaging. Every state change is stored, so the workflows list (SC07) and
the timeline (SC08) show exactly where each pursuit is, what it waits on, and what happened.
The demo path is: Pursue -> HITL-1 GO -> budget -> HITL-2 -> narrative -> HITL-4 -> package ->
HITL-5 -> Mark submitted.

## Current state

- `hope_workflow.workflow.OpportunityLifecycleWorkflow` (Temporal) already runs the whole
  lifecycle with `assert_transition`, HITL gates (signal `submit_decision`, SLA timers, hash
  binding, separation of duties), the deadline guard and the `revalidate` / `opportunity_amended`
  signals. Its start state is `Normalized`. Handlers per state are in `_drive()`; `Screened` goes
  to `Archived` when the recommendation is `skip`; `AwaitingCompliance` opens a HITL-3 gate;
  `AwaitingSubmissionAuth` calls the submit agent.
- Agents come from `hope_workflow.stubs.StubAgents.registry()` (all nine are stubs); context
  comes from `InMemoryContextSource` (factory samples); `PlatformActivities.publish` defaults to
  `InMemoryPillar`, so in a real run **no event reaches `pillar_gate_requests`**, and the approval
  inbox can't see any gate.
- `POST /v1/workflows/{workflow_id}/signals/{gate}` (in `api/workflows.py` after M0) validates the
  gate, inserts into `approvals`, marks the gate decided and publishes `hitl.decided`, but
  **nothing forwards the decision to Temporal**, and the workflow's own `record_approval` would
  insert a second `approvals` row. It refuses HITL-5 approvals (they went through
  `/packages/{id}/authorize`).
- `client.revalidate_signal` / `client.amendment_signal` assume payload shapes that don't match the
  real `ProfileUpdated` (`changes: list[FieldChange]`, `protected_changed`) and `OpportunityAmended`
  (`changes: list[FieldChange]`) payloads.
- There is no `GET /v1/workflows`; `GET /v1/workflows/{id}` has no title, history or artifact links.
- After M0: `Role` enum, `hope_core.auth`, `default_gateway()`, the ports
  `hope_drafting.ports.draft_sections`, `hope_packaging.ports.build_package`,
  `hope_budget.ports.compute_for_framework`, the renamed `EligibilityActivityResult` /
  `AlignmentActivityResult`, `apps/web/src/api/workflow/` and `make demo`.

## Behaviour

### How the demo runs

1. **Temporal is required; there is no in-process fallback.** `infra/docker-compose.yml` already
   has `temporal` (`temporalio/temporal:1.4.1`, `start-dev`, ports 7233/8233). `make demo` (M0)
   must start it and run `uv run python -m hope_workflow.worker --agents real --postgres`
   (Requests to M0). Reason: the workflow is already written and tested on Temporal; a second
   in-process engine would double the code paths a demo can break on. If Temporal is down, pursue
   returns `503 workflow_unavailable` and SC07/SC08 still render from Postgres.
2. **No Kafka needed.** In `--postgres` mode, `platform.publish` uses `PostgresPublisher`, which in
   one tenant transaction writes the envelope to `outbox` and applies the pillar projection
   (`project(cur, envelope)`, see Requests to M0), so `pillar_gate_requests` and
   `pillar_workflow_timeline` update immediately. The outbox rows stay unpublished unless the relay
   runs; nothing in the MVP consumes Kafka.

### Pursue

3. `POST /v1/opportunities/{opportunity_id}/pursue`, body `{}` (or `{"agency_id": "…"}`; it defaults
   to `HOPE_AGENCY_ID` and any other value returns `404 not_found`). Roles:
   `development_director`, `program_director`, `executive_director`; otherwise `403 forbidden`.
4. In one tenant transaction, under `pg_advisory_xact_lock(hashtext(workflow_id))`:
   1. opportunity missing -> `404 not_found`;
   2. a `workflow_runs` row exists for the opportunity and agency (any state) ->
      `409 already_pursuing` with `workflow_id` and `state`;
   3. run `hope_matching.eligibility.evaluate_eligibility(profile, opportunity)` (deterministic,
      no LLM, under 50 ms); `status == "ineligible"` -> `422 ineligible` with `failed_rules`;
   4. internal deadline (`hope_workflow.deadlines.plan_deadlines(...).internal_deadline`) already
      passed -> `422 deadline_passed`;
   5. start the workflow with `hope_workflow.client.start_lifecycle` (deterministic ID
      `opportunity-lifecycle:{tenant}:{agency}:{opportunity}`, `USE_EXISTING`, 5 s timeout) with
      `LifecycleInput(..., pursued=True, small_org_ack=settings.small_org_ack, started_by=user_id)`;
      Temporal error -> roll back, `503 workflow_unavailable`;
   6. insert `workflow_runs` (`started_by`, `started_at`) and upsert `tenant_opportunity`
      (`state = 'Normalized'`, `workflow_id`) if the workflow hasn't mirrored yet.
   Response `201 {"workflow_id": "…"}`.
5. `pursued=True` (new `LifecycleInput` field): a human chose this opportunity, so `Screened` always
   goes to `Recommended`; the A6 recommendation is kept on the row but never archives a pursuit.

### Real agents (replacing the stubs)

6. `hope_workflow.adapters.real_registry(deps)` builds the `AgentRegistry`; the worker flag
   `--agents real|stub` (default `stub`; `make demo` passes `real`) selects it. `deps.gateway =
   default_gateway()`; when it is the mock (no `HOPE_OPENAI_API_KEY`), `adapters.offline` registers
   deterministic responders (`JudgeSample` from `hope_matching.testing.scores_judge(78.0)`, the A7
   `FrameworkStructure` from the budget sample lines) so the demo also runs offline.
7. **Context:** `PostgresContextSource` loads the current profile (`ProfileRepository.current`) and
   the current opportunity version (`opportunity_versions.normalized`). Missing -> non-retryable
   `ApplicationError(type="not_found")`.
8. **Eligibility / alignment / recommend (A4-A6):** `evaluate_eligibility`, `assess_alignment`,
   `build_matrix` (single row), mapped to `EligibilityActivityResult` (`status`, `reasons =
   failed_rules + review_rules`, `effort_hours = effort.hours`) and `AlignmentActivityResult`.
   Invalid model output after the gateway's retries -> non-retryable `model_output_invalid`.
9. **Budget (A7 + M5):** `FrameworkGenerator(gateway, InMemoryCostBasisResolver(demo basis)).draft(...)`,
   insert `frameworks` (`status='draft'`, next `version`), then
   `ledger = hope_budget.ports.compute_for_framework(framework_id)` (M5 persists and returns it).
   `BudgetDraft.drafted_by` = the HITL-1 GO decider. HITL-2 `artifact_hash = ledger.content_hash`,
   `summary` "Budget sign-off: {total} request, {n} lines, all cap checks pass" (amount formatted from
   the ledger, never from the LLM). On HITL-2 approve, `frameworks.status = 'approved_locked'`.
10. **Verify:** framework: passes when every `cap_checks[].ok` and `content_hash` matches; narrative:
    passes when every section has a non-empty `body_md` and
    `hope_budget.numeric.find_raw_figures(body_md)` is empty (money comes only from placeholders).
11. **Narrative (M6):** `hope_drafting.ports.draft_sections(framework, opportunity, profile, ledger)`;
    `narrative_hash = content_hash([s.content_hash for s in sections])`. HITL-4 `artifact_hash =
    content_hash({framework, narrative_hash})`.
12. **Compliance (MVP):** no HITL-3. The compliance step is a deterministic check (`required
    sections present`, from `opportunity.requirements`); pass -> `AwaitingCompliance ->
    AwaitingExecApproval` with reason "Compliance checks passed (no HITL-3 in the MVP)"; fail ->
    back to `Drafting` with the missing section names as feedback.
13. **Package (M7):** `hope_packaging.ports.build_package(framework_id) -> PackageManifest`; HITL-5
    request with `package_id = manifest.package_id`, `artifact_hash = manifest.content_hash`.
14. **Submission (MVP, manual):** HITL-5 approve does not submit anything. The workflow stays in
    `AwaitingSubmissionAuth` with the gate passed, and waits for the `mark_submitted` signal
    (`MarkSubmitted(submitted_by, confirmation, submitted_at)`), sent by
    `POST /v1/workflows/{id}/mark-submitted`. Then `AwaitingSubmissionAuth -> Submitted` and the
    workflow completes. The submit agent and `SubmissionError` path are not used in the MVP.
15. Timeouts: agent activities `start_to_close` 2 min (LLM steps 5 min), the existing `RETRY`
    policy; SLA timers as today (they only matter if the demo sits for days).

### Decisions from the UI

16. `POST /v1/workflows/{workflow_id}/signals/{gate}` (owned here; M3's SC06 and M5's SC13 call it):
    lock the open gate row; role in `approver_roles` else `403 forbidden`; `artifact_hash` differs
    -> `409 stale_artifact` with `current_hash`; gate not open -> `409 gate_closed`. Then signal
    `submit_decision(HitlDecision(..., role=<acting role>))` to Temporal (5 s timeout, `503
    workflow_unavailable` on failure, nothing written), and mark the gate row `decided`. The
    `approvals` row is written **only** by the workflow's `record_approval` activity (no duplicate).
    HITL-5 approvals are accepted here in the MVP. `202` with `request_id`, `decision`.
17. If the workflow rejects a decision (separation of duties, or the hash changed between the check
    and the signal), it re-requests the gate with a new `request_id` and notifies; SC08 shows the new
    open gate.
18. `POST /v1/workflows/{workflow_id}/mark-submitted`, role `aor`, body `{"confirmation": "GRANT1234567",
    "submitted_at": "2026-11-08T16:00:00Z"}` (both optional, `submitted_at` defaults to now and can't be
    in the future). Requires state `AwaitingSubmissionAuth` with a decided HITL-5 `approve`, else
    `409 not_authorized`. Signals `mark_submitted`; `202`.

### History

19. `platform.mirror_state` takes a `StateChange` (`ProjectionRow` + `from_state`, `actor`, `cause`
    (`forward | rollback | guard`), `gate`, `request_id`, `reason`) and in one transaction upserts
    `tenant_opportunity`, updates `workflow_runs` (state, artifact ids) and inserts one
    `workflow_transitions` row (`event_id` = the `opportunity.state_changed` event id, so retries are
    idempotent). `actor` is the decider's user id for gate outcomes, `A4`/`A5`/`A6`/`A7`/`A9`/`A10`
    for agent steps, `A0` for guards and timers.
20. Revalidation / amendment: the workflow keeps both signals; `client.revalidate_signal` and
    `client.amendment_signal` are fixed to parse `ProfileUpdated` and `OpportunityAmended`
    (`changes[].path` mapped to areas). No consumer forwards those events in the MVP (out of scope).
21. Single tenant: every query runs in `tenant_tx(conn, HOPE_TENANT_ID)`; no tenant in any request.
22. LLMs are only called inside matching, budget and drafting through `ModelGateway.structured`;
    the workflow's control flow, gates, amounts and dates are code.

## Contracts

- **Shared models used:** `HitlRequest`, `HitlDecision` (with M0's `role`), `Gate`,
  `OpportunityState`, `TERMINAL`, `assert_transition`, `AgencyProfile`, `GrantOpportunity`,
  `MatrixRow`, `ProposalFramework`, `BudgetLedger`, `NarrativeSection`, `PackageManifest`,
  `EligibilityResult`, `AlignmentAssessment` (`hope_core.schemas.matching`), `Role`, `Principal`,
  `require_roles` (`hope_core.auth`), `StaleArtifactError` and the problem+json errors.
- **Service-local models (`hope_workflow.contracts`):** `LifecycleInput` gains `pursued: bool =
  False`, `started_by: str | None = None`; new `StateChange`, `MarkSubmitted`; `NotificationRequest`,
  `DeadlinePlan`, `Milestone` unchanged.
- **Events:** produces `opportunity.state_changed` (payload now includes `actor`, `cause`, `gate`,
  `request_id`), `hitl.requested`, `hitl.decided`, `notification.requested`; all with
  `trace.correlation_id = workflow_id`, written to `outbox` and projected in-transaction.
- **Endpoints** (router `hope_pillar/api/workflows.py`; errors are `application/problem+json`):

`POST /v1/opportunities/{opportunity_id}/pursue` -> `201`

```json
{ "workflow_id": "opportunity-lifecycle:0b9e1c2d-…:6f1c7d2e-…:9a3e5b21-…" }
```

Errors: `403 forbidden`; `404 not_found`; `409 already_pursuing`
`{"type": "about:blank", "title": "Already pursuing", "status": 409, "code": "already_pursuing",
"workflow_id": "opportunity-lifecycle:…", "state": "AwaitingGoNoGo"}`; `422 ineligible`
`{"code": "ineligible", "failed_rules": ["applicant_type", "geography"]}`; `422 deadline_passed`
`{"code": "deadline_passed", "internal_deadline": "2026-11-05T22:00:00Z"}`; `503 workflow_unavailable`.

`GET /v1/workflows?status=active|waiting|finished|all&state=<OpportunityState>` (any role; default
`status=active`; `waiting` = has an open gate; `finished` = terminal or `Submitted`; at most 200
items, no paging in the MVP) -> `200`

```json
{
  "items": [
    {
      "workflow_id": "opportunity-lifecycle:…",
      "opportunity_id": "9a3e5b21-77c4-4a0e-8f55-0d2f9c1e3b44",
      "title": "Rural Health Care Services Outreach Program",
      "funder_name": "Health Resources and Services Administration",
      "state": "AwaitingBudgetSignoff",
      "internal_deadline": "2026-12-01T22:00:00Z",
      "application_due": "2026-12-04T22:00:00Z",
      "open_gate": {
        "request_id": "3d4a6a5e-2b9c-4c41-8f0e-9a7e1b2c3d02",
        "gate": "HITL-2",
        "approver_roles": ["finance_director"],
        "due_at": "2026-11-10T15:00:00Z"
      },
      "busy": false,
      "started_by": "demo",
      "updated_at": "2026-11-07T15:12:44Z"
    }
  ],
  "counts": { "active": 3, "waiting": 2, "finished": 3 }
}
```

`busy` = active, not terminal, and no open gate (an agent step is running). Sort: open gate `due_at`
ascending, then `internal_deadline` ascending (nulls last), then `updated_at` desc.
Errors: `422 validation_error` (unknown `status`/`state`).

`GET /v1/workflows/{workflow_id}` (any role) -> `200`: today's `WorkflowView` (`workflow_id`,
`opportunity_id`, `agency_id`, `state`, `updated_at`, `gates[]`, `timeline[]`) plus:

```json
{
  "title": "Rural Health Care Services Outreach Program",
  "funder_name": "Health Resources and Services Administration",
  "internal_deadline": "2026-12-01T22:00:00Z",
  "application_due": "2026-12-04T22:00:00Z",
  "busy": true,
  "started_by": "demo",
  "started_at": "2026-11-07T15:04:05Z",
  "artifacts": {
    "framework_id": "c7d1…",
    "ledger_id": "ledger-…",
    "narrative_hash": null,
    "package_id": null
  },
  "submission": null,
  "deadline_plan": {
    "funder_timezone": "America/New_York",
    "buffer_hours": 72,
    "milestones": [
      { "name": "budget_signoff", "due_at": "2026-11-17T22:00:00Z", "owner_role": "finance_director", "gate": "HITL-2" }
    ]
  },
  "transitions": [
    { "event_id": "…", "from": "Normalized", "to": "Screened", "at": "2026-11-07T15:04:09Z",
      "actor": "A4", "cause": "forward", "gate": null, "reason": "eligible" }
  ]
}
```

`submission` after Mark submitted: `{"submitted_at": "…", "submitted_by": "demo", "confirmation":
"GRANT1234567"}`. `deadline_plan` is computed on read with `plan_deadlines(opportunity, now)`.
Errors: `404 not_found`.

`GET /v1/workflows/{workflow_id}/history` (any role) -> `200`, ascending by `at`:

```json
{
  "items": [
    { "kind": "transition", "at": "2026-11-07T15:04:12Z", "from": "Recommended", "to": "AwaitingGoNoGo",
      "actor": "A0", "cause": "forward", "reason": null },
    { "kind": "gate_requested", "at": "2026-11-07T15:04:12Z", "request_id": "…", "gate": "HITL-1",
      "approver_roles": ["development_director", "executive_director"], "due_at": "2026-11-12T15:04:12Z",
      "summary": "Go / No-Go: score 78, $300,000 ceiling, ~120 h" },
    { "kind": "gate_decided", "at": "2026-11-07T15:06:30Z", "request_id": "…", "gate": "HITL-1",
      "decision": "go", "decided_by": "demo", "role": "development_director", "comment": null },
    { "kind": "approval_invalidated", "at": "…", "gate": "HITL-2", "reason": "profile financials changed" }
  ]
}
```

Sources: `workflow_transitions`, `pillar_gate_requests`, `approvals` (decisions with `role`, and
`decision = 'invalidated'` rows). Errors: `404 not_found`.

`POST /v1/workflows/{workflow_id}/signals/{gate}` body `{"decision": "approve", "artifact_hash":
"sha256:…", "comment": null, "role": "finance_director"}` (`role` optional: defaults to the first
principal role in `approver_roles`) -> `202 {"request_id": "…", "decision": "approve"}`. Errors:
`403 forbidden`, `404 not_found`, `409 stale_artifact` (`current_hash`), `409 gate_closed`,
`503 workflow_unavailable`.

`POST /v1/workflows/{workflow_id}/mark-submitted` -> `202 {"workflow_id": "…", "state":
"AwaitingSubmissionAuth"}` (the state changes to `Submitted` within a second). Errors: `403
forbidden`, `404 not_found`, `409 not_authorized`, `422 validation_error`, `503 workflow_unavailable`.

- **Database** (`0610_workflow_runs.sql`, RLS `tenant_isolation` like `0001_core.sql`):

```sql
CREATE TABLE workflow_runs (
  workflow_id     text PRIMARY KEY,
  tenant_id       uuid NOT NULL REFERENCES tenants,
  opportunity_id  uuid NOT NULL REFERENCES opportunities,
  agency_id       uuid NOT NULL REFERENCES agencies,
  state           text NOT NULL,
  started_by      text NOT NULL,
  started_at      timestamptz NOT NULL DEFAULT now(),
  framework_id    uuid,
  ledger_id       text,
  narrative_hash  text,
  package_id      uuid,
  submitted_at    timestamptz,
  submitted_by    text,
  confirmation    text,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, opportunity_id, agency_id)
);
CREATE TABLE workflow_transitions (
  event_id     uuid PRIMARY KEY,
  tenant_id    uuid NOT NULL REFERENCES tenants,
  workflow_id  text NOT NULL REFERENCES workflow_runs,
  from_state   text,
  to_state     text NOT NULL,
  cause        text NOT NULL CHECK (cause IN ('forward','rollback','guard')),
  actor        text NOT NULL,
  gate         text,
  request_id   uuid,
  reason       text,
  occurred_at  timestamptz NOT NULL
);
CREATE INDEX workflow_transitions_wf ON workflow_transitions (tenant_id, workflow_id, occurred_at);
CREATE TRIGGER workflow_transitions_append_only BEFORE UPDATE OR DELETE ON workflow_transitions
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
```

- **Settings** (`hope_workflow.settings.WorkflowSettings`, prefix `HOPE_`): `workflow_agents`
  (`stub | real`, default `stub`), `small_org_ack` (bool, default `false`; `true` in the demo env).

### Demo seed (`hope_workflow.demo.seed()`)

Idempotent (fixed UUIDs, `ON CONFLICT DO NOTHING`), runs as `hope_system`, needs no Temporal. It
seeds three **finished** pursuits so SC07/SC08 look real before the live run; the live demo pursues a
fresh opportunity from the matrix.

| Seeded workflow | Opportunity (seeded by this module, `source_system = 'demo'`) | Final state | History |
|---|---|---|---|
| `opportunity-lifecycle:{t}:{a}:00000000-0000-4000-8000-000000000401` | "Community Health Workers for Public Health Response" (CDC, due 2026-09-30) | `Submitted` | full happy path, 16 transitions, HITL-1/2/4/5 approved by `demo`, confirmation `GRANT1442017` |
| `…:00000000-0000-4000-8000-000000000402` | "Rural Communities Opioid Response Program" (HRSA, due 2026-10-15) | `Declined` | to HITL-1, `no_go` "Outside our service area" |
| `…:00000000-0000-4000-8000-000000000403` | "Community Facilities Direct Loan and Grant Program" (USDA, due 2026-12-20) | `Ineligible` | `Normalized -> Ineligible`, reason "applicant_type" |

Rows: `opportunities` + `opportunity_versions` (built with `hope_core.testing.factories.grant_opportunity`),
`workflow_runs`, `tenant_opportunity`, `workflow_transitions` (timestamps spaced 26 h apart ending
3 days ago), `pillar_gate_requests` (decided) and `approvals`.

## Owns

```text
services/workflow/**   (incl. src/hope_workflow/{adapters/**,settings.py,demo.py}, tests/**, pyproject.toml)
db/migrations/0610_workflow_runs.sql
services/pillar/src/hope_pillar/api/workflows.py
services/pillar/tests/snapshots/openapi/workflows.json
apps/web/src/features/workflow/**
apps/web/src/api/workflow/**
apps/web/src/app/workflows/**
```

API tests for the router live in `services/workflow/tests/test_workflows_api.py` (they build the
pillar app with `create_app(services=...)` and a fake Temporal client), so no pillar test file is
touched.

## Acceptance criteria

- [ ] AC1 Pursue returns 201 `{workflow_id}` with the deterministic ID, starts exactly one Temporal workflow, and writes `workflow_runs` and `tenant_opportunity`.
- [ ] AC2 A second pursue (also concurrent) returns `409 already_pursuing` with the existing `workflow_id` and `state`.
- [ ] AC3 Pursue returns `422 ineligible` (with `failed_rules`), `422 deadline_passed`, `404 not_found`, `403 forbidden` for a role outside the three, and `503 workflow_unavailable` (nothing written) when Temporal is down.
- [ ] AC4 With real adapters (MockProvider responders) in the time-skipping environment, a pursued opportunity reaches `AwaitingGoNoGo` with a real `MatrixRow`, and after GO reaches `AwaitingBudgetSignoff` with `artifact_hash == ledger.content_hash`.
- [ ] AC5 The full MVP path runs end to end in the time-skipping environment: GO, HITL-2, (no HITL-3), HITL-4, package, HITL-5, `mark_submitted` -> `Submitted`; every transition passes `assert_transition`.
- [ ] AC6 A pursued opportunity with a `skip` recommendation still goes to `Recommended`.
- [ ] AC7 Narrative verification fails a section with a raw money figure and sends the workflow back to `Drafting` with feedback.
- [ ] AC8 `PostgresPublisher` writes the outbox row and the gate projection in one transaction; a `hitl.requested` is visible in `pillar_gate_requests` without Kafka.
- [ ] AC9 The signal endpoint enforces role, open gate and hash (`409 stale_artifact` with `current_hash`), forwards the decision to Temporal, and leaves exactly one `approvals` row per decision.
- [ ] AC10 `mark-submitted` requires `aor` and an approved HITL-5 (`409 not_authorized` otherwise) and moves the workflow to `Submitted`.
- [ ] AC11 Every state change inserts one `workflow_transitions` row with the right `actor` and `cause`, idempotently; the table rejects UPDATE/DELETE.
- [ ] AC12 `GET /v1/workflows` filters by `status`/`state`, sorts as specified and returns `counts`, `open_gate` and `busy`; `GET /v1/workflows/{id}` returns `artifacts`, `submission`, `deadline_plan` and `transitions`; `/history` merges transitions, gate requests, decisions and invalidations in order; unknown ids return 404.
- [ ] AC13 `revalidate_signal` / `amendment_signal` parse the real `ProfileUpdated` / `OpportunityAmended` payloads.
- [ ] AC14 `seed()` is idempotent and creates the three finished pursuits with their histories.
- [ ] AC15 The OpenAPI snapshot `openapi/workflows.json` matches; all existing workflow tests still pass.
- [ ] AC16 SC07 and SC08 meet their acceptance criteria.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/workflow/tests/test_workflows_api.py::test_pursue_starts_workflow` | db |
| AC2 | `test_workflows_api.py::test_pursue_already_pursuing`, `::test_pursue_concurrent` | db |
| AC3 | `test_workflows_api.py::test_pursue_errors` (parametrized: ineligible, deadline_passed, not_found, forbidden, unavailable) | db |
| AC4 | `services/workflow/tests/test_adapters.py::test_real_agents_reach_budget_signoff` | unit (time-skipping) |
| AC5 | `services/workflow/tests/test_lifecycle_mvp.py::test_mvp_happy_path_to_submitted` | unit (time-skipping) |
| AC6 | `test_lifecycle_mvp.py::test_pursued_skip_still_recommended` | unit (time-skipping) |
| AC7 | `test_adapters.py::test_narrative_verify_rejects_raw_money` | unit |
| AC8 | `services/workflow/tests/test_postgres.py::test_publisher_projects_in_transaction` | db |
| AC9 | `test_workflows_api.py::test_signal_checks_and_forwards`, `::test_single_approval_row` | db |
| AC10 | `test_workflows_api.py::test_mark_submitted` | db |
| AC11 | `test_postgres.py::test_transitions_recorded_idempotently`, `::test_transitions_append_only` | db |
| AC12 | `test_workflows_api.py::test_list_workflows`, `::test_get_workflow_detail`, `::test_history_merged`, `::test_unknown_workflow_404` | db |
| AC13 | `services/workflow/tests/test_client.py::test_real_payload_shapes` | unit |
| AC14 | `services/workflow/tests/test_demo.py::test_seed_idempotent` | db |
| AC15 | `services/workflow/tests/test_workflows_api.py::test_openapi_snapshot`, existing suite | api |
| AC16 | see SC07 and SC08 | unit |

Offline only: `MockProvider` with the `adapters.offline` responders; a `FakeTemporal` (records
`start_workflow` and `signal` calls, can raise `RPCError`). DB tests use `pytest.mark.db` like today.
Commands: the CI commands in `AGENTS.md`.

## Requests to M0

1. `make demo` starts the `temporal` compose service, waits for port 7233, and runs
   `uv run python -m hope_workflow.worker --agents real --postgres` with `HOPE_SMALL_ORG_ACK=true`.
2. Move the pure projection function `hope_pillar.projector.project(cur, envelope)` to
   `hope_core.projection.project` (no behaviour change; `hope_pillar.projector` imports it), so the
   workflow can project in-transaction without depending on `hope_pillar`. If declined, `make demo`
   must also run Redpanda, `hope-pillar-relay` and `hope-pillar-projector`.
3. Add `hope-workflow` to `services/pillar/pyproject.toml` (the router starts and signals workflows
   through `hope_workflow.client`). `hope_workflow` never imports `hope_pillar`, so there is no cycle.
4. The demo principal has `mfa=true` by default (HITL-2 and HITL-5 require step-up MFA in the signal
   endpoint).
5. Pin the port semantics: `compute_for_framework` persists the ledger and returns it (M5);
   `build_package` persists the package and returns its manifest (M7).
6. `NotificationRequest` is service-local and stays in `hope_workflow.contracts`; nothing to promote.

## Coordination with other MVP specs

- **M2 (SC03)** calls `api.workflow.pursue(opportunityId)` and handles `already_pursuing`,
  `ineligible` and also `deadline_passed` ("The internal deadline for this opportunity has passed.")
  and `workflow_unavailable` ("Hope's workflow engine isn't running. Try again in a minute."). SC03
  lists Pursue roles `program_director` and `executive_director`; this spec also allows
  `development_director` (the HITL-1 approver).
- **M3 (SC06)** and **M5 (SC13)** submit decisions with `POST /v1/workflows/{id}/signals/{gate}`;
  HITL-5 approvals go through it too in the MVP.
- **M7 (SC22)** "Mark submitted" calls `POST /v1/workflows/{id}/mark-submitted` (new endpoint, owned here).

## Out of scope

HITL-3, real portal submission and `SubmissionError` retries, notification delivery, the
profile/amendment event bridge, re-pursuing a closed opportunity, paging, audit trail, cancelling a
workflow.

## Decisions needed

- **Temporal in the demo.** Recommended: required, no fallback (see Behaviour 1).
- **Separation of duties in the demo.** There is one demo user, so the HITL-2 drafter rule would block
  the demo. Recommended: `HOPE_SMALL_ORG_ACK=true` in the demo env only; the rule stays on by default.
- **HITL-3.** Recommended: skipped in the MVP with an explicit transition reason.
- **Pursue roles.** Recommended: `development_director`, `program_director`, `executive_director`.

## References

- `services/workflow/src/hope_workflow/{workflow,agents,stubs,activities,client,deadlines,postgres,worker}.py`
- `services/pillar/src/hope_pillar/api/routes.py` (`signal_gate`, `_decide`, `get_workflow`), `hope_pillar/projector.py`
- `services/matching/src/hope_matching/{eligibility,alignment,recommender,testing}.py`, `services/budget/src/hope_budget/{framework,numeric}.py`
- `docs/specs/features/M0-mvp-scaffolding.md`, `docs/specs/screens/SC03-opportunity-matrix.md`; full versions: `S04`, `S07` on this branch.
