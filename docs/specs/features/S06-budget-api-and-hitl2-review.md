# S06: Budget API and HITL-2 budget review

> **Out of scope for the hackathon. Don't build this.** This spec belongs to the earlier design (the Phase 1 pipeline and the M0-M7 / S-spec roadmap). Hackathon agents build only H0-H5 (see [`README.md`](../README.md)). Keep this file for after the hackathon.

| | |
|---|---|
| Wave | 1 |
| Depends on | S00 |
| Screens | SC13 |
| Migrations | `db/migrations/0510_budget_api.sql` |
| Blueprint | 2.2 A7, 4.4 (HITL-2), 5.4, 8.1 |
| Status | Draft |

## Goal

Finance reviews, edits and signs off a grant budget in Hope. Every figure comes from the
deterministic Budget Engine (`hope_budget`). A reviewer can change a line's structure
(quantity, effort, funding source, add or remove a line). They can never type an amount.
The engine recomputes, and the HITL-2 approval is bound to the exact framework hash.
This spec persists frameworks and cost-basis records and serves the budget API that SC13
uses. It also consumes `framework.recompute_requested` and locks the framework when HITL-2
is approved.

## Current state

On `main` (after S00):

- **Engine.** `services/budget/src/hope_budget/`:
  - `engine.py`: `BudgetEngine(ctx).compute(lines) -> BudgetLedger` (sealed: `ledger_id` =
    `content_hash`). Also `validate()`, `ProposedLine`, `BudgetContext`, `BudgetInputError`,
    `seal()`, `is_sealed()`.
  - `solver.py`: `fit_budget(lines, ctx, policy) -> BudgetSolution`.
  - `framework.py`: `FrameworkGenerator.draft()` and `drafted_envelope()`.
  - `numeric.py`: the reconciler.
  - `store.py`: `save_ledger()` / `load_ledger()`.
  - `resolver.py`: `CostBasisResolver` protocol and `InMemoryCostBasisResolver` (the only implementation).
- **Contracts.** S00 promotes `CostBasisRecord` and the numeric report models to
  `hope_core.schemas.budget`, and adds `BudgetLedger.content_hash` and
  `ProposalFramework.drafted_by`.
- **Tables.** `db/migrations/0001_core.sql` has `frameworks` and `budget_ledgers`, both
  under RLS. `0500_budget_ledgers_immutable.sql` makes ledgers append-only with
  `ledger_id = content_hash`. Nothing writes `frameworks` today. There is no cost-basis
  table, so the engine can only run in tests.
- **Pillar.**
  - `GET /v1/frameworks/{framework_id}` is built. After S00 it lives in
    `services/pillar/src/hope_pillar/api/frameworks.py` and returns `FrameworkView` with
    `ledgers[]` from `hope_pillar.api.models`.
  - After S00, `POST /v1/frameworks/{id}/recompute` returns 202 and writes
    `framework.recompute_requested` to the outbox. It has no consumer.
- **Workflow.**
  - `hope_workflow.workflow.LifecycleWorkflow._budget_signoff` opens HITL-2 with
    `artifact_hash = framework.content_hash` and forbids `drafted_by` as the approver
    unless `small_org_ack`.
  - On `approve` it sets the in-workflow copy to `approved_locked`.
  - On any other decision it returns to `Planning` with the comment as feedback.
- **Web.** `apps/web/src/app/frameworks/[frameworkId]/budget/page.tsx` is an S00
  `ComingSoon` placeholder.

## Behaviour

### Cost basis (the only source of rates)

1. **Store.** `hope_budget/cost_basis.py` adds `PostgresCostBasisResolver(cur)`, which
   implements `CostBasisResolver`:
   - `resolve(ref)` returns the active row for `ref` as a `CostBasisRecord`, or `None`.
   - `catalog()` returns every active record, ordered by `ref`.
