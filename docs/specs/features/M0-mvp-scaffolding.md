# M0: MVP scaffolding (hackathon)

> **Out of scope for the hackathon. Don't build this.** This spec belongs to the earlier design (the Phase 1 pipeline and the M0-M7 / S-spec roadmap). Hackathon agents build only H0-H5 (see [`README.md`](../README.md)). Keep this file for after the hackathon.

| | |
|---|---|
| Wave | MVP, runs alone first (about 3 h) |
| Depends on | - |
| Screens | app shell only |
| Migrations | `0002_mvp.sql` (only if needed) |
| Replaces for the MVP | S00 (full version kept for later) |
| Status | Ready |

## Goal

Make every shared change M1-M7 need, so seven agents can work in parallel without touching
the same file. No product features. This is a trimmed S00: follow S00's steps **3, 8, 9, 10,
11, 14, 16** as written there, with the changes and additions below. Skip S00 steps 1, 4, 6,
7, 12, 13, 17.

## Behaviour

1. **Contracts M1-M7 share** (S00 step 2, trimmed): add `HitlDecision.role: str`,
   `HitlRequest.package_id: UUID | None`, `ProposalFramework.drafted_by: str`,
   `BudgetLedger.content_hash: str`. Make `MatrixRow.eligibility`, `scores`, `evidence_ids`
   always present. Promote `hope_matching.contracts.EligibilityResult` and `AlignmentAssessment` to
   `hope_core.schemas.matching`. Rename the workflow's same-named activity models to
   `EligibilityActivityResult` / `AlignmentActivityResult` to avoid the name clash.
2. **Roles.** Add a `Role` StrEnum in `hope_core/auth.py`: `development_director`, `program_director`,
   `finance_director`, `executive_director`, `aor` (authorized organizational representative),
   `admin`. Gate approver roles stay: HITL-1 `development_director` or `executive_director`;
   HITL-2 `finance_director`; HITL-4 `executive_director`; HITL-5 `aor`. Web fixtures, the workflow
   and the web env use these names.
3. **Single tenant + demo user** (replaces S00 step 5). `Principal`, `get_principal` and
   `require_roles` move to `hope_core/auth.py`. `tenant_id` always comes from
   `HOPE_TENANT_ID`. The user comes from `X-Hope-User` and the roles from `X-Hope-Roles`; with no
   headers, the default is `HOPE_DEMO_USER` with all roles. Add
   `GET /v1/me` (in `api/me.py`): `{ "user_id", "display_name", "roles": [...], "agency_id", "agency_name" }`,
   where `agency_id` is the one agency (`HOPE_AGENCY_ID`). Web: drop the tenant env and header,
   and add a **role switcher** in the app-shell user menu (stored in `localStorage`, sent as
   `X-Hope-Roles`) so the demo can act as each approver.
4. **OpenAI provider.** Add `OpenAIProvider` in `hope_core/model_gateway.py`, implementing the
   existing `Provider` protocol with structured output (JSON schema response format). Settings:
   `HOPE_OPENAI_API_KEY`, `HOPE_OPENAI_MODEL` (default `gpt-4o-mini`), `HOPE_OPENAI_EMBED_MODEL`
   (default `text-embedding-3-small`). Add `default_gateway()`, which returns OpenAI when the key
   is set and `MockProvider` otherwise. Log tokens and cost per call (`usage` table not needed).
   Add the `openai` dependency to `packages/core`.
5. **Pillar routers** (S00 step 9, MVP set only): split `routes.py` into `ingest.py`,
   `opportunities.py`, `matrix.py`, `workflows.py`, `frameworks.py`, `packages.py`, plus new
   empty mounted routers `me.py`, `approvals.py`, `narratives.py`, `dashboard.py`. Mount
   `hope_profile.api.router` and delete the pillar's duplicate profile routes. The router
   owners are M1 `opportunities.py`, M2 `matrix.py`, M3 `approvals.py`, M4 `workflows.py`
   (including `POST /v1/opportunities/{id}/pursue`), M5 `frameworks.py`, M6 `narratives.py`,
   and M7 `packages.py` + `dashboard.py`.
