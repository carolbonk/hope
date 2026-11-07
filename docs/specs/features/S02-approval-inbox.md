# S02: Approval inbox API and screens

| | |
|---|---|
| Wave | 1 |
| Depends on | S00 |
| Screens | [SC05](../screens/SC05-approval-inbox.md), [SC06](../screens/SC06-approval-detail.md) |
| Migrations | - (none reserved; reads existing tables only) |
| Blueprint | 4.4 (HITL checkpoints, gate mechanics), 7.4 (pillar API), 8.4 (step-up MFA) |
| Status | Draft |

## Goal

Every approver sees one inbox of the HITL gates waiting on their roles, soonest SLA first,
and opens any request to review exactly the artifact they are approving before they decide.
Today the web app builds the inbox by fetching every workflow one by one, and there is no
way to open a single request; this spec adds `GET /v1/approvals` and
`GET /v1/approvals/{request_id}` and rebuilds SC05 (list) and SC06 (detail and decision) on them.

## Current state

- **Gate projection.** `db/migrations/0100_pillar.sql` creates `pillar_gate_requests`
  (`request_id`, `tenant_id`, `workflow_id`, `subject_id` = opportunity id, `gate`,
  `artifact_hash`, `approver_roles text[]`, `due_at`, `summary`, `payload_ref`,
  `status` in `open|decided|superseded`, `decision`, `decided_by`, `requested_at`,
  `decided_at`), with a partial unique index `pillar_gate_one_open (tenant_id, workflow_id, gate) WHERE status = 'open'`.
  `services/pillar/src/hope_pillar/projector.py::project` fills it from `hitl.requested`
  (superseding the previous open request for the same workflow and gate) and `hitl.decided`.
- **Reads.** The only read of gates is `GET /v1/workflows/{workflow_id}` (`GateView` in
  `services/pillar/src/hope_pillar/api/models.py`). There is no list across workflows.
- **Decisions.** `POST /v1/workflows/{workflow_id}/signals/{gate}` (`signal_gate`) and
  `POST /v1/packages/{package_id}/authorize` (`authorize_package`) in
  `services/pillar/src/hope_pillar/api/routes.py` (after S00: `api/workflows.py` and
  `api/packages.py`). `_lock_gate` returns 403 when the principal has none of
  `approver_roles`, 403 when the gate is in `STEP_UP_MFA_GATES` and `principal.mfa` is false,
  and 409 when the request is not `open`. `_decide` returns 409 when `artifact_hash` differs
  (after S00: problem+json `code: "stale_artifact"` with `current_hash`), writes `approvals`
  and publishes `hitl.decided`. HITL-5 `approve` through the signals route is refused (409).
- **Gate policy.** `services/workflow/src/hope_workflow/policy.py::GATES` holds the default
  roles, SLA hours, escalation role and decision options per gate. On SLA timeout
  `ApplicationWorkflow._gate` adds `escalate_to` to the roles **in workflow memory only**; it
  does not publish a new `hitl.requested`, so the projection keeps the original roles.
- **HITL-0** profile proposals do not use `pillar_gate_requests`. They live in
  `profile_change_proposals` (`db/migrations/0300_profile.sql`) and are decided through
  `POST /v1/agencies/{agency_id}/profile/proposals/{proposal_id}/approve|reject` (profile service).
- **Web.** `apps/web/src/features/approvals/` has `ApprovalInbox.tsx` (list plus inline
  decisions), `RequestCard.tsx` (decision buttons, comment, 409 notice), `StepUpDialog.tsx`
  (6-digit placeholder) and `ApprovalInbox.test.tsx`. `HttpApi.listHitlRequests` in
  `apps/web/src/api/http.ts` emulates a list by calling the matrix and then
  `GET /v1/workflows/{id}` per row. Decision labels and options are in `apps/web/src/lib/gates.ts`
  (`GATES`, `optionFor`). Note: `lib/gates.ts` sends `reject` for HITL-5 "Hold", but the
  workflow only accepts `approve` and `defer` for HITL-5 (`policy.GATES`); see Shared contract additions.

## Behaviour

### `GET /v1/approvals`