2. **Writes.** `upsert_cost_basis(cur, record, actor) -> CostBasisVersion`.
   - Inserts a new version and deactivates the previous active row, in one transaction.
   - A record whose fields are identical to the active row (compared by `content_hash`) is
     a no-op that returns the existing version.
   - A record without `provenance` raises `BudgetInputError(["cost basis {ref} has no provenance"])`.
   - `deactivate_cost_basis(cur, ref, actor)` marks the active row inactive.
3. **Ref namespaces.**
   - `erp:` refs are reserved for the ERP sync (S25).
   - The API may write any other ref (`hris:`, `quote:`, `manual:`). A manual write always
     stores `provenance.source = "user_input"`, `verified_by = <user_id>`, `captured_at = now()`.

### Framework persistence

4. **Repository.** `hope_budget/repository.py`:
   - `save_framework(cur, framework, proposed_lines, actor) -> ProposalFramework`:
     1. Computes `framework.content_hash` (`framework_hash()`) and checks that
        `framework.budget` is sealed (`LedgerIntegrityError` otherwise).
     2. Writes the ledger via `store.save_ledger`.
     3. Inserts a `frameworks` row with `version = max(version)+1` for
        `(opportunity_id, agency_id)`, `status='draft'`, and `framework` JSON that holds
        `extra.proposed_lines` (the `ProposedLine` list, needed to recompute or edit later).
     4. Marks the previous non-superseded row `status='superseded'` and sets its
        `superseded_by`.
     5. Writes `framework.drafted` via `hope_core.outbox.write_event`, using
        `drafted_envelope()` with `trace.correlation_id = workflow_id` when known.

     All of this is one `tenant_tx`. Each version gets a new `framework_id`
     (`frameworks.framework_id` is the primary key; the lineage key is
     `(opportunity_id, agency_id)`).
   - `load_framework(cur, framework_id) -> StoredFramework | None` returns the row, the
     parsed `ProposalFramework`, `proposed_lines`, `superseded_by` and `workflow_id`.
   - `current_framework(cur, opportunity_id, agency_id)`.
5. **Drafting entry point for S07.** `hope_budget/service.py` provides
   `BudgetService.draft(tx, opportunity, profile, workflow_id, drafted_by) -> FrameworkDraft`.
   1. Builds the resolver from `PostgresCostBasisResolver`.
   2. Calls `FrameworkGenerator.draft()`.
   3. Sets `drafted_by` and calls `save_framework`.

   S07's budget adapter calls this; S06 does not touch `services/workflow`.

### Reading the budget

6. `GET /v1/frameworks/{framework_id}/budget` returns `BudgetView` (shape below). It joins:
   - the framework row;
   - the ledger;
   - the cost-basis record behind every ref used, with its provenance. A ref that no longer
     resolves is listed in `missing_refs[]`;
   - `rates_changed[]`: lines whose stored `basis.unit_rate_minor` differs from the active
     record's rate;
   - the solver block from `framework.extra.solver`;
   - the open HITL-2 gate from `pillar_gate_requests` (`workflow_id` + gate `HITL-2` +
     `status='open'`; the `workflow_id` comes from `tenant_opportunity`);
   - the latest row in `budget_recompute_requests`;
   - a short opportunity summary (title, funder name, award ceiling and floor,
     `application_due`).

   It also computes `permissions` for the caller (step 9).

   A superseded framework still returns 200 with `status: "superseded"` and
   `superseded_by`, so the screen can redirect.

### Editing lines (HITL-2 "request changes (inline)")

