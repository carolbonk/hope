# S00: Shared contracts and scaffolding

| | |
|---|---|
| Wave | 0 (runs alone; every wave-1 spec depends on it) |
| Depends on | - |
| Screens | - (adds route placeholders and nav entries only) |
| Migrations | `db/migrations/0002_shared.sql` |
| Blueprint | 2.3, 5, 7.3-7.5 |
| Status | Ready |

## Goal

Make every shared change that wave-1 specs need **once, up front**, so the 15 wave-1 specs
can run in parallel and never edit the same file. This spec adds no product behaviour. It
promotes service-local contracts into `hope_core`, adds shared helpers, splits shared files
(the pillar router, the OpenAPI snapshot, the web API client) into per-feature files, and
creates empty skeletons for every folder that later specs own.

## Current state (main after PRs #1-#9)

- Contracts that are defined in services but used across services:
  `hope_matching.contracts` (`EligibilityResult`, `RuleOutcome`, `EffortEstimate`,
  `DimensionScore`, `AlignmentAssessment`), `hope_profile.contracts` (`FieldChange`,
  `ProfileUpdated`, `ProfileChangeProposal`, `StaleFieldAlert`, `NarrativeHit`,
  `CompletenessReport`), `hope_workflow.contracts` (all activity request/response models),
  `hope_pillar.contracts` (`IngestSource`, `IngestRequest`, `ProfileChangeProposal`, `DeadLetter`),
  `hope_ingestion.contracts` (event payloads), `hope_budget.contracts` (cost-basis and
  reconciliation models).
- `Principal` and `get_principal` live in `services/pillar/src/hope_pillar/api/auth.py`; the
  profile service has its own principal dependency.
- All pillar routes are in one file, `services/pillar/src/hope_pillar/api/routes.py`, with one
  OpenAPI snapshot, `services/pillar/tests/snapshots/openapi.json`.
- `hope_profile.api.router` is not mounted in any app, and the pillar defines its own
  `GET/PATCH /v1/agencies/{agency_id}/profile`, which overlap the profile service's.
- `POST /v1/frameworks/{id}/recompute` returns 501 because there is no event type.
- 409 responses carry only a text message.
- Web: one `HopeApi` interface in `apps/web/src/api/types.ts`, implemented in `http.ts` and
  `fixture.ts`; the nav is hard-coded in `components/AppShell.tsx`.

## Behaviour (the changes, in order)

1. **Promote contracts.** Move every model listed above into `hope_core/schemas/` (one module
   per domain: `matching.py`, `profile_events.py`, `workflow.py`, `ingest.py`, `budget.py`,
   `dead_letter.py`), and export them from `hope_core.schemas`. Delete the service copies and
   update every import. No re-export shims. Field names and types stay the same unless listed in step 2.
2. **Contract field additions.**
   - `HitlDecision.role: str` (the role the approver acted in; required, used for separation of duties).
   - `HitlRequest.package_id: UUID | None = None` and `HitlRequest.channel: str | None = None` (HITL-5 only).
   - `ProposalFramework.drafted_by: str` (agent or user id).
   - `BudgetLedger.content_hash: str` (`hope_core.hashing.content_hash` of the ledger, excluding the field itself).
   - `Deadlines.internal_due: datetime | None` and `ExtractedDeadline.time_assumed: bool = False`.
   - `MatrixRow`: make `dimension_scores`, `eligibility` and `evidence_ids` always present (S05 fills them).
3. **Event types** in `hope_core/topics.py`: add `PROFILE_SOURCE_UPLOADED = "profile.source_uploaded"`,
   `FRAMEWORK_RECOMPUTE_REQUESTED = "framework.recompute_requested"`,
   `PARSE_REVIEW_RESOLVED = "opportunity.parse_review_resolved"`,
   `NOTIFICATION_DELIVERED = "notification.delivered"`,
   `MATRIX_DISPOSITION_SET = "recommendation.disposition_set"`, `WORKFLOW_STARTED = "workflow.started"`.
   Each gets a payload model in `hope_core.schemas` and a schema reference in the event registry.
4. **Lifecycle rollback rules.** Move the amendment / revalidation rollback table from
   `hope_workflow` into `hope_core/schemas/lifecycle.py` as `ROLLBACK_ON: dict[Trigger, OpportunityState]`,
   with `rollback_target(current, trigger)`. Workflow imports it.
