# M3: Approvals (hackathon MVP)

| | |
|---|---|
| Wave | MVP (runs in parallel with M1, M2, M4-M7 after M0) |
| Depends on | M0 |
| Screens | [SC05](../screens/SC05-approval-inbox.md) (inbox), [SC06](../screens/SC06-approval-detail.md) (decision) |
| Migrations | `0110-0119` reserved; **none used** (the existing `pillar_gate_requests` projection is the read model) |
| Blueprint | 4.4 (HITL gates, gate mechanics), 7.4 (pillar API), 8.4 (step-up MFA) |
| Replaces for the MVP | S02 (full version kept on `specs/web` for later) |
| Status | Draft |

## Goal

In the demo, every human decision on the way from "Pursue" to a downloadable package happens
in one place: the approver (picked with M0's role switcher) opens the **Approval Inbox**, sees
what is waiting on their role, opens one request, reviews a short preview of the exact
artifact, and records a decision that is bound to that artifact's hash. MVP gates:
**HITL-1** go/no-go, **HITL-2** budget sign-off, **HITL-4** executive approval,
**HITL-5** submission authorization (which, in the MVP, only unlocks M7's download and
"Mark submitted"; nothing is sent to a funder).

## Current state (main + M0)

- **Read model.** `db/migrations/0100_pillar.sql::pillar_gate_requests` (`request_id`, `tenant_id`,
  `workflow_id`, `subject_id` = opportunity id, `gate`, `artifact_hash`, `approver_roles text[]`,
  `due_at`, `summary`, `payload_ref`, `status` `open|decided|superseded`, `decision`, `decided_by`,
  `requested_at`, `decided_at`), one open row per workflow and gate (`pillar_gate_one_open`).
  `services/pillar/src/hope_pillar/projector.py::project` fills it from `hitl.requested`
  (superseding the previous open row) and `hitl.decided`.
- **Decisions today.** `POST /v1/workflows/{workflow_id}/signals/{gate}` and
  `POST /v1/packages/{package_id}/authorize` (after M0: `api/workflows.py`, owned by M4, and
  `api/packages.py`, owned by M7). Their helpers `_lock_gate` / `_decide` check approver role, step-up
  MFA (`STEP_UP_MFA_GATES` = HITL-2, HITL-3, HITL-5), open status, and hash (409); `_decide` writes
  `approvals` (append-only), updates the projection row and publishes `hitl.decided` through the
  outbox. HITL-5 approve is refused on the signals route. `_decide` does **not** set the deciding role.
- **Workflow side.** `services/workflow/src/hope_workflow/workflow.py::ApplicationWorkflow._gate`
  waits for a `HitlDecision`; `_invalid` rejects it when `d.details.get("role")` is not in
  `approver_roles`, when `decided_by` drafted the budget (HITL-2 separation of duties unless
  `WorkflowInput.small_org_ack`), or when the option is not in `policy.GATES[gate].options`. A rejected
  decision only produces a `hitl_rejected` notification; the API caller never hears about it.
- **Options** (`hope_workflow.policy.GATES`): HITL-1 `go, defer, no_go`; HITL-2 and HITL-4
  `approve, request_changes, reject`; HITL-5 `approve, defer`. `hope_pillar` does not depend on
  `hope_workflow`.
- **M0 gives:** `hope_core.auth` (`Principal`, `get_principal`, `Role` enum: `development_director`,
  `program_director`, `finance_director`, `executive_director`, `aor`, `admin`), demo user with all
  roles when no headers are sent, the role switcher (sends `X-Hope-Roles`), problem+json errors with
  `stale_artifact` + `current_hash`, `HitlDecision.role`, `HitlRequest.package_id`,
  `ProposalFramework.drafted_by`, an empty mounted `api/approvals.py`, the per-feature web client
  folder `apps/web/src/api/approvals/`, and a `ComingSoon` placeholder at `/approvals/[requestId]`.
- **Web today.** `apps/web/src/features/approvals/` (`ApprovalInbox.tsx` with inline decisions,
  `RequestCard.tsx`, `StepUpDialog.tsx`, tests). The HTTP client fans out over matrix rows and
  `GET /v1/workflows/{id}` to build the inbox.

## Behaviour

### Read: `GET /v1/approvals`

1. Any principal may list (single tenant; RLS via `tenant_tx`; `tenant_id` from `HOPE_TENANT_ID`).
2. Query: `status` = `open` (default) | `decided` | `all`; `gate` (repeatable; one of the
   four MVP gates, anything else -> 422 `validation_error`); `assignee=me` (rows whose
   `approver_roles` overlap the principal's roles; empty `approver_roles` counts as everyone's);
   `opportunity_id` (UUID); `limit` 1-100, default 50. No cursor in the MVP (D4).
3. Only MVP gates are returned (`gate IN ('HITL-1','HITL-2','HITL-4','HITL-5')`). `superseded`
   rows are never listed; they appear only in a detail's `history`.
4. Order: open -> `due_at ASC NULLS LAST, requested_at ASC`; decided/all -> `coalesce(decided_at, requested_at) DESC`.
5. Joins: `tenant_opportunity` on `workflow_id` (for `internal_deadline`, `state`) and
   `opportunities` on `subject_id::uuid` (for `title`). Missing joins give `null`s, never a 500.
6. Computed per item: `overdue` (`open` and `due_at < now()`), `can_decide` (`open` and role
   overlap), `step_up_required` (gate is HITL-2 or HITL-5), `acting_role` (the first of
   `approver_roles` the principal holds, else `null`).
7. `counts` uses the same `gate`/`assignee`/`opportunity_id` filters, ignores `status` and
   `limit`, and covers open rows only: `{open, overdue, by_gate: {"HITL-1": n, "HITL-2": n, "HITL-4": n, "HITL-5": n}}`
   (all four keys always present).

### Read: `GET /v1/approvals/{request_id}`

8. 404 `not_found` if the id is not a projection row of an MVP gate.
9. Returns the list item plus `options` (with labels; see the table), `preview` (built only from
   stored rows, never an LLM call), `history` (other rows for the same workflow and gate, newest
   first, max 10) and `approvals` (rows of the `approvals` table for that workflow and gate).

| Gate | `options` (`decision` / `label` / `tone` / `requires_comment`) | `preview.kind` and source |
|---|---|---|
| HITL-1 | `go` "GO" primary no; `defer` "Defer" neutral no; `no_go` "NO-GO" danger **yes** | `opportunity`: `tenant_opportunity` (`composite_score`, `recommendation`, `internal_deadline`) + latest `opportunity_versions.normalized` (`funder.agency_name`, `funding.award_ceiling`, `deadlines.application_due`); `links.opportunity = /opportunities/{id}` |
| HITL-2 | `approve` "Approve and lock" primary no; `request_changes` "Request changes" neutral **yes**; `reject` "Reject" danger **yes** | `budget`: `frameworks` row with `content_hash = artifact_hash`; from `framework->'budget'`: `totals` (all `*_minor`), `periods`, `cap_checks[]` (`rule`, `status`); `indirect_rate_bps` = `round(indirect_minor * 10000 / mtdc_base_minor)` (null when the base is 0); `drafted_by`; `missing: true` and nulls when no row matches; `links.budget = /frameworks/{id}/budget` |
| HITL-4 | `approve` "Approve" primary no; `request_changes` "Request changes" neutral **yes**; `reject` "Reject" danger **yes** | `draft`: latest `frameworks` row for the opportunity: `framework_id`, `project_title` (`scope.project_title`), `request_minor`, `approvals[]` (`gate`, `approver_user_id`, `at`); `links.draft = /frameworks/{id}/draft` |
| HITL-5 | `approve` "Authorize submission" primary no; `defer` "Hold" neutral **yes** | `package`: `package_id` (`HitlRequest.package_id`, stored in `payload_ref` as `package:{uuid}` until the projection has a column; see Requests to M0), `links.package = /packages/{package_id}` |

### Write: `POST /v1/approvals/{request_id}/decision`

10. Body `{decision, artifact_hash, comment?, role?}`. In one `tenant_tx`, in this order:
    1. Lock the row (`SELECT … FOR UPDATE`); none -> 404 `not_found`.
    2. `status != 'open'` -> 409 `gate_closed` (extras `status`, `decision`, `decided_by`, `decided_at`).
    3. Role: `role` if given (must be held by the principal and be in `approver_roles`), else
       `acting_role`; none -> 403 `approver_role_required` (extras `approver_roles`).
    4. Step-up: HITL-2 / HITL-5 without `principal.mfa` -> 403 `step_up_required`.
    5. `decision` not in the gate's options -> 422 `decision_not_allowed` (extras `options`).
    6. `requires_comment` and blank `comment` -> 422 `comment_required`.
    7. HITL-2 separation of duties: if the matching framework's `drafted_by` equals
       `principal.user_id` -> 403 `separation_of_duties`. (The workflow would silently reject it.)
    8. `artifact_hash != row.artifact_hash` -> 409 `stale_artifact` with `current_hash` (M0's error).
    9. Write: insert into `approvals` (`gate`, `decision`, `artifact_hash`, `decided_by`,
       `decided_at`, `comment`), set the row `decided`, and publish `hitl.decided` through the
       existing `tx.publish` (outbox) with a `HitlDecision` carrying `role` **and**
       `details={"role": role}` (what today's workflow `_invalid` reads), `trace.correlation_id = workflow_id`.
11. 202 response with the decision and `next` (where the UI goes: HITL-5 approve ->
    `/packages/{package_id}`; otherwise `/approvals`).
12. HITL-5 here records the AOR authorization only. It never calls `route_outbound` (no real
    submission in the MVP); M7's package screen reads the decided HITL-5 row to unlock download
    and "Mark submitted".
13. Idempotency: a retry after success gets 409 `gate_closed` whose extras show the same
    decision by the same user; the web treats that as success (SC06 interaction 4).
14. The LLM plays no part in any of these endpoints.

### Demo seed (`services/pillar/src/hope_pillar/demo.py:seed()`)

15. Idempotent (fixed `uuid5(NAMESPACE_URL, "hope-demo/approvals/<key>")` ids, `ON CONFLICT DO NOTHING`).
    Creates, for the M0 tenant and agency, four demo opportunities (rows in `opportunities`,
    `opportunity_versions`, `tenant_opportunity` with `workflow_id = demo-wf-<key>`), two
    `frameworks` rows, and these `pillar_gate_requests` (times relative to seed time):

| key | gate | opportunity title | roles | due | state | artifact |
|---|---|---|---|---|---|---|
| `rhcso` | HITL-1 | Rural Health Care Services Outreach Program (HRSA, ceiling $300,000, score 77.3, `pursue`) | development_director, executive_director | +4 d | open | `content_hash` of the matrix row |
| `aware` | HITL-2 | Project AWARE: Advancing Wellness and Resiliency in Education (SAMHSA) | finance_director | +20 h | open | framework v2 hash (request $1,620,000.00, 5 periods, indirect $247,118.64 at 18.2% MTDC, caps pass, `drafted_by: "hope-budget-agent"`) |
| `aware-old` | HITL-2 | same | finance_director | - | superseded | framework v1 hash |
| `crg` | HITL-4 | Community Resilience Grants (Cascade Health Foundation, request $150,000) | executive_director | -3 h | open (overdue) | draft hash `sha256:` of the seeded framework |
| `chw` | HITL-5 | Community Health Workers for Public Health Response and Resilient Communities (CDC) | aor | +6 h | open | manifest hash, `payload_ref = package:<uuid5 chw-package>` |
| `yof` | HITL-1 | Youth Opportunity Fund | development_director, executive_director | - | decided `no_go` by `demo-user`, comment "Outside our service area." | - |

    Seeded workflows are not running in Temporal; deciding them only writes rows and an outbox
    event that no workflow consumes, which is safe. The live demo flow (Pursue -> HITL-1 opened by
    M4's workflow) adds real rows next to them.

### Web (SC05, SC06)

16. `apps/web/src/api/approvals/`: `types.ts` (endpoint shapes below), `http.ts`
    (`listApprovals(q)`, `getApproval(id)`, `decide(id, body, {stepUp})` sending `X-Hope-MFA: true`
    after the step-up dialog), `fixture.ts` (in-memory copy of the seed cases plus the 409 case), `index.ts`.
    The matrix/workflow fan-out in today's `HttpApi.listHitlRequests` is removed.
17. SC05 lists, SC06 shows and decides. Details are in the screen specs.

## Contracts

- **Shared models used:** `Gate`, `HitlRequest`, `HitlDecision` (`role` from M0), `Decision`,
  `STEP_UP_MFA_GATES` (`hope_core.schemas.hitl`); `ProposalFramework`, `Totals`, `CapCheck`,
  `Approval` (`hope_core.schemas.proposal_framework`); `Money`; `Principal`, `get_principal`,
  `Role` (`hope_core.auth`); `StaleArtifactError`, `NotFound`, `Problem` (`hope_core.errors`);
  `EventType.HITL_DECIDED`, `PillarEnvelope`.
- **Shared contract additions:** none in Owns. Needed from M0/M4 are under Requests to M0.
- **Events:** produces `hitl.decided` (topic `gop.hitl.events`, payload `HitlDecision`, schema
  `hitl-decision`), consumed by the workflow (M4) and the projector. Consumes nothing.
- **Service-local models** (in `api/approvals.py`): `ApprovalItem`, `ApprovalCounts`,
  `ApprovalPage`, `DecisionOption`, `OpportunityPreview`, `BudgetPreview`, `DraftPreview`,
  `PackagePreview` (discriminated on `kind`), `GateHistoryEntry`, `ApprovalLogEntry`,
  `ApprovalDetail`, `DecisionBody`, `DecisionAccepted`, and the constant
  `GATE_OPTIONS: dict[Gate, tuple[DecisionOption, ...]]` (a drift test compares it with `hope_workflow.policy.GATES`).

### `GET /v1/approvals?assignee=me`

Roles: any. Headers (dev): `X-Hope-User`, `X-Hope-Roles: finance_director` (from the role switcher).

```json
{
  "items": [
    {
      "request_id": "6f1d2c9a-41b8-5e0f-9a3c-7b2e8d4f1a60",
      "gate": "HITL-2",
      "status": "open",
      "workflow_id": "demo-wf-aware",
      "opportunity_id": "0c9a7e52-8d13-5f4b-b6a1-2e9f3d7c4b18",
      "title": "Project AWARE: Advancing Wellness and Resiliency in Education",
      "summary": "Budget sign-off: request 1,620,000.00",
      "approver_roles": ["finance_director"],
      "artifact_hash": "sha256:3f1c9a0b7e2d4c6f8a1b3c5d7e9f0a2b4c6d8e0f1a3b5c7d9e1f3a5b7c9d1e3f",
      "requested_at": "2026-11-07T19:00:00Z",
      "due_at": "2026-11-08T15:00:00Z",
      "internal_deadline": "2026-11-25T22:00:00Z",
      "overdue": false,
      "can_decide": true,
      "acting_role": "finance_director",
      "step_up_required": true,
      "decision": null,
      "decided_by": null,
      "decided_at": null
    }
  ],
  "counts": { "open": 1, "overdue": 0, "by_gate": { "HITL-1": 0, "HITL-2": 1, "HITL-4": 0, "HITL-5": 0 } }
}
```

Codes: 200; 422 `validation_error`.

### `GET /v1/approvals/{request_id}`

Roles: any. Response = `ApprovalItem` fields plus:

```json
{
  "options": [
    { "decision": "approve", "label": "Approve and lock", "tone": "primary", "requires_comment": false },
    { "decision": "request_changes", "label": "Request changes", "tone": "neutral", "requires_comment": true },
    { "decision": "reject", "label": "Reject", "tone": "danger", "requires_comment": true }
  ],
  "preview": {
    "kind": "budget",
    "framework_id": "9e3b1f64-2a7c-5d08-8f4e-1c6a0b9d2e73",
    "version": 2,
    "periods": 5,
    "drafted_by": "hope-budget-agent",
    "totals": {
      "direct_minor": 137288136, "mtdc_base_minor": 135780000, "indirect_minor": 24711864,
      "request_minor": 162000000, "cost_share_minor": 0, "project_total_minor": 162000000
    },
    "indirect_rate_bps": 1820,
    "cap_checks": [ { "rule": "award_ceiling", "status": "pass" }, { "rule": "indirect_cap", "status": "pass" } ],
    "missing": false,
    "links": { "budget": "/frameworks/9e3b1f64-2a7c-5d08-8f4e-1c6a0b9d2e73/budget" }
  },
  "history": [
    {
      "request_id": "b2d4e6f8-0a1c-5e3b-9d7f-4a6c8e0b2d41",
      "status": "superseded",
      "artifact_hash": "sha256:9b0c6d2e4f6a8c0e2a4c6e8a0c2e4a6c8e0a2c4e6a8c0e2a4c6e8a0c2e4ae21a",
      "decision": null,
      "decided_by": null,
      "requested_at": "2026-11-06T15:30:00Z",
      "decided_at": null
    }
  ],
  "approvals": []
}
```

Other preview shapes:

```json
{ "kind": "opportunity", "composite_score": 77.3, "recommendation": "pursue", "agency_name": "HRSA",
  "award_ceiling": { "amount_minor": 30000000, "currency": "USD" }, "application_due": "2026-12-11T21:59:00Z",
  "internal_deadline": "2026-12-08T22:00:00Z", "links": { "opportunity": "/opportunities/7a…" } }
{ "kind": "draft", "framework_id": "4c…", "project_title": "Community Resilience Grants", "request_minor": 15000000,
  "approvals": [ { "gate": "HITL-2", "approver_user_id": "sam.ortiz", "at": "2026-10-30T17:12:00Z" } ],
  "links": { "draft": "/frameworks/4c…/draft" } }
{ "kind": "package", "package_id": "d8…", "links": { "package": "/packages/d8…" } }
```

Codes: 200; 404 `not_found`; 422 `validation_error` (id not a UUID).

### `POST /v1/approvals/{request_id}/decision`

Roles: one of the row's `approver_roles` (HITL-1 `development_director`/`executive_director`,
HITL-2 `finance_director`, HITL-4 `executive_director`, HITL-5 `aor`). HITL-2/HITL-5 also need
`X-Hope-MFA: true` (dev placeholder for step-up).

Request:

```json
{ "decision": "approve", "artifact_hash": "sha256:3f1c9a0b…c9d1e3f", "comment": null, "role": "finance_director" }
```

202:

```json
{
  "request_id": "6f1d2c9a-41b8-5e0f-9a3c-7b2e8d4f1a60",
  "event_id": "a7c3e9f1-5b2d-4e8a-9c6f-0d1b3a5e7c92",
  "gate": "HITL-2",
  "decision": "approve",
  "role": "finance_director",
  "decided_by": "demo-user",
  "decided_at": "2026-11-07T20:41:00Z",
  "next": "/approvals"
}
```

Errors (`application/problem+json`):

| Status | `code` | When | Extras |
|---|---|---|---|
| 404 | `not_found` | no MVP gate row with that id | - |
| 409 | `gate_closed` | row is `decided` or `superseded` | `status`, `decision`, `decided_by`, `decided_at` |
| 403 | `approver_role_required` | principal holds none of `approver_roles` (or `role` invalid) | `approver_roles` |
| 403 | `step_up_required` | HITL-2/5 without `X-Hope-MFA: true` | - |
| 422 | `decision_not_allowed` | decision not in options | `options` |
| 422 | `comment_required` | option needs a comment and it's blank | - |
| 403 | `separation_of_duties` | HITL-2 approver drafted the budget | `drafted_by` |
| 409 | `stale_artifact` | hash differs from the open row | `current_hash` |
| 422 | `validation_error` | body shape | FastAPI errors |

Example:

```json
{ "type": "about:blank", "title": "Stale artifact", "status": 409, "code": "stale_artifact",
  "detail": "The artifact changed after this request was opened.",
  "current_hash": "sha256:5d7f9b1c3e5a7c9e1b3d5f7a9c1e3b5d7f9a1c3e5b7d9f1a3c5e7b9d1f3a5c7e" }
```

- **Database:** no migration. Reads `pillar_gate_requests`, `tenant_opportunity`, `opportunities`,
  `opportunity_versions`, `frameworks`, `approvals`; writes `approvals`, `pillar_gate_requests`
  (status/decision columns) and `outbox`. All inside `tenant_tx`.

## Owns

```text
services/pillar/src/hope_pillar/api/approvals.py
services/pillar/src/hope_pillar/demo.py
services/pillar/tests/test_approvals.py
services/pillar/tests/test_approvals_demo.py
services/pillar/tests/snapshots/openapi/approvals.json
db/migrations/0110-0119 (reserved, not used)
apps/web/src/features/approvals/**
apps/web/src/api/approvals/**
apps/web/src/app/approvals/**
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 `GET /v1/approvals` returns open MVP-gate rows sorted by `due_at` (nulls last) with `title`, `internal_deadline`, `overdue`, `can_decide`, `acting_role` and `step_up_required`; superseded rows and non-MVP gates are never listed.
- [ ] AC2 `assignee=me` follows `X-Hope-Roles` (switching to `finance_director` shows only HITL-2), and empty `approver_roles` counts as assigned.
- [ ] AC3 `status`, `gate`, `opportunity_id` filter; `counts.open`, `counts.overdue` and all four `counts.by_gate` keys ignore `status` and `limit`.
- [ ] AC4 Detail returns the right `preview.kind` per gate with the fields in the table, `options` with labels, `history` and `approvals`; a HITL-2 whose framework is gone returns `missing: true`.
- [ ] AC5 Unknown id -> 404 `not_found` on detail and decision.
- [ ] AC6 A valid decision returns 202, inserts one `approvals` row, marks the row `decided`, and writes one `hitl.decided` outbox event whose payload has `role` and `details.role`.
- [ ] AC7 Each error in the table returns its status and `code` (one test per row) and writes nothing.
- [ ] AC8 HITL-5 approve returns `next = /packages/{package_id}` and never calls `route_outbound`.
- [ ] AC9 `GATE_OPTIONS` matches `hope_workflow.policy.GATES` options for the four MVP gates.
- [ ] AC10 `seed()` creates the six gate rows and their opportunities/frameworks; running it twice creates no duplicates.
- [ ] AC11 The `approvals` router has its own OpenAPI snapshot.
- [ ] AC12 SC05 and SC06 meet their acceptance criteria; the web client calls `GET /v1/approvals` (no fan-out) and its routes exist in `snapshots/openapi/approvals.json`.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/pillar/tests/test_approvals.py::test_list_open_sorted_and_computed_fields` | db/api |
| AC2 | `test_approvals.py::test_assignee_me_follows_roles_header` | db/api |
| AC3 | `test_approvals.py::test_filters_and_counts` | db/api |
| AC4 | `test_approvals.py::test_detail_preview_per_gate` (parametrized HITL-1/2/4/5), `::test_budget_preview_missing` | db/api |
| AC5 | `test_approvals.py::test_unknown_request_404` | api |
| AC6 | `test_approvals.py::test_decision_writes_approval_projection_and_event` | db/api |
| AC7 | `test_approvals.py::test_decision_errors` (parametrized over the error table) | db/api |
| AC8 | `test_approvals.py::test_hitl5_authorize_no_routing` | db/api |
| AC9 | `test_approvals.py::test_gate_options_match_workflow_policy` (imports `hope_workflow` in the test only) | unit |
| AC10 | `services/pillar/tests/test_approvals_demo.py::test_seed_idempotent` | db |
| AC11 | `services/pillar/tests/test_openapi.py::test_router_snapshots` (M0) | api |
| AC12 | SC05/SC06 test plans; `apps/web/src/api/approvals/http.test.ts::lists via approvals endpoint`, `apps/web/src/api/approvals/http.contract.test.ts::routes exist in snapshot` | unit |

DB tests follow `services/pillar/tests/test_api.py` (`world`, `open_gate` pattern; helpers in a package
module because pytest runs with `--import-mode=importlib`) and skip when Postgres is down.
All tests are offline; no model is called (MockProvider is not even needed).
Commands: the CI commands in `AGENTS.md`; `UPDATE_SNAPSHOTS=1 uv run pytest services/pillar/tests/test_openapi.py` once.

## Out of scope

HITL-0, HITL-3, REVIEW-* gates; cursor pagination; escalation display; delegation; bulk decisions;
e-signature; real IdP step-up; real submission (`route_outbound`); notifications; audit screen.

## Requests to M0

1. **Run the projector in `make demo`.** Without `hope_pillar.projector.Projector` consuming
   `hitl.requested`, gates opened by M4's live workflow never reach `pillar_gate_requests` and the
   inbox stays empty. Alternative: M4's publish activity also upserts the projection row.
2. **`get_principal` reads `X-Hope-MFA`** (bool, default false) into `Principal.mfa`, as today's
   `auth.py` does; M0's text lists only `X-Hope-User` / `X-Hope-Roles`.
3. **Generic problem exception** in `hope_core.errors`: `ProblemError(status, code, title, detail, **extras)`
   handled by the same installer, so routers can raise `gate_closed`, `approver_role_required`,
   `step_up_required`, `decision_not_allowed`, `comment_required`, `separation_of_duties`. Design-around
   if absent: `approvals.py` returns a local `JSONResponse(media_type="application/problem+json")`.
4. **Projection column for `package_id`.** `HitlRequest.package_id` (M0) has nowhere to go in
   `pillar_gate_requests`. Add `package_id uuid` there (pillar migration, M0) and project it. Design-around:
   M4 sets `payload_ref = "package:{uuid}"` and M3 parses it.
5. **Workflow reads `HitlDecision.role`** (M4): `_invalid` checks `d.details.get("role")`; switch to
   `d.role` (M3 sends both for now). Also M4's HITL-1 roles must be `development_director` **or**
   `executive_director` as M0 step 2 says (`policy.GATES` lists only `development_director`).
6. **Demo seed order:** run `hope_pillar.demo.seed` after the core tenant/agency seed (it inserts its
   own demo opportunities, so it doesn't need M1/M2's seeds).
7. **Nav badge (optional):** let a nav entry show a count; M3 would supply `counts.open` from `api/approvals`.
8. **`lib/gates.ts`** HITL-5 "Hold" should send `defer`, not `reject` (SC06 doesn't depend on it; it uses `options` from the API).

## Decisions needed

- **D1 Step-up MFA in the demo.** Recommended: keep today's placeholder dialog (any 6 digits) for
  HITL-2 and HITL-5; it shows the control in 3 seconds. Alternative: skip it in the MVP.
- **D2 HITL-5 approval path.** Recommended: decide HITL-5 in SC06 via M3's decision POST (records the
  AOR authorization; M7 unlocks download/Mark submitted from the decided row). The existing
  `/v1/packages/{id}/authorize` stays for later real submission.
- **D3 Where other screens decide.** Recommended: M5's budget screen (SC13) and M6's draft screen
  (SC19) link to `/approvals/{request_id}` for HITL-2/HITL-4 instead of building their own decision
  UI, so there is one decision UX and one write path.
- **D4 Pagination.** Recommended: none (limit 100); the demo has under 20 requests.
- **D5 Signals route.** Recommended: M4 keeps `POST /v1/workflows/{id}/signals/{gate}` unchanged; the
  web only uses M3's decision POST.

## References

- `services/pillar/src/hope_pillar/api/routes.py` (`_lock_gate`, `_decide`, `signal_gate`, `authorize_package`), `models.py`, `projector.py`
- `services/workflow/src/hope_workflow/policy.py::GATES`, `workflow.py::_gate`, `_invalid`, `contracts.py::WorkflowInput.small_org_ack`
- `db/migrations/0001_core.sql` (`approvals`, `frameworks`, `tenant_opportunity`), `0100_pillar.sql`
- `apps/web/src/features/approvals/*`, `apps/web/src/lib/gates.ts`
- Full roadmap version: `docs/specs/features/S02-approval-inbox.md` (branch `specs/web`)