7. `PUT /v1/frameworks/{framework_id}/budget/lines` with `BudgetLinesEdit`. The steps run in order:
   1. Load and `SELECT … FOR UPDATE` the framework row. If it is missing, return 404 `not_found`.
   2. If the status is `approved_locked`, return 409 `framework_locked`.
   3. If the status is `superseded`, or `base_hash != content_hash`, return 409
      `stale_artifact` with `current_hash` and `current_framework_id`.
   4. If the lifecycle state (`tenant_opportunity.state` for the workflow) is not
      `Planning` or `AwaitingBudgetSignoff`, return 409 `invalid_state` with `state`.
   5. If the caller's roles don't include one of `BUDGET_EDIT_ROLES =
      {"finance_director", "cfo", "development_director"}`, return 403 `forbidden`.
   6. Validate the body. `BudgetLineEdit` has no `unit_rate_minor` or `amount_minor` field
      and `extra="forbid"`, so any amount or rate field is a 422 (FastAPI validation,
      `code: "validation_error"`).
   7. Build the `BudgetContext`: `PostgresCostBasisResolver`, `AgencyRates.from_profile`
      of the current profile version, and `BudgetRules.from_funding` of the current
      opportunity version. `periods` uses the same rule as `FrameworkGenerator.draft`.
   8. `BudgetEngine(ctx).validate(lines)`. Any errors return 422 `budget_input_invalid`
      with `errors: [{line_id | null, message}]`. A message is attributed to a `line_id`
      when it starts with `line <id>:`.
   9. Compute. If `fit` is false, use `BudgetEngine.compute(lines)`; human edits are never
      silently changed. If `fit` is true, run `fit_budget(lines, ctx)`, with every line the
      user touched in this edit treated as `locked=True`.
   10. If the new ledger's `ledger_id` equals the current ledger's and the lines are
       identical, return 200 with the current `BudgetView` and `changed: false`. No new
       version is written.
   11. Otherwise build version n+1 with `status="draft"`, the same scope,
       `budget = new ledger`, `extra.solver` (from the fit or empty), and
       `drafted_by = caller.user_id`. Then call `save_framework`.
   12. Write an `audit_log` row:
       - `action = "budget.lines_edited"`;
       - `subject = framework:{new_id}`;
       - `detail = {previous_framework_id, previous_hash, new_hash, changed_line_ids}`.
   13. Return 200 `BudgetView` of the new version with `changed: true`.

   The open HITL-2 gate still carries the old hash, so it can no longer be approved
   (the pillar returns 409 `stale_artifact`). Re-opening it is a workflow change; see
   "Shared contract additions".

   The editor becomes the drafter, so they cannot approve HITL-2 unless `small_org_ack` is set.

### Recompute

8. The consumer `hope_budget.recompute.RecomputeConsumer` runs as consumer group
   `budget-recompute` on `Topic.AGENT_COMMANDS`, event `framework.recompute_requested`.
   1. It is idempotent via `processed_events`.
   2. It reloads the framework and its `proposed_lines`, and recomputes with current rates,
      profile and opportunity (`compute`, no solver).
   3. It updates the `budget_recompute_requests` row:
      - unchanged ledger: `status="unchanged"`;
      - changed ledger: a new version, written as in step 7 with
        `drafted_by = framework.drafted_by` so a system recompute does not change the
        drafter, and `status="new_version"` with `new_framework_id`;
      - a locked framework: `status="rejected"` with `errors=["framework is approved_locked"]`;
      - `BudgetInputError`: `status="failed"` with `errors`.

     The row is inserted with `status="pending"` by the consumer when it first sees the
     event (keyed by `event_id`).

### HITL-2 lock

9. **Permissions** in `BudgetView.permissions`:
   - `can_edit`: step 7 checks 2, 4 and 5 pass.
   - `can_decide`: there is an open gate, the caller has one of its `approver_roles`, and
     the caller is not `drafted_by` (unless the workflow's `small_org_ack`; S06 reads it
     from `tenant_opportunity` if S04 exposes it, see Decisions).
   - `decide_blocked_reason`: one of `"no_open_gate" | "not_an_approver" | "you_drafted_this" | null`.
   - `requires_step_up: true` (HITL-2 is in `STEP_UP_MFA_GATES`).