5. **`hope_core/auth.py`, single tenant.** Move `Principal` (`tenant_id`, `user_id`, `roles`, `mfa`)
   here, plus `require_roles(*roles)`. `get_principal` no longer reads `X-Hope-Tenant`: it always
   sets `tenant_id` from a new required setting `HOPE_TENANT_ID` (`HopeSettings.tenant_id: UUID`),
   and reads only `X-Hope-User`, `X-Hope-Roles` and `X-Hope-MFA` (dev). The pillar and profile both
   use it. RLS and `tenant_tx` are unchanged. Remove the tenant header and
   `NEXT_PUBLIC_HOPE_TENANT_ID` from the web client, its env example and its tests. Matching's
   per-tenant `MatchingConfig` becomes one global config. S01 later swaps the header user for OIDC
   behind the same function.
6. **`hope_core/outbox.py`.** `write_event(tx, envelope)`: inserts a `PillarEnvelope` into
   `outbox` inside the caller's `tenant_tx` so the state change and its event commit together.
   Replace the pillar's and profile's private versions with it.
7. **`hope_core/claimcheck.py`.** `put_payload(store, tenant_id, obj) -> payload_ref` and
   `get_payload(store, payload_ref, model)`; S3/MinIO-backed, with an in-memory store for tests.
   Matching then accepts `payload_ref` events instead of rejecting them.
8. **`hope_core/errors.py`.** A `Problem` model (`type`, `title`, `status`, `code`, `detail`,
   plus extras) served as `application/problem+json`, and the exceptions `StaleArtifactError(current_hash)`
   -> 409 `stale_artifact`, `ConcurrencyError` -> 409 `version_conflict`, `NotFound` -> 404 `not_found`,
   `Forbidden` -> 403 `forbidden`. Add one FastAPI exception-handler installer and use it in the pillar app.
9. **Pillar API split.** Split `api/routes.py` into one module per prefix:
   `ingest.py`, `opportunities.py`, `matrix.py`, `workflows.py`, `frameworks.py`, `packages.py`.
   Also create empty, mounted routers (no routes yet) for `me.py`, `users.py`, `approvals.py`,
   `rules.py`, `parse_reviews.py`, `notifications.py`, `audit.py`, `narratives.py`, `verification.py`,
   `compliance.py`, `integrations.py`, `awards.py`, and `agencies.py`, which mounts
   `hope_profile.api.router` under `/v1`. Delete the pillar's duplicate profile routes; the
   profile router is the only owner of `/v1/agencies/**`.
10. **Per-router OpenAPI snapshots.** Replace `tests/snapshots/openapi.json` with
    `tests/snapshots/openapi/<router>.json`, each holding only that router's paths and the
    schemas those paths reference. Running `UPDATE_SNAPSHOTS=1` writes all of them.
11. **Recompute endpoint.** `POST /v1/frameworks/{id}/recompute` now emits
    `framework.recompute_requested` through the outbox and returns 202 (S06 adds the consumer).
12. **New service skeletons** (uv workspace members with `pyproject.toml`, `src/hope_<name>/__init__.py`,
    one import test): `notifications`, `drafting`, `verification`, `compliance`, `packaging`,
    `submission`, `integrations`, `awards`. Add their migration ranges to `AGENTS.md`:
    notifications `0700-0799`, drafting `0800-0899`, verification `0900-0999`, compliance
    `1000-1099`, packaging `1100-1199`, submission `1200-1299`, integrations `1300-1399`,
    awards `1400-1499`. The lexical migration order stays valid because the file names are zero-padded to 4 digits.
13. **Core skeletons:** `hope_core/providers/__init__.py` (S16) and `hope_core/telemetry/__init__.py` (S29), empty.
14. **Web API split.** Replace the single `HopeApi` with one client per feature under
    `apps/web/src/api/<feature>/` (`types.ts`, `http.ts`, `fixture.ts`, `index.ts`) for
    `session`, `matrix`, `opportunities`, `approvals`, `workflow`, `profile`; `api/client.ts`
    composes them. Behaviour is unchanged and every existing test still passes. Create empty
    folders with an `index.ts` for every other feature in `FOLDERS.md`.
15. **Web nav and route placeholders.** Add `apps/web/src/nav.ts` with every route in
    `SCREENS.md` (label, href, roles, `ready` flag). `AppShell` renders from it. Add a
    `page.tsx` for every route that shows a shared `ComingSoon` state until its screen spec
    replaces the file. Add an error-code mapper in `apps/web/src/lib/problem.ts` for the
    `Problem` model (`stale_artifact` shows "This changed since you opened it" and reloads).
16. **Regenerate** `packages/schemas` (`uv run hope-export-schemas && pnpm --filter @hope/schemas gen`).
17. **`db/migrations/0002_shared.sql`:** nothing yet. Add it only if step 6 needs an `outbox`
    column (for example `payload_ref`); otherwise don't create the file.

## Owns

