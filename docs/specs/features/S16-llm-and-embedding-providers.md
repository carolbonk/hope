# S16: Real LLM and embedding providers, usage metering

> **Out of scope for the hackathon. Don't build this.** This spec belongs to the earlier design (the Phase 1 pipeline and the M0-M7 / S-spec roadmap). Hackathon agents build only H0-H5 (see [`README.md`](../README.md)). Keep this file for after the hackathon.

| | |
|---|---|
| Wave | 1 |
| Depends on | S00 |
| Screens | - |
| Migrations | `db/migrations/0010_model_usage.sql` |
| Blueprint | 2.3 (model routing), 8.3 (untrusted content), 8.5 (budgets, circuit breakers), 9 (LLM access, embeddings) |
| Status | Draft |

## Goal

Every agent already calls models through `ModelGateway`, but the only provider is
`MockProvider`. This spec adds production providers behind the same interface, so A2, A3,
A4, A5, A9 and A11 can run against a real model without any agent code changing. It also
records every call in a usage ledger with tokens and cost, and enforces a monthly spend cap.
Hope is free for nonprofits, so platform LLM spend has to be visible and bounded from day one.

## Recommendation (provider and embedding dimension)

| Role | Recommended | Why |
|---|---|---|
| Primary for `frontier`, `mid`, `small` | **OpenAI** Chat Completions with `response_format: {"type": "json_schema", "strict": true}` | Schema-constrained decoding matches `ModelGateway.structured(...)` directly. One API key also covers embeddings. |
| Secondary (failover) for `frontier`, `mid`, `small` | **Anthropic** Messages API with a forced tool call (`tool_choice: {"type": "tool"}`) whose `input_schema` is the response schema | Covers the blueprint's "at least two vendors" rule, and gives A11 the "different vendor" verifier it requires. |
| `embed` | **OpenAI `text-embedding-3-small` at 1536 dimensions** | Cheap, multilingual and good enough for passage retrieval. 1536 is under pgvector's 2,000-dimension limit for HNSW/IVFFlat indexes on `vector`, so `narrative_chunks` can get an ANN index later. |
| `rerank` | Not implemented in this spec | Matching uses BM25 + dense + RRF today (`hope_matching.alignment.rrf`). The tier stays unmapped and raises `TierNotConfiguredError`. |

**Embedding dimension: 1536.** Embeddings never fail over across vendors, because vectors
from different models live in different spaces. The `embed` tier has exactly one provider,
with retries but no cross-vendor failover. If it is down, embedding calls fail and the
caller's workflow pauses (blueprint 8.5), so we never quietly mix vector spaces.

Alternatives considered:
- **Anthropic primary + Voyage embeddings.** Comparable quality, but that's two vendors and two keys just for the MVP path.
- **Google Gemini.** Viable, but its JSON-schema support differs again. Keep it as a later third vendor.
- **Self-hosted (vLLM).** Deferred until volume justifies it (blueprint 13.4).

## Current state

- `packages/core/src/hope_core/model_gateway.py`:
  - `ModelTier` (`frontier`, `mid`, `small`, `embed`, `rerank`).
  - `RunBudget(max_calls=50, max_tokens=200_000)` with `charge(tokens)` raising `BudgetExceededError`.
  - The `Provider` protocol: `complete_json(tier, messages, schema) -> (dict, tokens)` and `embed(texts) -> list[list[float]]`.
  - `MockProvider` (responders keyed by schema title, deterministic 64-dimension hash embeddings).
  - `ModelGateway(providers)`. `structured()` tries providers in order and fails over on any exception except `LookupError`, charges the budget, and validates with Pydantic. A validation error raises and does **not** fail over. `embed()` always uses `providers[0]`.
  - `untrusted(text, label)` and `as_json`.
- `packages/core/src/hope_core/settings.py`: `HopeSettings.model_provider: str = "mock"` (`HOPE_MODEL_PROVIDER`). Nothing reads it.
- `packages/core/src/hope_core/providers/__init__.py` is an empty skeleton (S00, step 13).
- Gateways are built by hand in tests: `hope_matching.testing.gateway`, `hope_ingestion.testing`, profile tests.
- Embedding callers: `hope_matching.alignment.hybrid_search` (query + passages, in memory) and `hope_profile.memory.NarrativeMemory.index_asset` / `.search` (`narrative_chunks.embedding vector`, no fixed dimension, searched `WHERE vector_dims(embedding) = %(dims)s`).
- No usage or cost is recorded anywhere.