10. **Lock consumer.** `hope_budget.lock.LockConsumer` runs as consumer group `budget-lock`
    on `hitl.decided`, for gate `HITL-2` and decision `approve`.
    - It finds the framework whose `content_hash == decision.artifact_hash`, sets
      `status='approved_locked'`, and appends an `Approval` (gate, approver, `approved_hash`, `at`).
    - It writes `framework.locked` with the locked `ProposalFramework` as payload. The lock
      changes status only: `content_hash` stays the approved hash, as in the workflow.
    - No match, or a match that is superseded: log `budget.lock_skipped` to `audit_log` and do nothing.
    - It is idempotent.
11. **Tenancy.** Every read and write goes through `tenant_tx` with `HOPE_TENANT_ID`, and
    RLS applies to every new table. No endpoint takes a tenant.
12. **LLM.** None of these endpoints calls a model. Editing and recompute are pure engine work.

## Contracts

- **Shared models used:**
  - `hope_core.schemas.proposal_framework`: `ProposalFramework`, `BudgetLedger`,
    `LineItem`, `LineItemBasis`, `CapCheck`, `Approval`.
  - `hope_core.schemas.budget`: `CostBasisRecord` (from S00).
  - `hope_core.schemas.hitl`: `Gate`, `HitlDecision`.
  - `Provenance`, `Money`, `PillarEnvelope`, `EventType.FRAMEWORK_DRAFTED / FRAMEWORK_LOCKED / FRAMEWORK_RECOMPUTE_REQUESTED`.
- **Service-local models**: `ProposedLine` (already in `hope_budget.engine`).
  - `hope_budget/api_models.py`: `BudgetView`, `BudgetLineEdit`, `BudgetLinesEdit`,
    `CostBasisView`, `CostBasisWrite`.
  - `hope_budget/repository.py`: `StoredFramework`.

  The pillar imports these from `hope_budget`. They are endpoint shapes, not shared contracts.
