# S04: Pursue, workflow list and history

| | |
|---|---|
| Wave | 1 |
| Depends on | S00 |
| Screens | SC07, SC08 (and the pursue call used by SC03 and SC04) |
| Migrations | `db/migrations/0610_workflow_transitions.sql` |
| Blueprint | 4.2, 4.3, 4.4, 7.3, 7.4 |
| Status | Draft |

## Goal

A user can start a pursuit of an opportunity in one click, see every workflow in flight
with where it is and what it waits on, and open a full, trustworthy history of one
workflow: every state transition, who or what caused it, and every gate decision. Today the
workflow runs in Temporal but nothing in the product can start it, and the screens are
built on a fixture and on `tenant_opportunity`, which only holds the latest state.

## Current state

- `hope_workflow.client.start_lifecycle(client, LifecycleInput)` starts
  `OpportunityLifecycleWorkflow` with the deterministic ID
  `opportunity-lifecycle:{tenant_id}:{agency_id}:{opportunity_id}`
  (`hope_workflow.workflow.lifecycle_workflow_id`) and `WorkflowIDConflictPolicy.USE_EXISTING`.
  Nothing calls it outside tests.
- On every transition the workflow (`OpportunityLifecycleWorkflow._set_state`) publishes
  `opportunity.state_changed` with payload `{"from": str, "to": str, "reason": str | None}`
  and upserts `tenant_opportunity` through `platform.mirror_state`
  (`hope_workflow.postgres.PostgresProjectionStore`). The previous states are not kept anywhere
  except Temporal history.
- `GET /v1/workflows/{workflow_id}` (pillar, moved to `hope_pillar/api/workflows.py` by S00)
  returns `WorkflowView` (`hope_pillar.api.models`): `workflow_id`, `opportunity_id`,
  `agency_id`, `state`, `updated_at`, `gates: GateView[]`, `timeline: TimelineEntry[]`
  (from `pillar_workflow_timeline`, written by `hope_pillar.projector.project`).
- There is no `GET /v1/workflows`. The web `HttpApi.listWorkflows()` derives the list from the
  matrix (`/agencies/{id}/matrix`, rows with a `workflow_id`), and `HttpApi.getWorkflow()` fakes
  `history` with one entry (`{from: null, to: state, actor: "pillar"}`).
- Web: `features/workflow/WorkflowScreen.tsx` (`WorkflowList`, `WorkflowDetail`),
  `features/workflow/Timeline.tsx` (`timelineSteps`, `Timeline`), `Timeline.test.tsx`;
  fixtures in `api/fixtures/workflows.ts` (`buildWorkflows`), which S00 moves to `api/workflow/`.

## Behaviour

### Pursue

1. `POST /v1/opportunities/{opportunity_id}/pursue` with `{"agency_id": "<uuid>"}`.
   The caller needs one of the roles `development_director`, `program_director`,
   `executive_director` (see Decisions needed), else `403 forbidden`.
2. Validate: the opportunity exists (`opportunities`) else `404 not_found`; the agency exists
   in this tenant (`agencies`, RLS) else `404 not_found`.
3. Look up `tenant_opportunity` for `(opportunity_id, agency_id)`:
   - row with a `workflow_id` and a non-terminal state (not in `hope_core.schemas.lifecycle.TERMINAL`)
     -> `409 already_pursuing` with `workflow_id` and `state` in the problem extras;
   - row with state `Ineligible` -> `422 ineligible` (the matrix is the source; S05 keeps it current);
   - row with a terminal state other than `Ineligible` (Declined, Expired, Archived, NotAwarded,
     Discarded) -> `409 workflow_closed` with `workflow_id` and `state`. Re-pursuing a closed
     opportunity is out of scope (Decisions needed).
4. The opportunity's `application_due` is in the past -> `422 deadline_passed`.
5. Start the workflow through `Services.workflows.start(LifecycleInput(tenant_id=HOPE_TENANT_ID,
   agency_id, opportunity_id))` (shared addition below; the default implementation calls
   `start_lifecycle`). The ID is deterministic, so a double click or a retry returns the same
   workflow. Temporal unreachable or timing out after 5 s -> `503 workflow_unavailable`;
   nothing is written.
