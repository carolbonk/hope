# AGENTS.md

Working rules for humans and AI agents in this repo. The architecture is in
`docs/architecture/blueprint.md`; section numbers below refer to it.

## Hackathon scope (read first)

Build only the H0-H5 specs in `docs/specs/README.md`. Everything from the earlier design is out of scope, so
don't build, extend or wire it:

- **Specs:** `docs/specs/features/M*.md`, all `S*.md` specs, and every screen spec other than SC00, SC01, SC09, SC11 and SC24-SC28.
- **Architecture:** the pipeline agents A0-A12, Temporal lifecycle workflow, HITL gates, Kafka flows and budget engine in `docs/architecture/blueprint.md`.
- **Services:** `services/ingestion` (import its parsing validators only, as H2 says), `services/matching`, `services/budget` and
  `services/workflow` stay as they are. The services in scope are `services/pillar` (API host), `services/profile` (H1) and
  `services/discovery` (H2).
- **Web:** no screens outside `/hope/*`, `/onboarding` and `/login`.

## Layout and ownership

Each area has one owner per phase (the table below is the Phase 1 split; during the hackathon the H0-H5 specs' `Owns` lists decide). Stay inside your folders; anything outside needs the
orchestrator.

| Path | Owner | Blueprint |
|---|---|---|
| `packages/core/` (`hope_core`) | orchestrator | 2.3, 5, 7.5 |
| `packages/schemas/` (generated JSON Schema + `@hope/schemas` TS types) | generated, orchestrator | 5 |
| `db/migrations/0001-0099` | orchestrator | 7.3 |
| `infra/`, `.github/`, root `pyproject.toml`, `uv.lock`, `package.json`, `pnpm-lock.yaml` | orchestrator | 11 |
| `services/pillar/`, `db/migrations/0100-0199` | pillar | 7 |
| `services/ingestion/`, `db/migrations/0200-0299` | ingestion | 2.2 A1/A2, 6.1, 8.5 |
| `services/profile/`, `db/migrations/0300-0399` | profile | 2.2 A3, 4.4 HITL-0 |
| `services/matching/`, `db/migrations/0400-0499` | matching | 2.2 A4/A5/A6, 5.3 |
| `services/budget/`, `db/migrations/0500-0599` | budget | 2.2 A7, 8.1 |
| `services/workflow/`, `db/migrations/0600-0699` | workflow | 4, 2.2 A0/A12 |
| `apps/web/` | web | 4.4, 5.3 |

## Rules

- **Contracts live in `hope_core.schemas`.** Never redefine a contract model in a service.
  If you need a field, ask the orchestrator to add it there. After a contract change run
  `uv run hope-export-schemas && pnpm --filter @hope/schemas gen` and commit the outputs
  (CI fails on stale output).
- **Reuse before writing.** Use `hope_core.money.Money` (integer minor units, never floats),
  `hope_core.hashing.content_hash`, `hope_core.envelope.PillarEnvelope`,
  `hope_core.topics.Topic/EventType`, `hope_core.schemas.lifecycle` (the only state machine),
  `hope_core.model_gateway.ModelGateway` and `hope_core.testing.factories`.
- **LLMs suggest, code decides.** Agents call `ModelGateway.structured(...)` with a Pydantic
  response model. No LLM output contains money amounts or makes a lifecycle transition.
  Wrap ingested text with `model_gateway.untrusted(...)`.
- **Tenancy.** Tenant data is read and written through `hope_core.db.tenant_tx` as `hope_app`
  (RLS enforced). Only cross-tenant workers use `HOPE_DATABASE_SYSTEM_URL` (`hope_system`).
- **Migrations** are plain SQL in `db/migrations`, applied in lexical order by
  `uv run hope-migrate`. Use only your number range. Never edit a file that has been merged.
- **Dependencies.** Each service declares its own deps in its `pyproject.toml`. If you add one,
  run `uv lock`. On a `uv.lock` merge conflict, take main's version and rerun `uv lock`.
- **Tests run without network or API keys** (MockProvider, InMemoryPillar). DB tests use the
  `migrated_db` fixture pattern from `packages/core/tests/conftest.py` and `@pytest.mark.db`.

## Web app (`apps/web`, after PR #34)

- The Hope UI is built: the zip frontend under `/hope/*` and SC11 `/onboarding`. Don't rebuild screens. Keep the
  liquid-glass `app/globals.css` and `features/onboarding/**`; map any new colour names onto glass tokens.
- There is no `src/`: `app/`, `components/`, `lib/`, `features/`, `api/` sit at the root, and `@/*` maps to `./*`.
- The seam: pages call `useHope()` / `useOpportunities()` only. Backends plug in through `lib/hope/sync/<name>.ts`
  (profile H1, opportunities H2, decisions H3) without changing hook signatures or pages.
  H0 creates the three no-op stubs and wires them once, before H1-H5 start. H1-H3 replace only their stub's body
  (signatures are in H0, section 3).
- H4/H5 are browser state plus `POST /api/hope/draft`. The OpenAI key is server-only (`OPENAI_API_KEY`).
- Web checks: `pnpm --filter @hope/web typecheck && pnpm --filter @hope/web lint && pnpm --filter @hope/web test`.
  Don't commit the generated `apps/web/AGENTS.md` / `CLAUDE.md`.

## Commands

```bash
uv sync --all-packages                       # Python deps (workspace)
pnpm install                                 # TS deps
docker compose -f infra/docker-compose.yml up -d
uv run hope-migrate                          # apply SQL migrations
uv run ruff format . && uv run ruff check .  # lint
uv run mypy packages/core/src services       # types (strict)
uv run pytest -q                             # tests
pre-commit install                           # git hooks (ruff + schema freshness)
```

## PRs

One PR per area against `main`. Never stack PRs. Keep CI green.