- **Shared contract additions** (for C2, or S00 if it hasn't merged):
  1. `HitlRequest.artifact_ref: str | None = None`: "what the hash refers to, e.g.
     `framework:{uuid}`". SC05 and SC06 need it to link a HITL-2 request to `/frameworks/{id}/budget`.
  2. **Workflow (S07, or the wave-2 workflow owner).** When `framework.drafted` arrives for
     a workflow in `AwaitingBudgetSignoff` with a different `content_hash`:
     - supersede the open HITL-2 request (`pillar_gate_requests.status='superseded'`);
     - run verification on the new framework;
     - re-open HITL-2 with the new hash and `drafted_by` from the new framework.

     In `Planning`, the next produce/verify loop uses the stored current framework instead
     of calling A7 again.
  3. `hope_pillar` depends on `hope-budget` (`services/pillar/pyproject.toml` and `uv.lock`).
  4. Problem codes added to `apps/web/src/lib/problem.ts`: `framework_locked`,
     `budget_input_invalid`, `invalid_state`.
  5. `FrameworkRecomputeRequested` payload (S00 creates it): `framework_id: UUID`,
     `requested_by: str`, `reason: str | None`. If S00 names it differently, S06 follows S00.
- **Events**

| Event | Topic | Payload | Producer | Consumers |
|---|---|---|---|---|
| `framework.drafted` | `gop.agent.results` | `ProposalFramework` | S06 (`save_framework`) | workflow (S07), S18 |
| `framework.recompute_requested` | `gop.agent.commands` | `FrameworkRecomputeRequested` | pillar (S00) | S06 `RecomputeConsumer` |
| `framework.locked` | `gop.opportunity.events` | `ProposalFramework` | S06 `LockConsumer` | S17, S19, S21 |
| `hitl.decided` | `gop.hitl.events` | `HitlDecision` | pillar | S06 `LockConsumer` (HITL-2 only) |

### Endpoints

All of these live in `services/pillar/src/hope_pillar/api/frameworks.py` under `/v1`.
Auth uses `hope_core.auth.get_principal`; dev uses `X-Hope-User` / `X-Hope-Roles`. Errors are
`application/problem+json` (`hope_core.errors.Problem`).

**`GET /v1/frameworks/{framework_id}/budget`**
- Roles: any signed-in user.
- Responses: 200 `BudgetView`; 404 `not_found`.

```json
{
  "framework_id": "6f1c2b9e-1d1a-4c55-9a51-2f0c8f1e7a10",
  "version": 2,
  "status": "draft",
  "content_hash": "sha256:4b1e…",
  "superseded_by": null,
  "drafted_by": "user-maria",
  "project_title": "Mentor Futures Expansion",
  "opportunity": {
    "opportunity_id": "0d0b7c8e-…",
    "title": "Youth Mentoring Expansion",
    "funder_name": "DOJ OJJDP",
    "award_ceiling": {"amount_minor": 10000000, "currency": "USD"},
    "award_floor": null,
    "application_due": "2026-12-03T23:59:00-05:00"
  },
  "workflow": {"workflow_id": "wf-0d0b7c8e", "state": "AwaitingBudgetSignoff"},
  "ledger": { "…": "BudgetLedger, sealed" },
  "proposed_lines": [
    {"line_id": "L1", "category": "personnel", "description": "Program manager", "period": 1,
     "basis": {"cost_basis_ref": "hris:position:PM-02", "quantity": "1", "effort_pct_bps": 5000},
     "funding_source": "request", "justification": "Leads the expansion", "locked": false,
     "min_effort_bps": 2500, "min_quantity": null, "quantity_step": null}
  ],
  "sources": [
    {"ref": "hris:position:PM-02", "kind": "salary", "description": "Program Manager II",
     "unit": "year", "unit_rate": {"amount_minor": 6500000, "currency": "USD"},
     "fringe_rate_bps": null, "version": 3,
     "provenance": {"source": "user_input", "source_ref": null, "captured_at": "2026-11-02T14:00:00Z",
                    "verified_by": "user-dana", "confidence": null}}
  ],
  "missing_refs": [],
  "rates_changed": [],
  "solver": {"feasible": true, "unresolved": [], "adjustments": []},
  "gate": {"request_id": "9a7e…", "status": "open", "artifact_hash": "sha256:4b1e…",
           "approver_roles": ["finance_director"], "due_at": "2026-11-10T17:00:00Z",
           "requested_at": "2026-11-07T17:00:00Z"},
  "last_recompute": {"requested_at": "2026-11-07T16:58:00Z", "status": "unchanged",
                     "new_framework_id": null, "errors": []},
  "permissions": {"can_edit": true, "can_decide": false,
                  "decide_blocked_reason": "you_drafted_this", "requires_step_up": true},
  "changed": null
}
```

**`PUT /v1/frameworks/{framework_id}/budget/lines`**
- Roles: `BUDGET_EDIT_ROLES`.
- Body (`BudgetLinesEdit`):

```json
{
  "base_hash": "sha256:4b1e…",
  "fit": false,
  "lines": [
    {"line_id": "L1", "category": "personnel", "description": "Program manager", "period": 1,
     "cost_basis_ref": "hris:position:PM-02", "quantity": "1", "effort_pct_bps": 4000,
     "funding_source": "request", "justification": "Leads the expansion", "locked": true}
  ],
  "comment": "Reduce PM effort to fit the ceiling"
}
```

  - `lines` is the full desired set of direct lines. Fringe and indirect are always derived.
  - `BudgetLineEdit` fields: `line_id`, `category` (`DirectCategory`), `description?`,
    `period` (>=1), `cost_basis_ref`, `quantity` (decimal string), `effort_pct_bps?`,
    `funding_source`, `justification?` (<= 2000 chars), `locked` (default false),
    `min_effort_bps?`, `min_quantity?`, `quantity_step?`.
  - `extra="forbid"`; `lines` holds 1 to 200 items; `comment` is <= 2000 chars.
- Responses:
  - 200 `BudgetView` (`changed: true|false`).
  - 403 `forbidden`.
  - 404 `not_found`.
  - 409 `stale_artifact` (`current_hash`, `current_framework_id`).
  - 409 `framework_locked`.
  - 409 `invalid_state` (`state`).
  - 422 `budget_input_invalid`:

```json
{"type": "about:blank", "title": "Budget input invalid", "status": 422, "code": "budget_input_invalid",
 "errors": [{"line_id": "L4", "message": "line L4: cost_basis_ref quote:Q-9 does not resolve"},
            {"line_id": null, "message": "agency fringe rate is missing"}]}
```

**`POST /v1/frameworks/{framework_id}/recompute`**
- Built by S00 (202). S06 only changes the response body to
  `{"request_id": "<event_id>", "status": "pending"}`.
- Roles: `BUDGET_EDIT_ROLES`.
- Errors: 409 `framework_locked`, 404 `not_found`.

**`GET /v1/cost-basis`** (new, see Catalog changes)
- Roles: any signed-in user.
- Query: `ref_prefix?`, `kind?`.
- 200: `{"items": [CostBasisView]}`. `CostBasisView` = `CostBasisRecord` + `version`, `active`, `updated_at`.

**`PUT /v1/cost-basis/{ref}`** (new)
- Roles: `finance_director`, `cfo`.
- Body `CostBasisWrite`:
  `{"kind": "salary", "description": "Program Manager II", "unit": "year",
  "unit_rate": {"amount_minor": 6500000, "currency": "USD"}, "fringe_rate_bps": null,
  "subaward_id": null, "cost_tags": [], "source_ref": "HR salary bands 2026.pdf"}`.
  The server sets `provenance`.
- Responses:
  - 200 `CostBasisView` (existing ref), 201 (new ref).
  - 422 `reserved_ref` (an `erp:` prefix).
  - 422 `validation_error` (negative rate, or a currency other than the agency budget currency).
  - 403 `forbidden`.
- The ref path segment is URL-encoded and must match `^[a-z]+:[A-Za-z0-9:._-]{1,120}$`.

### Database: `db/migrations/0510_budget_api.sql`

```sql
CREATE TABLE cost_basis_records (
  record_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants,
  ref           text NOT NULL,
  version       int  NOT NULL,
  record        jsonb NOT NULL,             -- CostBasisRecord
  content_hash  text NOT NULL,
  source        text NOT NULL,              -- provenance.source
  active        boolean NOT NULL DEFAULT true,
  created_by    text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, ref, version),
  CHECK (record ? 'provenance' AND record->'provenance' IS NOT NULL AND record->'provenance' <> 'null'::jsonb)
);
CREATE UNIQUE INDEX cost_basis_one_active ON cost_basis_records (tenant_id, ref) WHERE active;

ALTER TABLE frameworks ADD COLUMN superseded_by uuid REFERENCES frameworks;
ALTER TABLE frameworks ADD COLUMN drafted_by text;
CREATE UNIQUE INDEX frameworks_one_current ON frameworks (tenant_id, opportunity_id, agency_id)
  WHERE status <> 'superseded';

CREATE TABLE budget_recompute_requests (
  event_id          uuid PRIMARY KEY,
  tenant_id         uuid NOT NULL REFERENCES tenants,
  framework_id      uuid NOT NULL REFERENCES frameworks,
  requested_by      text NOT NULL,
  requested_at      timestamptz NOT NULL DEFAULT now(),
  status            text NOT NULL CHECK (status IN ('pending','unchanged','new_version','failed','rejected')),
  new_framework_id  uuid REFERENCES frameworks,
  errors            jsonb NOT NULL DEFAULT '[]',
  finished_at       timestamptz
);
CREATE INDEX budget_recompute_by_framework ON budget_recompute_requests (tenant_id, framework_id, requested_at DESC);
```

- RLS: enable and force `tenant_isolation` (`tenant_id = current_tenant()`) on
  `cost_basis_records` and `budget_recompute_requests`, with the same `DO $$` loop as
  `0300_profile.sql`.
- Grants: `SELECT, INSERT, UPDATE` to `hope_app` and `hope_system`. No `DELETE`.
- A trigger forbids `UPDATE` on `cost_basis_records`, except `active` going from true to false.

## Owns

```text
services/budget/src/hope_budget/cost_basis.py
services/budget/src/hope_budget/repository.py
services/budget/src/hope_budget/service.py
services/budget/src/hope_budget/recompute.py
services/budget/src/hope_budget/lock.py
services/budget/src/hope_budget/api_models.py
services/budget/src/hope_budget/testing.py
services/budget/tests/test_cost_basis_store.py
services/budget/tests/test_repository.py
services/budget/tests/test_edit.py
services/budget/tests/test_recompute.py
services/budget/tests/test_lock.py
services/pillar/src/hope_pillar/api/frameworks.py
services/pillar/tests/test_frameworks_api.py
services/pillar/tests/snapshots/openapi/frameworks.json
apps/web/src/features/budget/**
apps/web/src/api/budget/**
apps/web/src/app/frameworks/[frameworkId]/budget/page.tsx
db/migrations/0510_budget_api.sql
docs/specs/README.md (S06 status row only)
```

## Acceptance criteria

- [ ] AC1 `PostgresCostBasisResolver.resolve` returns the active version; an upsert with changed fields creates version n+1 and deactivates n; an identical upsert is a no-op.
- [ ] AC2 A cost-basis record without provenance is rejected in code (`BudgetInputError`) and by the table `CHECK`.
- [ ] AC3 RLS: records and recompute requests of another tenant are invisible.
- [ ] AC4 `save_framework` writes the ledger, the framework at version n+1, supersedes version n, and writes `framework.drafted` in one transaction (a forced failure leaves none of them).
- [ ] AC5 `BudgetService.draft` persists the A7 draft with `drafted_by` and `extra.proposed_lines` (MockProvider).
- [ ] AC6 `GET …/budget` returns every field in the example, including `sources` with provenance, the open gate, `rates_changed` when a rate changed after compute, and `missing_refs` when a ref was deactivated.
- [ ] AC7 `PUT …/budget/lines` recomputes through the engine and returns a new version with a new `content_hash` and `drafted_by` = the editor; an identical edit returns `changed: false` with no new row.
- [ ] AC8 A body with `amount_minor` or `unit_rate_minor` on a line is rejected with 422 and nothing is written.
- [ ] AC9 Stale `base_hash` -> 409 `stale_artifact` with `current_hash`; locked -> 409 `framework_locked`; wrong state -> 409 `invalid_state`; missing role -> 403.
- [ ] AC10 Engine validation errors -> 422 `budget_input_invalid` with each message attributed to its `line_id`.
- [ ] AC11 `fit: true` runs the solver and never changes a line the user edited in this request.
- [ ] AC12 After an edit, a HITL-2 signal with the old hash returns 409 `stale_artifact` (existing pillar check).
- [ ] AC13 The recompute consumer records `unchanged`, `new_version`, `failed` or `rejected` correctly and is idempotent on a replayed event.
- [ ] AC14 The lock consumer locks only the framework whose hash matches an approved HITL-2 decision, emits `framework.locked`, and skips superseded or unmatched hashes with an audit entry.
- [ ] AC15 `permissions` is correct for: an approver who is not the drafter; the drafter; a non-approver; no open gate.
- [ ] AC16 `PUT /v1/cost-basis/{ref}` stores `user_input` provenance with `verified_by`, rejects `erp:` refs with 422 `reserved_ref`, and requires the finance roles.
- [ ] AC17 Every budget number in every response equals the engine's output (golden fixture from `hope_budget.testing`).
- [ ] AC18 SC13 acceptance criteria pass (see `screens/SC13-budget-review.md`).
- [ ] AC19 All CI commands in `AGENTS.md` pass, and the `frameworks.json` OpenAPI snapshot is updated.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/budget/tests/test_cost_basis_store.py::test_upsert_versions_and_noop` | db |
| AC2 | `test_cost_basis_store.py::test_provenance_required` | db |
| AC3 | `test_cost_basis_store.py::test_rls_isolation` | db |
| AC4 | `services/budget/tests/test_repository.py::test_save_framework_atomic` | db |
| AC5 | `services/budget/tests/test_repository.py::test_service_draft_persists` | db |
| AC6 | `services/pillar/tests/test_frameworks_api.py::test_get_budget_view` | api |
| AC7 | `services/budget/tests/test_edit.py::test_edit_creates_version`, `::test_identical_edit_unchanged` | db |
| AC8 | `services/pillar/tests/test_frameworks_api.py::test_amount_fields_rejected` | api |
| AC9 | `test_frameworks_api.py::test_edit_conflicts` (parametrized: stale, locked, state, role) | api |
| AC10 | `test_frameworks_api.py::test_budget_input_invalid` | api |
| AC11 | `services/budget/tests/test_edit.py::test_fit_respects_edited_lines` | unit |
| AC12 | `test_frameworks_api.py::test_old_hash_signal_is_stale` | api |
| AC13 | `services/budget/tests/test_recompute.py::test_recompute_outcomes`, `::test_replay_idempotent` | db |
| AC14 | `services/budget/tests/test_lock.py::test_lock_on_approve`, `::test_skip_stale_hash` | db |
| AC15 | `test_frameworks_api.py::test_permissions_matrix` | api |
| AC16 | `test_frameworks_api.py::test_cost_basis_write` | api |
| AC17 | `services/budget/tests/test_edit.py::test_golden_view_numbers` | unit |
| AC18 | see SC13 test plan | unit |
| AC19 | CI | ci |

Commands: the CI commands in `AGENTS.md`, plus `UPDATE_SNAPSHOTS=1 uv run pytest services/pillar/tests/test_openapi.py`
whenever a route changes.

## Out of scope

- HRIS/payroll connectors (positions still come from manual entry).
- ERP sync (S25).
- Narrative placeholders (S17) and verification (S18).
- Multi-currency budgets.
- Category caps and period caps (the `CapRule` values exist but have no grantor input yet).
- Changing the scope (goals, KPIs) from SC13.
- Re-opening the HITL-2 gate inside the workflow (shared addition 2).

## Decisions needed

1. **Versioning model.** Recommended default: every edit is a new `frameworks` row with a
   new `framework_id`, linked by `superseded_by`. The alternative (one id with a version
   column as part of the key) would mean changing the primary key and the
   `budget_ledgers.framework_id` foreign key.
2. **Who may edit lines.** Recommended default: `finance_director`, `cfo`,
   `development_director`. Role names are final once S01 merges.
3. **`small_org_ack` visibility.** S06 needs it for `permissions.can_decide`. Recommended
   default: read it from the workflow input via S04's projection
   (`tenant_opportunity.small_org_ack`). Until then, treat it as false; the workflow still
   enforces the rule.
4. **Rate changes after HITL-2 is opened.** Recommended default: no automatic recompute.
   SC13 shows `rates_changed`, and the reviewer chooses Recompute.
5. **CFO threshold** ("CFO for asks above a threshold", blueprint 4.4). Recommended
   default: out of scope; the workflow policy already escalates to `cfo` on timeout.

## References

- `services/budget/src/hope_budget/{engine,solver,framework,store,numeric}.py`
- `services/workflow/src/hope_workflow/workflow.py` (`_plan_budget`, `_budget_signoff`), `policy.py` (HITL-2 roles)
- `services/pillar/src/hope_pillar/api/routes.py` (`_lock_gate`, `_decide`, `get_framework`), now split by S00
- `db/migrations/0001_core.sql`, `0100_pillar.sql`, `0500_budget_ledgers_immutable.sql`
- Blueprint 2.2 A7, 4.4, 5.4, 8.1; 2 CFR 200.1 (MTDC), 200.414 (indirect)