6. In the request's tenant transaction, write `workflow.started`
   (`hope_core.schemas.WorkflowStarted`, S00) to the outbox with `trace.correlation_id =
   workflow_id`, and upsert `tenant_opportunity` with `state = 'Ingested'` only if no row exists
   (the workflow's own mirror overwrites it within seconds). Response `201` with the started
   workflow. If Temporal reports the workflow already existed (race with step 3), return `409
   already_pursuing` instead.
7. The LLM is not involved. Eligibility, deadlines and the transition are decided by code.

### Transition history

8. New consumer `hope_workflow.projection.TransitionProjector` (group `workflow-transitions`)
   subscribes to `opportunity.state_changed` and inserts one `workflow_transitions` row per
   event (`ON CONFLICT (event_id) DO NOTHING`, so redelivery is harmless). It runs as
   `python -m hope_workflow.projection` with the `hope_system` database URL.
9. The workflow publishes the payload as `OpportunityStateChanged` (shared addition) instead of
   the ad-hoc dict, adding `actor` (the decider's user id for gate decisions, the agent id such
   as `A4` for agent steps, `A0` for guards and timers), `gate`, `request_id` and `cause`.
   Old events without `actor` are projected with `actor = 'A0'`.
10. Rollbacks (revalidation, amendment) are recorded as transitions with `cause = "rollback"`
    and the reason, so history shows them even though they are not lifecycle edges.

### Reads

11. `GET /v1/workflows` lists `tenant_opportunity` rows with a `workflow_id`, joined to
    `opportunities` and to the open gate in `pillar_gate_requests`. Filters, sorting and paging
    are in Contracts. Any signed-in role can read.
12. `GET /v1/workflows/{workflow_id}` keeps every current field and adds `title`,
    `internal_deadline`, `application_due`, `funder_name`, `deadline_plan` and `transitions`.
13. `GET /v1/workflows/{workflow_id}/history` returns one merged, time-ordered feed of
    transitions, gate requests, gate decisions and other timeline events, paged by cursor.
14. A workflow ID that doesn't exist, or belongs to another tenant (RLS), returns `404 not_found`.

## Contracts

- **Shared models used:** `HitlRequest`, `HitlDecision`, `Gate` (`hope_core.schemas.hitl`),
  `OpportunityState`, `TERMINAL`, `assert_transition` (`hope_core.schemas.lifecycle`),
  `LifecycleInput`, `DeadlinePlan`, `Milestone` (`hope_core.schemas.workflow`, promoted by S00),
  `Problem` and the exceptions in `hope_core.errors` (S00), `Principal`, `require_roles`
  (`hope_core.auth`, S00).
- **Shared contract additions** (for S00 or C2, not this PR):
  - `hope_core.schemas.workflow.OpportunityStateChanged`:
    `from_state: OpportunityState | None`, `to_state: OpportunityState`,
    `cause: Literal["forward", "rollback", "guard"]`, `actor: str` ("user id or agent id"),
    `gate: Gate | None = None`, `request_id: UUID | None = None`, `reason: str | None = None`,
    `workflow_id: str`, `agency_id: UUID`. Serialized with aliases `from`/`to` for backward
    compatibility. `EVENT_TOPIC` already routes `opportunity.state_changed`.
  - `hope_workflow.workflow.OpportunityLifecycleWorkflow._set_state` publishes that model
    (the workflow file is edited by the contracts spec, not here).
  - `hope_pillar.api.deps.Services.workflows: WorkflowStarter`, a protocol
    `async def start(inp: LifecycleInput) -> StartResult` with
    `StartResult(workflow_id: str, created: bool)`; the default wraps
    `hope_workflow.client.connect` + `start_lifecycle`, and tests inject `FakeStarter`.
    This adds `hope-workflow` to `services/pillar/pyproject.toml`.
  - `WorkflowStarted` payload (S00 step 3) must carry `workflow_id`, `agency_id`,
    `opportunity_id`, `started_by`.
- **Events:** consumes `opportunity.state_changed` (topic `gop.opportunity.events`); produces
  `workflow.started` (topic per S00's `EVENT_TOPIC` entry; producer `pillar`; consumers: none yet,
  S31 may count it).
- **Endpoints** (router `hope_pillar/api/workflows.py`; all `application/json`, errors
  `application/problem+json`):

`POST /v1/opportunities/{opportunity_id}/pursue`. Roles: `development_director`,
`program_director`, `executive_director`. Body:

```json
{ "agency_id": "6f1c7d2e-1b8a-4f0e-9b1d-2a7c4e5f6a10" }
```

`201`:

```json
{
  "workflow_id": "opportunity-lifecycle:0b9e…:6f1c…:9a3e…",
  "opportunity_id": "9a3e5b21-77c4-4a0e-8f55-0d2f9c1e3b44",
  "agency_id": "6f1c7d2e-1b8a-4f0e-9b1d-2a7c4e5f6a10",
  "state": "Ingested",
  "started_at": "2026-11-07T15:04:05Z"
}
```

Errors: `403 forbidden`; `404 not_found`; `409 already_pursuing`
(`{"code": "already_pursuing", "workflow_id": "…", "state": "AwaitingGoNoGo"}`);
`409 workflow_closed` (same extras); `422 ineligible`; `422 deadline_passed`;
`422 validation_error`; `503 workflow_unavailable`.

`GET /v1/workflows`. Any role. Query: `agency_id` (uuid, optional; defaults to the one agency),
`state` (repeatable `OpportunityState`), `status` (`active` | `waiting` | `finished` | `all`,
default `active`; `waiting` = has an open gate, `finished` = terminal or `Submitted`),
`gate` (repeatable `Gate`), `q` (title contains, case-insensitive, max 100 chars),
`sort` (`deadline` default, `updated`, `title`), `cursor`, `limit` (1-200, default 50).

```json
{
  "items": [
    {
      "workflow_id": "opportunity-lifecycle:…",
      "opportunity_id": "9a3e…",
      "agency_id": "6f1c…",
      "title": "Rural Health Care Services Outreach Program",
      "funder_name": "HRSA",
      "state": "AwaitingGoNoGo",
      "internal_deadline": "2026-12-01T22:00:00Z",
      "application_due": "2026-12-04T22:00:00Z",
      "open_gate": {
        "request_id": "3d4a…",
        "gate": "HITL-1",
        "approver_roles": ["development_director"],
        "due_at": "2026-11-10T15:00:00Z",
        "escalated": false
      },
      "updated_at": "2026-11-07T14:58:00Z"
    }
  ],
  "total": 7,
  "counts": { "active": 6, "waiting": 5, "finished": 1 },
  "next_cursor": null
}
```

`counts` ignore `status` but respect the other filters. `funder_name` comes from
`opportunity_versions.normalized->'funder'->>'name'`. `escalated` is true when the latest gate
request for that gate was re-requested by the SLA timer (`pillar_gate_requests.summary` prefix is
not reliable, so the projector field is a shared addition: see Decisions needed).
Errors: `400 invalid_cursor`, `422 validation_error`.

`GET /v1/workflows/{workflow_id}`. Any role. The current `WorkflowView` plus:

```json
{
  "title": "Rural Health Care Services Outreach Program",
  "funder_name": "HRSA",
  "internal_deadline": "2026-12-01T22:00:00Z",
  "application_due": "2026-12-04T22:00:00Z",
  "deadline_plan": {
    "funder_timezone": "America/New_York",
    "buffer_hours": 72,
    "milestones": [
      { "name": "budget_signoff", "due_at": "2026-11-17T22:00:00Z", "owner_role": "finance_director", "gate": "HITL-2" }
    ]
  },
  "transitions": [
    { "event_id": "…", "from": "Recommended", "to": "AwaitingGoNoGo", "at": "2026-11-07T14:58:00Z",
      "actor": "A0", "cause": "forward", "gate": null, "reason": null }
  ]
}
```

`deadline_plan` is recomputed on read with `hope_workflow.deadlines.plan_deadlines(opportunity,
now)` (pure function; no Temporal query), so it is null when the opportunity has no deadline.
Errors: `404 not_found`.

`GET /v1/workflows/{workflow_id}/history`. Any role. Query: `cursor`, `limit` (1-200, default 100),
`kind` (repeatable: `transition`, `gate_requested`, `gate_decided`, `event`).

```json
{
  "items": [
    { "kind": "transition", "at": "2026-11-07T14:58:00Z", "event_id": "…",
      "from": "Recommended", "to": "AwaitingGoNoGo", "actor": "A0", "cause": "forward", "reason": null },
    { "kind": "gate_requested", "at": "2026-11-07T14:58:01Z", "request_id": "…", "gate": "HITL-1",
      "approver_roles": ["development_director"], "due_at": "2026-11-12T14:58:01Z",
      "artifact_hash": "sha256:…", "summary": "Go / No-Go: …", "status": "open" },
    { "kind": "gate_decided", "at": "2026-11-08T10:00:00Z", "request_id": "…", "gate": "HITL-1",
      "decision": "go", "decided_by": "u-dana", "comment": null },
    { "kind": "event", "at": "2026-11-07T14:58:02Z", "event_id": "…",
      "event_type": "notification.requested", "producer": "workflow" }
  ],
  "next_cursor": "eyJ…"
}
```

Ordering: `at` ascending, ties by `event_id`/`request_id`. Transitions come from
`workflow_transitions`; gates from `pillar_gate_requests`; events from `pillar_workflow_timeline`
excluding `opportunity.state_changed`, `hitl.requested` and `hitl.decided` (already shown as
richer items). Errors: `404 not_found`, `400 invalid_cursor`.

- **Database** (`0610_workflow_transitions.sql`):

```sql
CREATE TABLE workflow_transitions (
  event_id        uuid PRIMARY KEY,
  tenant_id       uuid NOT NULL REFERENCES tenants,
  workflow_id     text NOT NULL,
  opportunity_id  uuid NOT NULL REFERENCES opportunities,
  agency_id       uuid NOT NULL REFERENCES agencies,
  from_state      text,
  to_state        text NOT NULL,
  cause           text NOT NULL DEFAULT 'forward' CHECK (cause IN ('forward','rollback','guard')),
  actor           text NOT NULL,
  gate            text,
  request_id      uuid,
  reason          text,
  occurred_at     timestamptz NOT NULL
);
CREATE INDEX workflow_transitions_wf ON workflow_transitions (tenant_id, workflow_id, occurred_at);
CREATE TRIGGER workflow_transitions_append_only BEFORE UPDATE OR DELETE ON workflow_transitions
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
ALTER TABLE workflow_transitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_transitions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON workflow_transitions
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
CREATE INDEX tenant_opportunity_workflow ON tenant_opportunity (tenant_id, workflow_id);
```

## Owns

```text
services/pillar/src/hope_pillar/api/workflows.py
services/pillar/tests/test_workflows_api.py
services/pillar/tests/snapshots/openapi/workflows.json
services/workflow/src/hope_workflow/projection.py
services/workflow/tests/test_projection.py
db/migrations/0610_workflow_transitions.sql
apps/web/src/api/workflow/**
apps/web/src/features/workflow/**
apps/web/src/app/workflows/page.tsx
apps/web/src/app/workflows/[workflowId]/page.tsx
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 Pursue starts the lifecycle workflow with the deterministic ID and returns 201 with `workflow_id`; the outbox holds one `workflow.started` event in the same transaction.
- [ ] AC2 A second pursue for the same opportunity and agency returns `409 already_pursuing` with the existing `workflow_id`, and does not start a second workflow (including when two requests race).
- [ ] AC3 Pursue returns `422 ineligible` for an Ineligible row, `409 workflow_closed` for a terminal row, `422 deadline_passed` for a past deadline, and `404 not_found` for an unknown opportunity or agency.
- [ ] AC4 Pursue without an allowed role returns `403 forbidden`; Temporal unavailable returns `503 workflow_unavailable` and writes nothing.
- [ ] AC5 `TransitionProjector` writes one row per `opportunity.state_changed`, ignores redelivery, and maps legacy payloads (`from`/`to`/`reason`) with `actor = "A0"`.
- [ ] AC6 `workflow_transitions` rejects UPDATE and DELETE and is isolated by RLS.
- [ ] AC7 `GET /v1/workflows` filters by `state`, `status`, `gate`, `q`, sorts by `deadline` (nulls last), `updated` and `title`, pages with a stable cursor, and returns `total`, `counts` and `open_gate`.
- [ ] AC8 `GET /v1/workflows/{id}` returns the new fields, with `transitions` in order and a `deadline_plan` that matches `plan_deadlines`.
- [ ] AC9 `/history` merges transitions, gate requests, decisions and other events in time order, filters by `kind`, and pages without duplicates or gaps.
- [ ] AC10 A workflow of another tenant returns 404 on every read.
- [ ] AC11 The OpenAPI snapshot `openapi/workflows.json` matches.
- [ ] AC12 SC07 and SC08 meet their acceptance criteria.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/pillar/tests/test_workflows_api.py::test_pursue_starts_workflow_and_writes_event` | db |
| AC2 | `test_workflows_api.py::test_pursue_is_idempotent`, `::test_pursue_race_returns_already_pursuing` | db |
| AC3 | `test_workflows_api.py::test_pursue_rejections` (parametrized per code) | db |
| AC4 | `test_workflows_api.py::test_pursue_requires_role`, `::test_pursue_temporal_unavailable` | api |
| AC5 | `services/workflow/tests/test_projection.py::test_projects_transitions_idempotently`, `::test_legacy_payload` | db |
| AC6 | `test_projection.py::test_transitions_append_only_and_rls` | db |
| AC7 | `test_workflows_api.py::test_list_filters_sort_and_cursor` | db |
| AC8 | `test_workflows_api.py::test_get_workflow_adds_transitions_and_plan` | db |
| AC9 | `test_workflows_api.py::test_history_merged_and_paged` | db |
| AC10 | `test_workflows_api.py::test_other_tenant_not_found` | db |
| AC11 | `services/pillar/tests/test_openapi.py::test_router_snapshots` (S00) | api |
| AC12 | see SC07 and SC08 test plans | unit |

Fixtures: `hope_core.testing.factories.grant_opportunity()` with `application_due` 30 days
ahead; a `FakeStarter` that records calls and can raise `RPCError` (unavailable) or return
`created=False`; seeded `tenant_opportunity` rows in states `AwaitingGoNoGo`, `Ineligible`,
`Declined`. Commands: the CI commands in `AGENTS.md`.

## Out of scope

Re-pursuing a closed opportunity; cancelling or pausing a workflow; assigning an owner (HITL-1
GO details are S02's); the pursue button on SC03/SC04 (S05/S03 call `api.workflow.pursue`);
the audit panel data (S13).

## Decisions needed

- **Pursue roles.** SC03 says `program_director` and `executive_director`; the workflow's
  HITL-1 default role is `development_director` (`hope_workflow.policy.GATES`), and the web
  fixture session uses `development_director`. Recommended: accept all three until S01 fixes the
  role catalogue.
- **Re-pursue after Declined/Expired.** Recommended: not in the MVP (`409 workflow_closed`);
  later, start a new run with a `-r{n}` suffix.
- **`open_gate.escalated`.** `pillar_gate_requests` doesn't record escalations. Recommended:
  C2 adds `HitlRequest.escalated_from_role: str | None` and the projector column; until then
  S04 returns `escalated: false`.
- **422 code for request validation.** Recommended: S00's handler maps FastAPI's
  `RequestValidationError` to `validation_error`.

## References

- `services/workflow/src/hope_workflow/{client,workflow,deadlines,postgres}.py`
- `services/pillar/src/hope_pillar/api/{routes,models}.py`, `hope_pillar/projector.py`
- `db/migrations/0001_core.sql` (`tenant_opportunity`, `approvals`), `0100_pillar.sql`
- Blueprint 4.3 (state machine), 4.4 (gates), 7.3-7.4; `docs/specs/screens/SC03-opportunity-matrix.md` (pursue UX).