## Behaviour

1. **Factory.** `hope_core.providers.build_gateway(settings: ProviderSettings | None = None, meter: UsageMeter | None = None) -> ModelGateway`:
   - `HOPE_MODEL_PROVIDER=mock` (the default): returns `ModelGateway([MockProvider()])`, exactly as today. No key is needed and tests are unchanged.
   - `HOPE_MODEL_PROVIDER=openai`: returns a gateway whose providers are `[Metered(Breaker(Retry(OpenAIProvider)))]`, plus the Anthropic provider wrapped the same way when `HOPE_ANTHROPIC_API_KEY` is set.
   - A missing key for the selected provider raises `ProviderConfigError("HOPE_OPENAI_API_KEY is required for HOPE_MODEL_PROVIDER=openai")` at startup, never at first call.
   - At startup it also checks that `HOPE_EMBEDDING_DIM` equals the embedding model's configured dimension.
   - Services replace their hand-built gateways with `build_gateway()` in their own wiring code (each service's own PR, not this one).
2. **Tier to model mapping** comes from settings (below), never from code constants:
   - `HOPE_OPENAI_MODEL_FRONTIER`, `HOPE_OPENAI_MODEL_MID`, `HOPE_OPENAI_MODEL_SMALL` and `HOPE_OPENAI_EMBEDDING_MODEL` (default `text-embedding-3-small`).
   - `HOPE_ANTHROPIC_MODEL_FRONTIER`, `HOPE_ANTHROPIC_MODEL_MID` and `HOPE_ANTHROPIC_MODEL_SMALL`.
   - A tier with no model on a provider makes that provider raise `TierNotConfiguredError`. The gateway treats this like any other failure and moves on to the next provider.
3. **OpenAI structured call** (`providers/openai.py`):
   - `POST {HOPE_OPENAI_BASE_URL}/v1/chat/completions` with `model`, `messages` (role/content copied from `Message`), `temperature` (`HOPE_MODEL_TEMPERATURE`, default 0) and `response_format = {"type": "json_schema", "json_schema": {"name": schema["title"], "schema": strict_schema, "strict": true}}`.
   - `strict_schema = to_strict_schema(schema)` (`providers/schema.py`). It inlines `$defs`, sets `additionalProperties: false` on every object, and marks every property required. A field that was optional becomes `anyOf [T, null]`. Keywords the vendor's strict mode rejects are dropped. Pydantic re-validates the result, so dropped constraints such as `maxLength`, `minimum` and `maximum` are still enforced.
   - If `to_strict_schema` can't express a schema (for example recursive or open `dict[str, Any]` like `RuleDraft.rule`), the provider sends `"strict": false` with the original schema and relies on Pydantic validation.
   - The provider reads `choices[0].message.content`, `json.loads` it, and returns tokens = `usage.prompt_tokens + usage.completion_tokens`. If `choices[0].message.refusal` is set, it raises `ModelRefusalError` (no retry, gateway fails over).
4. **Anthropic structured call** (`providers/anthropic.py`):
   - `POST {HOPE_ANTHROPIC_BASE_URL}/v1/messages` with headers `x-api-key` and `anthropic-version: 2023-06-01`.
   - System messages are joined into the top-level `system`; other messages go into `messages`. The request sets `max_tokens` (`HOPE_ANTHROPIC_MAX_TOKENS`, default 4096), `tools=[{"name": "respond", "description": schema title, "input_schema": schema}]` and `tool_choice={"type": "tool", "name": "respond"}`.
   - The provider returns the `input` of the first `tool_use` block, with tokens = `usage.input_tokens + usage.output_tokens`. `stop_reason == "max_tokens"` raises `ModelTruncatedError`.
5. **Embeddings** (`providers/openai.py`):
   - `POST /v1/embeddings` with `model`, `input` (a batch of at most `HOPE_EMBEDDING_BATCH`, default 256, texts) and `dimensions = HOPE_EMBEDDING_DIM` (1536).
   - Results are ordered by `data[].index`. The provider checks that each vector length equals the dimension and that no input is empty (empty strings are rejected before the call with `ValueError`).
   - `AnthropicProvider.embed` raises `NotImplementedError`. The gateway never routes `embed` to it (see Shared contract additions: `ModelGateway(embedder=...)`).
6. **Retries** (`providers/http.py`, `Retry` wrapper):
   - `httpx.Client` with a timeout of `HOPE_MODEL_TIMEOUT_S` (default 60) per request.
   - Retries on 408/409/429/500/502/503/504 and on connection errors, with up to `HOPE_MODEL_MAX_ATTEMPTS` (default 3) attempts, exponential backoff (0.5 s × 2ⁿ ± 25 %), honouring `Retry-After` (and `retry-after-ms`).
   - No retry on 400/401/403/404/422. 401/403 raise `ProviderAuthError`, which is logged at error level without the key.
   - This mirrors `hope_ingestion.http.RetryPolicy`; the code is not shared, because core can't import a service.
7. **Circuit breaker** (`providers/breaker.py`, `Breaker` wrapper, one per provider instance):
   - After `HOPE_MODEL_BREAKER_FAILURES` (default 5) consecutive failures the breaker opens for `HOPE_MODEL_BREAKER_COOLDOWN_S` (default 60).
   - While open, calls raise `ProviderUnavailableError` immediately, so the gateway fails over.
   - After the cooldown, one trial call is let through (half-open). Success closes the breaker; failure re-opens it.
8. **Gateway failover** (shared change, see below):
   - `structured()` moves to the next provider on a provider error or on a Pydantic `ValidationError`. Each provider gets at most one validation retry: the same request plus a user message `"The previous output failed validation: <error summary>. Return JSON matching the schema."`. The error summary contains only field paths and error types, never input text.
   - If every provider fails, it raises `AllProvidersFailedError` (a subclass of today's `RuntimeError`), and Temporal activities let the workflow pause (blueprint 8.5).
9. **Metering** (`providers/metering.py`, `Metered` wrapper):
   - Every attempt writes one `UsageRecord`. That includes failures, validation retries and failover attempts.
   - Each record has: `tenant_id` (from `usage_context`), `run_id`, `agent`, `operation` (`structured` | `embed`), `tier`, `provider`, `model`, `input_tokens`, `output_tokens`, `cost_micro_usd`, `latency_ms`, `outcome` (`ok` | `error` | `validation_error` | `refused` | `budget_exceeded`), `error_class`, `request_id` (vendor request id header) and `created_at`.
   - Context comes from a `contextvars`-based `with usage_context(agent="A5", run_id=..., tenant_id=...)`. Calls outside any context are recorded with `agent="unknown"` and `tenant_id = HOPE_TENANT_ID`.
   - **No prompt or response content is stored.**
   - Sinks:
     - `PostgresUsageSink(system_url)` inserts into `model_usage` through `hope_system`, batched up to 50 rows or 2 s, and flushed on exit.
     - `InMemoryUsageSink` is for tests.
     - If a sink write fails, the call still succeeds. The failure is logged and counted, and the records are retried in the next batch, keeping at most 10,000 queued rows.
10. **Pricing** (`providers/pricing.py`):
    - Cost is computed only by code: `cost_micro_usd = ceil(input_tokens × input_price + output_tokens × output_price)`, with prices in micro-USD per token from a `PriceTable`.
    - The `PriceTable` loads from `HOPE_MODEL_PRICES` (JSON: `{"<model>": {"input_per_mtok_usd": "0.02", "output_per_mtok_usd": "0"}}`, decimal strings) and is parsed with `Decimal`.
    - A model with no price records `cost_micro_usd = NULL` and logs one warning per model per process. Budgets then fall back to token limits.
    - Platform cost is not grant money, so the "no LLM money" rule isn't affected. No model output is ever used to compute cost.
11. **Monthly cap** (`providers/metering.py`, `SpendGuard`):
    - Before each call, it reads the current calendar month's (UTC) total `cost_micro_usd` for the tenant from `model_usage`, cached for 60 s in-process.
    - If `HOPE_LLM_MONTHLY_BUDGET_USD` is set and the total is at or above it, the call raises `BudgetExceededError("monthly_budget")` without calling the vendor. The guard records an `outcome=budget_exceeded` row and emits a structured log event `llm.monthly_budget_exceeded` (S12/S29 can alert on it later).
    - Unset means no cap. Per-run limits stay in `RunBudget`.
12. **Untrusted content.** Providers send messages verbatim, so `untrusted()` wrapping still happens in agents. As defence in depth, the OpenAI and Anthropic providers check that no message with role `system` contains an `<untrusted` tag, and raise `ValueError` if one does. Untrusted text belongs in user messages only.
13. **Logging.** Keys never appear in logs, exceptions or `UsageRecord`. `ProviderSettings` uses `SecretStr` for keys, and `repr` is redacted.
14. **Usage report.** `python -m hope_core.providers.usage --month 2026-11` prints totals by agent, tier and model: calls, tokens, cost and error rate. It reads through `hope_system`.

## Contracts

- **Shared models used:** `ModelTier`, `Message`, `RunBudget`, `BudgetExceededError`, `ModelGateway`, `MockProvider` and `untrusted` from `hope_core.model_gateway`. `HopeSettings.tenant_id` from S00.
- **Shared contract additions** (for S00/C2; these touch `hope_core/model_gateway.py`, `packages/core/pyproject.toml` and `.env.example`):
  - `ModelGateway.__init__(self, providers: list[Provider], *, embedder: Provider | None = None)`. `embed()` uses `embedder` if given, otherwise `providers[0]` (today's behaviour). No cross-vendor failover for `embed`.
  - `ModelGateway.structured`: fail over on `pydantic.ValidationError`, with one validation retry per provider, as in step 8. Raise `AllProvidersFailedError(RuntimeError)` when all providers fail.
  - `ModelGateway.embed` charges an optional `budget: RunBudget | None = None` (tokens = sum of `len(text) // 4 + 1`, the estimate already used by `MockProvider`) so embedding-heavy runs are bounded.
  - `RunBudget.max_cost_micro_usd: int | None = None` and `charge(tokens: int, cost_micro_usd: int = 0)`, which raises when the cost exceeds the cap. `Metered` passes the cost through a new optional `Provider.last_cost_micro_usd: int | None` attribute that the gateway reads after each call.
  - New exception classes in `hope_core.model_gateway`: `AllProvidersFailedError`, `ProviderUnavailableError`, `TierNotConfiguredError`.
  - `packages/core/pyproject.toml`: add `httpx>=0.27` (already locked through `hope-ingestion`).
  - `.env.example`: `HOPE_OPENAI_API_KEY=`, `HOPE_ANTHROPIC_API_KEY=`, `HOPE_EMBEDDING_DIM=1536`, `HOPE_LLM_MONTHLY_BUDGET_USD=` and the model ID variables in step 2, all empty except the dimension.
  - `hope_core.schemas.usage.UsageRecord` (a Pydantic contract with the fields in step 9), so S29 dashboards and a future admin screen read one model.
- **Settings** (this spec's own `BaseSettings`, `hope_core/providers/settings.py`, prefix `HOPE_`):
  - `model_provider` (reused from `HopeSettings`, `mock` | `openai`).
  - `openai_api_key: SecretStr | None`, `openai_base_url = "https://api.openai.com"`.
  - `anthropic_api_key: SecretStr | None`, `anthropic_base_url = "https://api.anthropic.com"`.
  - The tier model IDs from step 2, `embedding_dim = 1536`, `embedding_batch = 256`, `model_temperature = 0.0`, `anthropic_max_tokens = 4096`, `model_timeout_s = 60`, `model_max_attempts = 3`, `model_breaker_failures = 5`, `model_breaker_cooldown_s = 60`, `model_prices: dict[str, ModelPrice] = {}` and `llm_monthly_budget_usd: Decimal | None = None`.
- **Events:** none. Usage is a ledger, not a pillar event, because it's high-volume and not consumed by agents.
- **Endpoints:** none. A usage screen is out of scope.
- **Database** (`0010_model_usage.sql`):

```sql
CREATE TABLE model_usage (
  usage_id        bigserial PRIMARY KEY,
  tenant_id       uuid REFERENCES tenants,          -- NULL = platform-level call
  run_id          text,
  agent           text NOT NULL,
  operation       text NOT NULL CHECK (operation IN ('structured','embed')),
  tier            text NOT NULL,
  provider        text NOT NULL,
  model           text NOT NULL,
  input_tokens    int  NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
  output_tokens   int  NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
  cost_micro_usd  bigint CHECK (cost_micro_usd >= 0),
  latency_ms      int  NOT NULL CHECK (latency_ms >= 0),
  outcome         text NOT NULL CHECK (outcome IN ('ok','error','validation_error','refused','budget_exceeded')),
  error_class     text,
  request_id      text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX model_usage_month ON model_usage (tenant_id, created_at);
CREATE INDEX model_usage_run ON model_usage (run_id) WHERE run_id IS NOT NULL;
CREATE TRIGGER model_usage_append_only BEFORE UPDATE OR DELETE ON model_usage
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
ALTER TABLE model_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_usage FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON model_usage USING (tenant_id = current_tenant())
  WITH CHECK (tenant_id = current_tenant());
GRANT SELECT ON model_usage TO hope_app;
GRANT SELECT, INSERT ON model_usage TO hope_system;
GRANT USAGE, SELECT ON SEQUENCE model_usage_usage_id_seq TO hope_system;
```

  `hope_system` bypasses RLS, as it does for the outbox relay today, so it can write platform rows with a NULL tenant.

## Owns

```text
packages/core/src/hope_core/providers/**
packages/core/tests/providers/**
db/migrations/0010_model_usage.sql
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 `build_gateway()` with the default settings returns a mock-only gateway, and every existing test passes unchanged.
- [ ] AC2 `build_gateway()` with `HOPE_MODEL_PROVIDER=openai` and no key raises `ProviderConfigError` naming the missing variable. A wrong `HOPE_EMBEDDING_DIM` also raises at build time.
- [ ] AC3 The OpenAI provider sends a `json_schema` `response_format` built from the Pydantic schema, and returns the parsed object and the token total. Recorded fixture: `chat_completion_ok.json`.
- [ ] AC4 `to_strict_schema` turns every Pydantic model used by agents today into a valid strict schema, or into a strict=false fallback for open dicts. The models are `RuleDraft`, `JudgeSample` and the ingestion and profile extraction models. Pydantic still rejects values that break the dropped constraints.
- [ ] AC5 A refusal or truncation raises the documented error, and the gateway fails over to the next provider.
- [ ] AC6 The Anthropic provider forces the `respond` tool, puts system messages in `system`, and returns the `tool_use.input`.
- [ ] AC7 Embeddings are batched at 256, re-ordered by `index`, and length-checked against the configured dimension (1536). Empty input raises before any HTTP call.
- [ ] AC8 Retries happen on 429/5xx and honour `Retry-After`; there's no retry on 400/401. Keys never appear in logs or exception messages.
- [ ] AC9 After 5 consecutive failures the breaker opens. Calls then fail fast and the gateway uses the secondary provider. After the cooldown, a successful trial closes the breaker.
- [ ] AC10 A `ValidationError` from the primary triggers one validation retry, then failover. When every provider fails, `AllProvidersFailedError` is raised.
- [ ] AC11 Every attempt, including failed ones, writes one `UsageRecord` with the context's agent, run and tenant, and no prompt or response text.
- [ ] AC12 Cost is computed from the price table with `Decimal` and rounded up to whole micro-USD. An unknown model records NULL cost and logs one warning.
- [ ] AC13 When the month's spend reaches `HOPE_LLM_MONTHLY_BUDGET_USD`, the next call raises `BudgetExceededError("monthly_budget")` without an HTTP request and records an `outcome=budget_exceeded` row.
- [ ] AC14 `model_usage` is append-only and RLS-scoped. `hope_app` sees only its tenant's rows and can't insert.
- [ ] AC15 A system message containing `<untrusted` is rejected.
- [ ] AC16 All CI commands in `AGENTS.md` pass offline, with no API keys.

## Test plan

All HTTP is faked with `httpx.MockTransport` and recorded JSON under `packages/core/tests/providers/fixtures/`. No network.

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `packages/core/tests/providers/test_factory.py::test_default_is_mock` | unit |
| AC2 | `test_factory.py::test_missing_key_fails_fast`, `test_factory.py::test_embedding_dim_mismatch` | unit |
| AC3 | `test_openai.py::test_structured_request_and_parse` | unit |
| AC4 | `test_schema.py::test_strict_schema_for_agent_models` (parametrized over the models listed), `test_schema.py::test_dropped_constraints_still_validated` | unit/property |
| AC5 | `test_openai.py::test_refusal_fails_over`, `test_anthropic.py::test_max_tokens_truncation` | unit |
| AC6 | `test_anthropic.py::test_forced_tool_call` | unit |
| AC7 | `test_openai.py::test_embed_batching_order_and_dim`, `test_openai.py::test_embed_rejects_empty` | unit |
| AC8 | `test_http.py::test_retry_after_and_no_retry_on_4xx`, `test_http.py::test_keys_redacted` | unit |
| AC9 | `test_breaker.py::test_open_half_open_close` (fake clock) | unit |
| AC10 | `test_gateway_failover.py::test_validation_retry_then_failover` | unit |
| AC11 | `test_metering.py::test_record_per_attempt_without_content` | unit |
| AC12 | `test_pricing.py::test_cost_rounding_and_unknown_model` | unit |
| AC13 | `test_metering.py::test_monthly_budget_blocks_call` (db), using `migrated_db` | db |
| AC14 | `test_usage_db.py::test_append_only_and_rls` | db |
| AC15 | `test_openai.py::test_untrusted_in_system_rejected` | unit |
| AC16 | CI | ci |

Commands: the CI commands in `AGENTS.md`. An optional live smoke test,
`HOPE_LIVE_MODEL_TESTS=1 uv run pytest packages/core/tests/providers -m live`, is skipped by default and never runs in CI.

## Out of scope

- Rerank providers.
- Self-hosted models, and fine-tuned LoRA models (blueprint A2, A9).
- Per-tenant routing and data residency (the MVP is single-tenant).
- Re-embedding existing `narrative_chunks` rows. That belongs to the profile owner; see Decisions.
- Wiring `build_gateway()` into each service. Each service does that in its own spec (S07, S17, S18 and so on).
- A usage UI.
- OpenTelemetry export of usage. S29 reads `model_usage` or wraps the `Metered` sink.

## Decisions needed

1. **Provider.** Recommended default: OpenAI as primary (chat + embeddings) and Anthropic as secondary (and as the A11 verifier vendor). The alternative is Anthropic primary + Voyage embeddings.
2. **Embedding model and dimension.** Recommended default: `text-embedding-3-small` at 1536. Changing it later means re-embedding every `narrative_chunks` row, because profile search already filters on `vector_dims`.
3. **Model IDs per tier.** Recommended default: set them in deployment config (S28), not in code. Pin dated model snapshots, and record the chosen IDs in `docs/architecture/blueprint.md` 9 when S28 lands. Verify names and prices against the vendors' current model lists at implementation time.
4. **Data handling.** Nonprofit profile data is confidential. Recommended default: use API organisations with training opt-out (the default for both vendors' APIs), and request zero-data-retention where the vendor offers it before any real agency data is sent. This needs Carolaine's sign-off.
5. **Monthly cap value.** Recommended default: `HOPE_LLM_MONTHLY_BUDGET_USD=200` for the first production deployment, revisited after a month of `model_usage` data.
6. **Re-embedding on switch-over from the mock (64 dimensions) to 1536.** Recommended default: the profile owner (S09) adds a one-off `reindex_all()` command. Until it runs, `NarrativeMemory.search` just finds no old chunks, because of its `vector_dims` filter.

## References

- `packages/core/src/hope_core/model_gateway.py`, `packages/core/src/hope_core/settings.py`, `services/profile/src/hope_profile/memory.py`, `services/matching/src/hope_matching/alignment.py`, `services/ingestion/src/hope_ingestion/http.py`.
- Blueprint 2.3, 8.3, 8.5, 9, 13.
- OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs; Embeddings: https://platform.openai.com/docs/guides/embeddings.
- Anthropic tool use: https://docs.anthropic.com/en/docs/build-with-claude/tool-use.
- pgvector index dimension limits: https://github.com/pgvector/pgvector#indexing.