1. Any authenticated principal may call it (dev: `X-Hope-User`, `X-Hope-Roles`; S01 swaps in
   OIDC behind `hope_core.auth.get_principal`). The tenant is always `HOPE_TENANT_ID` (S00);
   all reads run in `tenant_tx`, so RLS limits rows to that tenant. No tenant appears in the URL or headers.
2. Query parameters (all optional):
   - `status`: `open` (default), `decided`, `superseded` or `all`.
   - `gate`: repeatable, any `Gate` value (`HITL-0` ... `HITL-5`, `REVIEW-ELIGIBILITY`, `REVIEW-PARSE`). Unknown value -> 422.
   - `assignee`: only `me`. Keeps rows whose `approver_roles` overlap the principal's roles.
     Rows with an empty `approver_roles` array count as assigned to everyone (matches `_lock_gate`).
   - `workflow_id`, `opportunity_id` (UUID): exact filters. Used by SC08, SC19 and SC21.
   - `overdue`: `true` keeps open rows with `due_at < now()`.
   - `limit`: 1-100, default 50. `cursor`: opaque, from `next_cursor`.
3. Ordering: `due_at ASC NULLS LAST, requested_at ASC, request_id ASC` for `status=open`;
   `coalesce(decided_at, requested_at) DESC, request_id DESC` otherwise. The cursor is the
   base64url JSON of the last row's sort key; an undecodable cursor -> 400 `invalid_cursor`.
4. Each item joins `tenant_opportunity` (on `workflow_id`) and `opportunities` (on
   `subject_id::uuid`) for `title`. A gate whose opportunity row is missing still appears, with `title: null`.