```text
packages/core/**
packages/schemas/**
services/*/src/** (import updates and the moves listed above only)
services/*/tests/** (import updates; pillar snapshot split)
services/{notifications,drafting,verification,compliance,packaging,submission,integrations,awards}/**
apps/web/src/api/**, apps/web/src/nav.ts, apps/web/src/components/AppShell.tsx,
apps/web/src/components/ComingSoon.tsx, apps/web/src/lib/problem.ts, apps/web/src/app/**/page.tsx (placeholders only)
db/migrations/0002_shared.sql
pyproject.toml, uv.lock, AGENTS.md, docs/specs/README.md (status row)
```

## Acceptance criteria

- [ ] AC1 No service defines a model that another service imports; `grep -r "class .*Contract)" services` finds only service-private models.
- [ ] AC2 All fields from step 2 exist, are exported to JSON Schema and TS, and old payloads without the new optional fields still validate.
- [ ] AC3 The new event types exist, each with a registered payload schema.
- [ ] AC4 `rollback_target` covers every rollback the workflow used before, and the workflow tests pass unchanged.
- [ ] AC5 Pillar and profile share `hope_core.auth.get_principal`; requests carry no tenant, every row they write has `tenant_id = HOPE_TENANT_ID`, and RLS still blocks rows of any other tenant.
- [ ] AC6 `write_event` commits the event and the state change in one transaction, or neither (test rolls back mid-way).
- [ ] AC7 Matching accepts a `payload_ref` event and loads the payload via `get_payload`.
- [ ] AC8 A stale `artifact_hash` returns 409 `application/problem+json` with `code: "stale_artifact"` and `current_hash`.
- [ ] AC9 Every route that existed before still exists with the same method, path and response model, except the removed duplicate profile routes; the app mounts all routers listed in step 9.
- [ ] AC10 There is one OpenAPI snapshot per router, and a route change only changes its own router's snapshot.
- [ ] AC11 `POST /v1/frameworks/{id}/recompute` returns 202 and writes `framework.recompute_requested` to the outbox.
- [ ] AC12 The 8 new services are installed by `uv sync --all-packages`, and their import tests pass.
- [ ] AC13 The web app builds; every route in `SCREENS.md` resolves; unbuilt ones show `ComingSoon`; all existing web tests pass; the HTTP contract test still passes against the split snapshots.
- [ ] AC14 Generated schemas are fresh (the pre-commit check passes).
- [ ] AC15 All CI commands in `AGENTS.md` pass.

## Test plan

| AC | Test | Type |
|---|---|---|
| AC1 | `packages/core/tests/test_contract_locations.py::test_no_cross_service_contracts` (AST scan of `services/*/src`) | unit |
| AC2 | `packages/core/tests/test_schemas.py::test_new_fields_backward_compatible` | unit |
| AC3 | `packages/core/tests/test_topics.py::test_every_event_type_has_schema` | unit |
| AC4 | `packages/core/tests/test_lifecycle.py::test_rollback_targets` + existing workflow tests | unit |
| AC5 | `services/pillar/tests/test_api.py::test_configured_tenant_used`, `services/profile/tests/test_api.py::test_configured_tenant_used`, `packages/core/tests/test_db.py::test_rls_blocks_other_tenant` | api |
| AC6 | `packages/core/tests/test_outbox.py::test_event_and_state_commit_atomically` | db |
| AC7 | `services/matching/tests/test_agents.py::test_payload_ref_event_loaded` | unit |
| AC8 | `services/pillar/tests/test_api.py::test_stale_hash_problem_json` | api |
| AC9 | `services/pillar/tests/test_routes_inventory.py::test_route_inventory` (expected method+path list) | api |
| AC10 | `services/pillar/tests/test_openapi.py::test_router_snapshots` | api |
| AC11 | `services/pillar/tests/test_api.py::test_recompute_emits_event` | db |
| AC12 | `services/<new>/tests/test_<new>_import.py` | unit |
| AC13 | `apps/web/src/nav.test.ts`, existing Vitest suite, `pnpm --filter @hope/web build` | unit/build |
| AC14, AC15 | CI | ci |

## Out of scope

Multi-tenant features (tenant routing, tenant admin, per-tenant config). Any product behaviour: new endpoints with logic (beyond the recompute event), OIDC, real providers, UI screens.

## Decisions needed

- None blocking. The production embedding dimension is decided in S16.

## References

- Requests from the Phase 1 PRs: #2 (matching), #3 (profile), #4 (workflow), #5 (pillar), #7 (web), #8 (budget), #9 (ingestion).
- `AGENTS.md`, `docs/specs/FOLDERS.md`, `docs/specs/API.md`, `docs/specs/SCREENS.md`.