6. **Service ports.** Create the `services/drafting` (`hope_drafting`) and `services/packaging`
   (`hope_packaging`) workspace members. Each gets one module, `ports.py`, with final
   signatures that raise `NotImplementedError`:
   - `hope_drafting.ports.draft_sections(framework: ProposalFramework, opportunity: GrantOpportunity, profile: AgencyProfile, ledger: BudgetLedger | None) -> list[NarrativeSection]`
   - `hope_packaging.ports.build_package(framework_id: UUID) -> PackageManifest`
   - `hope_budget.ports.compute_for_framework(framework_id: UUID) -> BudgetLedger` (wraps the existing engine; M5 fills it in)

   Add `NarrativeSection` (`section_id`, `title`, `body_md`, `placeholders: list[str]`,
   `evidence_ids`, `content_hash`) and `PackageManifest` (`package_id`, `framework_id`,
   `files: [{name, sha256, bytes}]`, `content_hash`) to `hope_core.schemas`.
7. **Demo runner.** Add `make demo`, which starts Postgres (and Redpanda, if it's needed),
   migrates, runs `uv run hope-demo-seed`, and starts the pillar API (`:8000`), the workflow
   worker and the web app (`:3000`, with the API URL set). `hope-demo-seed` (in `hope_core/demo.py`)
   creates the tenant and the agency, then calls `seed()` from each installed
   `hope_<service>.demo` module that exists. Seeding is idempotent.
8. **Web.** Do S00 step 14 (per-feature API clients) for `session`, `matrix`, `opportunities`,
   `approvals`, `workflow`, `profile`, `budget`, `proposal`, `packages` and `dashboard`. Add
   `apps/web/src/nav.ts` with the MVP routes (Dashboard `/`, Matrix, Approvals, Workflows,
   Profile), plus a `ComingSoon` `page.tsx` placeholder for `/opportunities/[opportunityId]`,
   `/approvals/[requestId]`, `/workflows/[workflowId]`, `/frameworks/[frameworkId]/budget`,
   `/frameworks/[frameworkId]/draft` and `/packages/[packageId]`. Add `lib/problem.ts`, the
   shared `Drawer` primitive (SC03 section 5) and `Toast` in `components/ui`.

## Owns

`packages/core/**`, `packages/schemas/**`, `services/pillar/src/hope_pillar/api/**` and its tests and
snapshots, `services/drafting/**`, `services/packaging/**`, `services/budget/src/hope_budget/ports.py`,
import-only edits in other services, `apps/web/src/{api,components,lib,nav.ts}/**`,
`apps/web/src/app/**/page.tsx` (placeholders), `apps/web/.env.example`, `Makefile`, `pyproject.toml`,
`uv.lock`, `infra/docker-compose.yml`, `AGENTS.md`, `docs/specs/README.md` (status row).

## Acceptance criteria

- [ ] AC1 All existing tests pass; CI is green.
- [ ] AC2 `GET /v1/me` returns the demo user, all roles and the agency, with no headers; `X-Hope-Roles: finance_director` limits the roles.
- [ ] AC3 With no `HOPE_OPENAI_API_KEY`, `default_gateway()` is the mock; with a key, an `OpenAIProvider` structured call returns a validated model (tested with a mocked HTTP transport, so there's no network in CI).
- [ ] AC4 Every router listed in step 5 is mounted; there is one OpenAPI snapshot per router; all previous routes still exist except the removed duplicate profile routes.
- [ ] AC5 Calling a port raises `NotImplementedError`, and its signature matches step 6 (mypy).
- [ ] AC6 `make demo` on a clean checkout brings the stack up, and `curl :8000/v1/me` and `:3000/` both return 200; running the seed twice creates no duplicates.
- [ ] AC7 The web app renders the nav from `nav.ts`; the role switcher changes the `X-Hope-Roles` header; placeholders render `ComingSoon`.
- [ ] AC8 A stale artifact hash returns 409 problem+json with `code: "stale_artifact"` and `current_hash`.

## Test plan

| AC | Test |
|---|---|
| AC1 | CI |
| AC2 | `services/pillar/tests/test_me.py::test_me_defaults`, `::test_roles_header` |
| AC3 | `packages/core/tests/test_openai_provider.py::test_default_is_mock`, `::test_structured_call` (httpx `MockTransport`) |
| AC4 | `services/pillar/tests/test_routes_inventory.py`, `test_openapi.py::test_router_snapshots` |
| AC5 | `services/drafting/tests/test_drafting_ports.py`, `services/packaging/tests/test_packaging_ports.py` |
| AC6 | manual: run `make demo` twice and note the result in the PR |
| AC7 | `apps/web/src/nav.test.ts`, `components/RoleSwitcher.test.tsx` |
| AC8 | `services/pillar/tests/test_api.py::test_stale_hash_problem_json` |

## Out of scope

Real login, multiple tenants, outbox/claim-check refactors, the cloud deploy.