5. Computed per item, never stored:
   - `overdue`: `status = 'open' AND due_at IS NOT NULL AND due_at < now()`.
   - `can_decide`: `status = 'open'` and (empty `approver_roles` or overlap with the principal's roles).
   - `step_up_required`: `gate in STEP_UP_MFA_GATES`.
   - `decide_in`: where the decision is made (see the table below).
6. **HITL-0.** When `gate` is unset or includes `HITL-0`, pending `profile_change_proposals`
   are merged into the result as items with `gate: "HITL-0"`, `request_id = proposal_id`,
   `workflow_id: null`, `opportunity_id: null`, `title: "Agency profile change"`,
   `artifact_hash = content_hash`, `approver_roles` = the HITL-0 roles from the agency's
   `approval_hierarchy` rule (fallback `hope_profile.validators.DEFAULT_HITL0_ROLES`),
   `due_at = proposed_at + sla_hours` (fallback 72 h), `summary` = "Profile change proposed by
   {proposed_by}: {top-level sections}", and `decide_in: "profile_proposals"`. Status maps
   `pending -> open`, `approved|rejected -> decided`. `can_decide` is false when
   `proposed_by` equals the principal (separation of duties, matching the table's CHECK).
   See Decisions needed (D1).
7. The response carries `counts` for the same filters except `status`, `overdue` and the
   cursor: `{open, overdue}`. These feed the nav badge and SC02.

| `gate` | `decide_in` | Where the human decides |
|---|---|---|
| `HITL-1`, `HITL-2`, `HITL-3`, `HITL-4`, `REVIEW-ELIGIBILITY` | `inbox` | SC06 (SC13, SC20 and SC21 may also decide; same signal) |
| `HITL-5` | `package` | SC22 (`POST /v1/packages/{request_id}/authorize`); SC06 is read-only |
| `HITL-0` | `profile_proposals` | SC10 |
| `REVIEW-PARSE` | `parse_review` | SC12 |

### `GET /v1/approvals/{request_id}`

8. Same auth as the list. Looks up `pillar_gate_requests.request_id`, then
   `profile_change_proposals.proposal_id`; neither -> 404 `not_found`.
9. Returns the list item plus:
   - `preview`: what the approver must see (blueprint 4.4 "What they see"), built only from
     stored rows, never from an LLM call. The `kind` depends on the gate:
     - `opportunity` (HITL-1, REVIEW-ELIGIBILITY): from `tenant_opportunity` and the latest
       `opportunity_versions.normalized`: `composite_score`, `recommendation`,
       `internal_deadline`, `application_due`, `agency_name`, `funding.award_ceiling`
       (`Money`), and `links.opportunity`.
     - `budget` (HITL-2): the `frameworks` row whose `content_hash = artifact_hash`
       (tenant-scoped); `framework_id`, `version`, `status`, `budget.totals`
       (`Totals`, minor units), `cap_checks` (rule and status only), `periods`, and
       `links.budget = /frameworks/{id}/budget`. No match -> `kind: "budget"` with
       `framework_id: null` and `missing: true` (the artifact was replaced; a decision will 409).
     - `draft` (HITL-3, HITL-4): the latest `frameworks` row for the opportunity and agency;
       `framework_id`, `project_title` (`framework.scope.project_title`),
       `request_minor` (`framework.budget.totals.request_minor`), `approvals` (`Approval[]` already
       recorded on the framework), and `links.compliance` (HITL-3) or `links.approve` (HITL-4).
     - `package` (HITL-5): `package_id = request_id`, `channel` (`HitlRequest.channel` from
       S00; `null` until the workflow sets it), `payload_ref` present or not, and `links.package = /packages/{request_id}`.
     - `profile_change` (HITL-0): `agency_id`, `base_version`, `diff` (the stored diff
       JSON), `proposed_by`, `proposed_at`, and `links.review = /profile/proposals`.
     - `parse` (REVIEW-PARSE): `links.review = /parse-review`.
   - `options`: the decision options for the gate, from `hope_core.schemas.hitl.GATE_OPTIONS`
     (Shared contract additions), in a fixed order: `go, approve, defer, request_changes, no_go, reject`.
   - `history`: earlier requests for the same `workflow_id` and `gate` (superseded or
     decided), newest first, each `{request_id, status, artifact_hash, decision, decided_by, requested_at, decided_at}`,
     plus that workflow's `approvals` rows for the gate (`decision`, `decided_by`, `decided_at`,
     `comment`, `artifact_hash`). Max 20.
10. S02 never writes. Decisions keep going through the existing signal, authorize and
    profile-proposal routes, which own every write-side check (roles, MFA, stale hash,
    separation of duties in the workflow, HITL-5 package routing).
11. The LLM plays no part in either endpoint.

### Web (SC05, SC06)

12. SC05 lists items from `GET /v1/approvals`; SC06 shows one request and posts the decision.
    Their full behaviour is in the screen specs.
13. `api/approvals/` (created by S00's split) gets `listApprovals(query)`, `getApproval(id)`
    and keeps `submitSignal`. `HttpApi.listHitlRequests`'s matrix-plus-workflows emulation is
    deleted. The HITL-5 authorize call moves to SC22's client (S21); SC06 links there.

## Contracts

- **Shared models used:** `Gate`, `HitlRequest`, `HitlDecision`, `Decision`,
  `STEP_UP_MFA_GATES` (`hope_core.schemas.hitl`); `Totals`, `CapCheck`, `Approval`
  (`hope_core.schemas.proposal_framework`); `Money` (`hope_core.money`); `Problem`,
  `NotFound` (`hope_core.errors`, S00); `Principal`, `get_principal` (`hope_core.auth`, S00).
- **Shared contract additions** (batch into S00):
  1. `hope_core.schemas.hitl.GATE_OPTIONS: dict[Gate, tuple[Decision, ...]]` moved from
     the `options` field of `hope_workflow.policy.GATES` (workflow imports it from core).
     Values: `HITL-1: (go, defer, no_go)`; `HITL-2/3/4, REVIEW-*: (approve, request_changes, reject)`;
     `HITL-5: (approve, defer)`; `HITL-0: (approve, reject)` (the profile routes only support those two).
  2. `hope_core.errors` codes used by the decision routes, so SC06 can branch on `code`
     instead of the message: `approver_role_required` (403), `step_up_required` (403),
     `gate_closed` (409, extras `status`, `decided_by`, `decided_at`),
     `use_package_authorize` (409, HITL-5 approve on the signals route), `invalid_cursor` (400).
     `_lock_gate` and `signal_gate` raise them (S00 already converts these routes to problem+json).
  3. `apps/web/src/lib/gates.ts`: HITL-5 "Hold" sends `defer`, not `reject`; HITL-0 options
     become approve and reject only; add `decideIn: "inbox" | "package" | "profile_proposals" | "parse_review"` to `GateInfo`.
  4. `apps/web/src/components/ui/DecisionPanel.tsx` and `StepUpDialog.tsx`: move the
     decision buttons, required-comment rule, step-up dialog and stale-hash notice out of
     `features/approvals/RequestCard.tsx` into shared primitives, so SC06 (S02), SC13 (S06),
     SC20 (S19) and SC21 (S20) render one decision UI. Props:
     `DecisionPanel({ gate, options, artifactHash, stepUpRequired, disabled, onSubmit(decision, comment, stepUpToken) => Promise<void> })`.
  5. Move `apps/web/src/features/status.tsx` (`GateBadge`, `UrgencyBadge`, `roleLabel`, ...)
     to `apps/web/src/components/ui/StatusBadges.tsx`; it is shared by every feature and has no owner today.
  6. `apps/web/src/nav.ts`: the Approvals entry shows `counts.open` as a badge (S00 adds an
     optional `badge?: () => Promise<number>` to nav entries; S02 supplies the loader from `api/approvals`).
- **Events:** none produced or consumed.
- **Endpoints** (service-local response models in `services/pillar/src/hope_pillar/api/approvals.py`):

`GET /v1/approvals?status=open&assignee=me&limit=2`, roles: any authenticated user.

```json
{
  "items": [
    {
      "request_id": "8a0f3c55-6f0e-4d7a-9a51-0c6e2f1b7d02",
      "gate": "HITL-2",
      "status": "open",
      "workflow_id": "wf-samhsa-aware",
      "opportunity_id": "5b8d3f8e-2a51-4c1e-9d0a-3f7c2b1e4a90",
      "title": "Project AWARE: Advancing Wellness and Resiliency in Education",
      "summary": "Budget sign-off: request 1,620,000.00",
      "approver_roles": ["finance_director"],
      "artifact_hash": "sha256:3f1c9a0b7e2d4c6f8a1b3c5d7e9f0a2b4c6d8e0f1a3b5c7d9e1f3a5b7c9d1e3f",
      "requested_at": "2026-11-06T19:00:00Z",
      "due_at": "2026-11-08T11:00:00Z",
      "overdue": false,
      "can_decide": true,
      "step_up_required": true,
      "decide_in": "inbox",
      "decision": null,
      "decided_by": null,
      "decided_at": null
    }
  ],
  "next_cursor": "eyJkdWUiOiIyMDI2LTExLTA4VDExOjAwOjAwWiIsImlkIjoiOGEwZi4uLiJ9",
  "counts": { "open": 5, "overdue": 1 }
}
```

Status codes: 200; 400 `invalid_cursor`; 422 `validation_error` (bad `status`, `gate`,
`assignee`, `limit`, UUID). Models: `ApprovalItem`, `ApprovalCounts`, `ApprovalPage`.

`GET /v1/approvals/{request_id}`, roles: any authenticated user.

```json
{
  "request_id": "8a0f3c55-6f0e-4d7a-9a51-0c6e2f1b7d02",
  "gate": "HITL-2",
  "status": "open",
  "workflow_id": "wf-samhsa-aware",
  "opportunity_id": "5b8d3f8e-2a51-4c1e-9d0a-3f7c2b1e4a90",
  "title": "Project AWARE: Advancing Wellness and Resiliency in Education",
  "summary": "Budget sign-off: request 1,620,000.00",
  "approver_roles": ["finance_director"],
  "artifact_hash": "sha256:3f1c9a0b7e2d4c6f8a1b3c5d7e9f0a2b4c6d8e0f1a3b5c7d9e1f3a5b7c9d1e3f",
  "requested_at": "2026-11-06T19:00:00Z",
  "due_at": "2026-11-08T11:00:00Z",
  "overdue": false,
  "can_decide": true,
  "step_up_required": true,
  "decide_in": "inbox",
  "decision": null,
  "decided_by": null,
  "decided_at": null,
  "options": ["approve", "request_changes", "reject"],
  "preview": {
    "kind": "budget",
    "framework_id": "c2a7e1d4-9b3f-4e8a-a1c6-5d2f7b9e0a13",
    "version": 3,
    "status": "verified",
    "periods": 5,
    "totals": {
      "direct_minor": 137288136, "mtdc_base_minor": 130000000, "indirect_minor": 24711864,
      "request_minor": 162000000, "cost_share_minor": 0, "project_total_minor": 162000000
    },
    "cap_checks": [
      { "rule": "award_ceiling", "status": "pass" },
      { "rule": "indirect_cap", "status": "pass" }
    ],
    "missing": false,
    "links": { "budget": "/frameworks/c2a7e1d4-9b3f-4e8a-a1c6-5d2f7b9e0a13/budget" }
  },
  "history": [
    {
      "request_id": "1e4b2c3d-0a9f-4b8e-8c7d-6e5f4a3b2c1d",
      "status": "superseded",
      "artifact_hash": "sha256:9b0c...e21a",
      "decision": null,
      "decided_by": null,
      "requested_at": "2026-11-05T15:30:00Z",
      "decided_at": null
    }
  ],
  "approvals": []
}
```

Status codes: 200; 404 `not_found`; 422 `validation_error` (not a UUID). Models:
`ApprovalDetail(ApprovalItem)`, `Preview` (discriminated union on `kind`: `OpportunityPreview`,
`BudgetPreview`, `DraftPreview`, `PackagePreview`, `ProfileChangePreview`, `ParsePreview`),
`GateHistoryEntry`, `ApprovalLogEntry`.

- **Database:** none. Reads `pillar_gate_requests`, `approvals`, `tenant_opportunity`,
  `opportunities`, `opportunity_versions`, `frameworks`, `profile_change_proposals`,
  `agency_profile_versions` inside `tenant_tx`. The existing `pillar_gate_one_open` index
  and the primary key cover MVP volumes (one agency, tens of open gates); see D3.

## Owns

```text
services/pillar/src/hope_pillar/api/approvals.py
services/pillar/tests/test_approvals.py
services/pillar/tests/snapshots/openapi/approvals.json
apps/web/src/features/approvals/**
apps/web/src/api/approvals/**
apps/web/src/app/approvals/page.tsx
apps/web/src/app/approvals/[requestId]/page.tsx
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 `GET /v1/approvals` returns open requests ordered by `due_at` (nulls last), with
  `title`, `overdue`, `can_decide`, `step_up_required` and `decide_in` computed as specified.
- [ ] AC2 `assignee=me` keeps only requests whose `approver_roles` overlap the principal's roles (or are empty).
- [ ] AC3 `status`, `gate` (repeated), `workflow_id`, `opportunity_id` and `overdue` filter correctly; `counts` ignores `status`/`overdue`/cursor.
- [ ] AC4 Cursor pagination returns every row exactly once across pages; a bad cursor returns 400 `invalid_cursor` as problem+json.
- [ ] AC5 A superseded request is not in the default list and is in `status=superseded`.
- [ ] AC6 Rows of another tenant are never returned (RLS); no request carries a tenant header.
- [ ] AC7 Pending HITL-0 proposals appear with `decide_in: "profile_proposals"`; the proposer gets `can_decide: false`.
- [ ] AC8 `GET /v1/approvals/{id}` returns the right `preview.kind` for HITL-1, HITL-2, HITL-3/4, HITL-5 and HITL-0, plus `options` from `GATE_OPTIONS` and the gate `history`.
- [ ] AC9 A HITL-2 request whose framework hash no longer exists returns `preview.missing: true`.
- [ ] AC10 Unknown id returns 404 `not_found`.
- [ ] AC11 The `approvals` router has its own OpenAPI snapshot, and no other router's snapshot changes.
- [ ] AC12 SC05 and SC06 meet every acceptance criterion in their screen specs.
- [ ] AC13 The web HTTP client calls `GET /v1/approvals` for the inbox (no per-workflow fan-out), and the HTTP contract test passes against `snapshots/openapi/approvals.json`.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/pillar/tests/test_approvals.py::test_list_open_sorted_by_due` | db/api |
| AC2 | `services/pillar/tests/test_approvals.py::test_assignee_me_filters_by_role` | db/api |
| AC3 | `services/pillar/tests/test_approvals.py::test_filters_and_counts` | db/api |
| AC4 | `services/pillar/tests/test_approvals.py::test_cursor_pagination_complete`, `::test_invalid_cursor_problem` | db/api |
| AC5 | `services/pillar/tests/test_approvals.py::test_superseded_hidden_by_default` | db/api |
| AC6 | `services/pillar/tests/test_approvals.py::test_other_tenant_rows_invisible` | db |
| AC7 | `services/pillar/tests/test_approvals.py::test_profile_proposals_merged` | db/api |
| AC8 | `services/pillar/tests/test_approvals.py::test_detail_preview_per_gate` (parametrized by gate) | db/api |
| AC9 | `services/pillar/tests/test_approvals.py::test_budget_preview_missing_framework` | db/api |
| AC10 | `services/pillar/tests/test_approvals.py::test_detail_not_found` | api |
| AC11 | `services/pillar/tests/test_openapi.py::test_router_snapshots` (S00) with `approvals.json` | api |
| AC12 | tests listed in SC05 and SC06 | unit |
| AC13 | `apps/web/src/api/approvals/http.test.ts::lists_via_approvals_endpoint`, `apps/web/src/api/approvals/http.contract.test.ts::routes_exist_in_snapshot` | unit |

Tests reuse the `world`/`open_gate` helpers pattern from `services/pillar/tests/test_api.py`
(pytest runs with `--import-mode=importlib`, so shared helpers must live in a package module such as `hope_pillar/testing.py`, not be imported from `conftest`).
DB tests skip when Postgres is unreachable, like the existing pillar tests.
Commands: the CI commands in `AGENTS.md`, plus `UPDATE_SNAPSHOTS=1 uv run pytest services/pillar/tests/test_openapi.py` once to write `approvals.json`.

## Out of scope

- Any write path (decisions stay on the signals, authorize and profile-proposal routes).
- Fixing escalation projection (the workflow should publish a new `hitl.requested` with the
  escalated roles; request for S07). Until then an escalated request keeps its original roles in the inbox.
- Delegation / out-of-office reassignment, bulk decisions, e-signature envelopes.
- Notifications (S12) and the nav bell.

## Decisions needed

- **D1 Include HITL-0 in the inbox?** Recommended: yes, read-only rows from
  `profile_change_proposals` with `decide_in: "profile_proposals"` linking to SC10, so
  approvers have one queue. Alternative: leave HITL-0 to SC10 only (drop behaviour step 6 and AC7).
- **D2 Who may list approvals?** Recommended: any authenticated user may list and view
  (transparency inside one organization); only `can_decide` users see decision controls,
  and the write routes still enforce roles. Alternative: require at least one approver role.
- **D3 Index.** No migration is reserved. Recommended: none for MVP. If C2 wants one, add
  `CREATE INDEX pillar_gate_requests_open_due ON pillar_gate_requests (tenant_id, due_at) WHERE status = 'open'` in a pillar migration.
- **D4 Escalated roles.** Recommended: S07 republishes `hitl.requested` (same `request_id`,
  new `approver_roles`, `due_at: null`) on escalation and the projector updates the row in place
  instead of `ON CONFLICT DO NOTHING`. Needs a projector change (pillar).

## References

- `services/pillar/src/hope_pillar/api/routes.py` (`get_workflow`, `_lock_gate`, `_decide`, `signal_gate`, `authorize_package`)
- `services/pillar/src/hope_pillar/api/models.py` (`GateView`, `WorkflowView`, `SignalBody`, `DecisionAccepted`)
- `services/pillar/src/hope_pillar/projector.py::project`
- `services/workflow/src/hope_workflow/policy.py` (`GATES`, `gate_policy`) and `workflow.py` (`_gate`, `_invalid`, `_open_request`)
- `services/profile/src/hope_profile/api.py` (proposal routes), `validators.py::DEFAULT_HITL0_ROLES`
- `db/migrations/0001_core.sql` (`approvals`, `frameworks`, `tenant_opportunity`), `0100_pillar.sql`, `0300_profile.sql`
- `apps/web/src/features/approvals/*`, `apps/web/src/lib/gates.ts`, `apps/web/src/api/http.ts`
- Blueprint 4.4, 7.4, 8.4
