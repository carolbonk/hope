# H0: Hackathon scaffolding

| | |
|---|---|
| Wave | Hackathon. Runs alone first (about 3-4 h) and merges before H1-H5 branch |
| Depends on | - (the Hope frontend from PR #34 is already on `main`) |
| Screens | [SC00](../screens/SC00-app-shell.md) app shell: adds the session guard and Sign out to the built shell; `/` already redirects |
| Migrations | `0002_hackathon.sql` |
| Status | Ready |

## Goal

Put the shared backend pieces and the web seams in place so H1-H3 can plug their backends into the
**existing** UI in parallel, without editing the same file:

- invite-code auth, `GET /v1/me` and a session guard around `/hope/*`;
- the shared contracts, tables and store functions H1-H3 read and write;
- the web tools, the OpenAI provider and the job runner H2 uses;
- one API router per spec, `services/discovery` (skeleton) and `make demo`;
- in `apps/web`: `api/http.ts`, `api/session/` and `lib/hope/sync/` with one no-op adapter per backend.

There is no product logic beyond auth. H0 builds no screen and restyles nothing.

## What already exists (don't rebuild)

- **The UI** is the Hope frontend under `/hope/*` (PR #34): `/hope/discover`, `/hope/saved`, `/hope/deadlines`,
  `/hope/profile`, `/hope/applications/[oppId]`, plus SC11 `/onboarding` (PR #24). `/` and `/hope` redirect
  to `/hope/discover` (`app/page.tsx`, `app/hope/page.tsx`).
- **The shell** is `app/hope/layout.tsx` (`HopeNav` + page + `HopeFooter` from `components/hope/ui.tsx`), with the
  EN/ES `LanguageToggle`. See SC00.
- **Browser state:** `useHope()` (`lib/hope/store.ts`) over `localStorage` key `hope:state:v1`
  (`{ version: 1, profile, decisions, history, applications }`), and `useOpportunities()` (`lib/hope/opportunities.ts`)
  over the demo catalog (`lib/hope/demo.ts`). H4/H5 run entirely on this state plus `POST /api/hope/draft`.
- **Layout:** `apps/web` has no `src/`. `app/`, `components/`, `lib/`, `features/`, `api/` sit at the package root
  and `@/*` maps to `./*`.
- **Design:** the liquid-glass `app/globals.css` and `components/ui/**`. H0 never changes them, and never changes
  `features/onboarding/**`.
- **Clients:** `api/profile` and `api/onboarding` already switch between an offline fixture and HTTP on
  `NEXT_PUBLIC_HOPE_API_URL`; H1 points them at the real backend.

## Behaviour

### 1. Single tenant and auth (backend)

- `HopeSettings` (`hope_core/settings.py`) gains:
  - `tenant_id: UUID` (`HOPE_TENANT_ID`), `agency_id: UUID` (`HOPE_AGENCY_ID`);
  - `session_secret` (`HOPE_SESSION_SECRET`), `invite_code` (`HOPE_INVITE_CODE`, optional);
  - `cookie_secure` (`HOPE_COOKIE_SECURE`, default `true`), `web_origin` (`HOPE_WEB_ORIGIN`, default `http://localhost:3000`);
  - `openai_api_key` (`HOPE_OPENAI_API_KEY`, optional), `openai_model` (default `gpt-4o-mini`),
    `openai_search_model` (default `gpt-4o-mini`), `openai_embed_model` (default `text-embedding-3-small`);
  - `jobs_inline` (`HOPE_JOBS_INLINE`, default `false`).
- The server always uses `settings.tenant_id`. No URL, header or body carries a tenant. There's no tenant picker.
- Table `users` (`user_id uuid pk`, `tenant_id`, `email citext`, `password_hash`, `display_name`, `created_at`,
  `unique (tenant_id, email)`), with RLS like every other tenant table. Passwords are hashed with `argon2-cffi`.
- `services/pillar/src/hope_pillar/api/auth.py` (replaces today's header-based principal):
  - `POST /v1/auth/signup` `{email, password, display_name, invite_code}` returns 201 `{user}` and sets the cookie.
    - It succeeds only when `HOPE_INVITE_CODE` is set (at least 16 characters) and `invite_code` matches it
      (`hmac.compare_digest`). Otherwise 403 `signup_closed`, whatever the email.
    - There is no email or domain allowlist: Hope doesn't verify mailbox ownership, so an email proves nothing.
    - Password shorter than 8 characters: 422 `weak_password` with `errors[{field: "password", code, message}]`.
    - Email already registered: 409 `email_taken`.
  - `POST /v1/auth/login` `{email, password}` returns 200 `{user}` and sets the cookie. A wrong email and a wrong
    password both return the same 401 `invalid_credentials`.
  - `POST /v1/auth/logout` returns 204 and clears the cookie.
  - `{user}` is `{user_id, email, display_name}`.
  - The cookie is `hope_session`: `itsdangerous` `URLSafeTimedSerializer` over `{user_id}`, `HttpOnly`,
    `SameSite=Lax`, `Secure` unless `HOPE_COOKIE_SECURE=false`, `Max-Age` 14 days. Only `make demo` turns `Secure` off.
- `hope_core/auth.py`: `Principal(tenant_id, user_id, email, display_name)` and the FastAPI dependency
  `get_principal`. It reads and verifies the cookie, loads the user, and returns 401 `not_signed_in` when there is no
  valid session. `tenant_id` always comes from settings. The pillar and profile routers use it. There are no roles:
  every signed-in user can do everything.
- `GET /v1/me` (`api/me.py`) returns `{user_id, email, display_name, agency_id, onboarding_complete}`.
  `onboarding_complete` is computed by code: the current profile has a non-empty mission statement and at least one
  program.
- Errors are `application/problem+json` `{type, title, status, code}`; 422s add `errors[{field, code, message}]`.
- CORS: `CORSMiddleware` allows only `settings.web_origin`, with credentials. Web (`:3000`) and API (`:8000`) on
  `localhost` are the same site, so the `Lax` cookie is sent. A deployment keeps both on one registrable domain.
- Response shapes match `contracts/mocks/w1/**` exactly (same keys and value types).

### 2. Session in the web app (`api/http.ts`, `api/session/`)

- `api/http.ts`:
  - `API_URL = process.env.NEXT_PUBLIC_HOPE_API_URL ?? ""` and `online = API_URL !== ""`.
  - `class ProblemError extends Error { status; code; errors: FieldError[] }` and `type FieldError = {field, code, message}`.
  - `apiFetch<T>(path, init?)`: `fetch(API_URL + path, { credentials: "include", ... })`, JSON in and out.
    - A problem response throws `ProblemError(status, body.code ?? "http_<status>", body.detail ?? body.title, body.errors ?? [])`.
    - A network failure throws `ProblemError(0, "network_error", ...)`. A 204 returns `undefined`.
    - A 401 also dispatches the window event `hope:unauthorized` before throwing.
  - `api/profile/types.ts` re-exports `ProblemError` / `FieldError` from here (one-line H0 edit, so there is one class).
- `api/session/index.ts`:
  - `me()`, `login({email, password})`, `signup({email, password, display_name, invite_code})`, `logout()`;
    types `User` and `Me` mirror `contracts/mocks/w1`.
  - `useSession()` returns `{ status: "offline" | "loading" | "signed_out" | "unreachable" | "ready", me?, retry }`.
    It shares one cached `me()` across components, refetches on window focus, and moves to `signed_out` on `hope:unauthorized`.
  - `invalidateSession()`, which SC01 and SC11 call after sign-in or onboarding.
  - `safeNext(next)` returns `next` only when it starts with `/` and not `//`; otherwise `/hope/discover`. SC01 uses it.
- `api/session/RequireSession.tsx` (client component), mounted by `app/hope/layout.tsx` around the page:
  - **Offline** (`online` is false): it renders the children and makes no request. The demo works exactly as today.
  - **Online:** it follows `useSession()`. The states, redirects and copy are in SC00 sections 6-7.
  - It only wraps `/hope/*`. `/login` (H1) and `/onboarding` sit outside that layout, so neither ever redirects to itself.
    SC01 itself sends a signed-in user from `/login` to `safeNext(next)` (or `/onboarding`).
- Signing out never clears `hope:state:v1`: that browser state holds the H4/H5 work.

### 3. The sync seam (`lib/hope/sync/`)

Pages call only `useHope()` and `useOpportunities()`. A backend plugs in through its adapter and nothing else.
H0 creates every adapter as a no-op with the exact signature below, and wires the calls once, before H1-H5 start.
After H0, each adapter file belongs to its spec. Keep the signatures.

| File (owner after H0) | Signature | No-op body | Called from |
|---|---|---|---|
| `sync/profile.ts` (H1) | `load(): Promise<OrgProfile \| null>`; `save(profile: OrgProfile): Promise<void>` | `null`; resolve | `load` from `HopeSync` once on mount; `save` from `useHope().saveProfile` after the local write |
| `sync/opportunities.ts` (H2) | `useRemoteOpportunities(): Opportunity[] \| null` | `null` | `useOpportunities()` returns `remote ?? demoOpportunities(today)`; H2 may change that merge inside its own file |
| `sync/decisions.ts` (H3) | `onDecide(opp: Opportunity, decision: "saved" \| "passed"): void`; `onUndo(oppId: string): void` | nothing | `useHope().decide` / `undo`, after the local update |
| `sync/index.ts` (H0) | re-exports the three adapters and `online`; `HopeSync()` component (renders `null`) | - | mounted once in `app/hope/layout.tsx` |

- Adapters run only when `online`. They never throw into a page: they catch, `console.warn`, and leave the browser
  state as it is. The browser record stays the source for the workspace (H4/H5).
- `HopeSync` applies a loaded profile through a new `useHope().hydrateProfile(p)`, which writes the profile but does
  not call `sync/profile.save` (so loading never echoes back).
- One-time H0 edits outside its own files (merged before H1-H5 branch, so no conflict):
  `lib/hope/store.ts` (`hydrateProfile` + the three call sites), `lib/hope/opportunities.ts` (the `remote ?? demo` line),
  `api/profile/types.ts` (the re-export), `lib/hope/i18n.ts` (new `session.*` keys in `en` and `es`; add, never rename).
  No page file changes. Hook signatures stay the same.
- Money: the UI's `Opportunity.amountMin/amountMax` and `OrgProfile.annualBudget` are whole currency units. On the wire
  money is `{amount_minor, currency}` (integer minor units). The adapters convert (`amount_minor / 100`), never the pages.

### 4. Shared contracts (`hope_core/schemas/hackathon.py`, exported from `hope_core.schemas`)

```python
class Citation(Contract):
    citation_id: str  # "c1", "c2"... unique within its parent
    kind: Literal["web", "profile"]
    url: str | None = None  # web
    title: str | None = None  # web page title
    quote: str  # exact supporting text, <= 500 chars
    profile_path: str | None = None  # profile, e.g. "mission.mission_statement"
    retrieved_at: datetime | None = None


class DiscoveryProgress(Contract):
    queries_total: int = 0
    queries_done: int = 0
    pages_read: int = 0
    candidates_found: int = 0
    current_step: str = ""  # "Searching: youth mentoring grants Washington"


class DiscoveryJob(Contract):
    job_id: UUID
    status: Literal["queued", "running", "done", "failed"]
    queries: list[str] = []
    progress: DiscoveryProgress
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class GrantCandidate(Contract):
    grant_id: UUID
    title: str
    funder: str
    url: str  # canonical grant page
    summary: str  # 1-3 plain-English sentences; may contain [cN] markers
    amount_text: str | None = None  # quoted, e.g. "up to $50,000"
    amount_max: Money | None = None  # parsed by code from amount_text, integer minor units
    deadline_text: str | None = None
    deadline: date | None = None  # parsed by code; None for rolling or unknown
    eligibility_summary: str | None = None
    fit_score: int = Field(ge=0, le=100)
    fit_reasons: list[str] = []  # <= 140 chars each, then [cN] markers; no marker = "Unverified"
    concerns: list[str] = []  # same marker rule
    citations: list[Citation] = []
    status: Literal["new", "saved", "passed"] = "new"
    found_by_job_id: UUID | None = None
    discovered_at: datetime
```

Also:
- `Mission.values: list[str] = []`; `AgencyProfile.service_area: list[str] = []` if missing (state or county names);
  `Legal.hq_city`, `Legal.hq_state`, `Legal.website` (all optional). H1 needs no extras table.
- `MeView` and `UserView` for section 1.
- Regenerate: `uv run hope-export-schemas && pnpm --filter @hope/schemas gen`, and commit the outputs.
- The API views H3 returns (`domain`, `days_left`, `urgency`, `fit_band`, `counts`) are H3's, built by code from
  `GrantCandidate`; they aren't stored contracts.

There are no brief or proposal contracts: H4/H5 live in the browser (`lib/hope/types.ts`).

### 5. Tables and store (`0002_hackathon.sql`, `hope_core/store.py`)

- Tables (all with `tenant_id` + RLS):
  - `users` (section 1);
  - `jobs` (`job_id`, `kind`, `subject_id text null`, `status`, `progress jsonb`, `result jsonb`, `error`,
    `created_by`, `started_at`, `finished_at`);
  - `grant_candidates`: one row per `GrantCandidate`, `unique (tenant_id, url)`, plus `status_changed_at`,
    `status_changed_by`, `pass_reason`, `pass_reason_text`.
- Typed store functions, each taking `tx` (from `hope_core.db.tenant_tx`):
  - users: `create_user`, `get_user`, `get_user_by_email`;
  - profile: `get_profile(tx) -> AgencyProfile | None` (current version);
  - jobs: `create_job(tx, kind, subject_id=None, created_by=...)`, `update_job_progress`, `finish_job`, `get_job`,
    `latest_job(tx, kind, subject_id=None)`, `list_jobs(tx, kind, limit)`;
  - candidates: `upsert_candidate` (on a URL conflict, update the fields but keep `status`),
    `list_candidates(tx, status, sort, limit, offset, job_id=None)`, `count_candidates(tx) -> {"new", "saved", "passed"}`,
    `get_candidate`, `set_candidate_status(tx, grant_id, status, *, reason=None, reason_text=None, actor=None)`.

### 6. Web tools (`hope_core/web.py`)

- `fetch(url) -> Page(url, final_url, title, text, links: list[Link(url, text)], content_type)`. It is all code:
  - httpx, 15 s timeout, 5 MB cap, a Hope user agent; HTML text via `trafilatura`, PDF text via `pypdf`; respects `robots.txt`;
  - SSRF guard: only `http`/`https` on ports 80 and 443. The host is resolved first, and any address that isn't
    public (`ipaddress.ip_address(a).is_global` is false: loopback, private, link-local including `169.254.169.254`,
    multicast, reserved) raises `FetchError("blocked_address")`. Redirects are followed by hand
    (`follow_redirects=False`, at most 5) and every hop is checked. The connection goes to the checked address, so
    a DNS change between check and request can't bypass it;
  - it stores nothing. Raw pages are never persisted.
- `search(query, max_results=8) -> list[SearchResult(url, title, snippet)]` is model call **M2** (section 7).
- `WebTools` protocol with `RealWebTools` and `RecordedWebTools(fixture_dir)`:
  - it replays `search/<normalised query>.json` and `pages/<sha256(url)[:16]>.json`;
  - query lookup ignores case and extra whitespace; an unknown query returns `[]`; an unknown URL raises `FetchError`;
  - `Page.content_type` is always set.
- H0 records `packages/core/tests/fixtures/web/` for H1's seeded demo profile (Riverbend Community Health Alliance,
  Wenatchee WA, NTEE E32/F30): 3 searches and about 6 grant pages, 2 of them with a linked guideline page (one a PDF).
  Specs may keep their own fixture dirs (H2 does).

### 7. Model calls: OpenAI provider and gateway

**LLMs suggest, code decides.** H0's own features (auth, session, sync, jobs) make no model call. H0 provides the two
calls below, which H1 and H2 use. Every call goes through code H0 owns, has a fixed structured output, and runs offline in tests.

**M1: structured completion** (`OpenAIProvider.complete_json`, reached only through `ModelGateway.structured`)

| | |
|---|---|
| Input | `tier: ModelTier`, `messages: list[Message]` (system + user; any ingested text wrapped with `untrusted()` by the caller), `response_model: type[BaseModel]`, optional `RunBudget` |
| Request | OpenAI Chat Completions, `response_format = {type: "json_schema", json_schema: {name: <model title>, schema: response_model.model_json_schema()}}`, `temperature: 0`, 60 s timeout |
| Structured output | One JSON object for `response_model`, plus `usage.total_tokens` |
| Validated by | `ModelGateway.structured`: `json.loads`, then `response_model.model_validate`. On invalid JSON or a `ValidationError` it retries once, then raises `ModelOutputError(schema_title)`. The caller decides what that means (H1: `suggestions_unavailable`; H2: skip the page) |
| Code decides | the provider (`default_gateway()`: `OpenAIProvider` when `HOPE_OPENAI_API_KEY` is set, otherwise `MockProvider`; never a silent fallback from OpenAI to the mock); the model per tier (`FRONTIER`/`MID`/`SMALL` -> `openai_model`); 2 retries with backoff on 429/5xx only; the `RunBudget` ceilings (`BudgetExceededError` stops the run); the log line (schema title, model, tokens, estimated cost; never prompt or page text) |
| Never | money amounts or lifecycle/status changes in the output (callers' schemas have no such fields); tool use |
| Offline | `MockProvider.register(Model, responder)` in callers' tests; `packages/core/tests/fixtures/openai/{chat_ok,chat_invalid,chat_429}.json` replayed through an httpx `MockTransport` for the provider itself |

**M2: web search** (`RealWebTools.search`)

| | |
|---|---|
| Input | `query: str` (stripped, 1-200 chars, else `ValueError`), `max_results` (1-10) |
| Request | OpenAI Responses API, model `openai_search_model`, `tools: [{type: "web_search"}]`, input `"Find web pages for: {query}"` |
| Structured output | Only the `url_citation` annotations on the output message (`url`, `title`, `start_index`, `end_index`). The model's prose is discarded |
| Validated by | `hope_core.web.parse_search_response(raw, max_results) -> list[SearchResult]` |
| Code decides | keeps only `http`/`https` URLs; drops the fragment; dedupes by URL in first-seen order; caps at `max_results`; `title` falls back to the domain; `snippet` is the cited span, at most 300 chars. Whether a page is a grant, and everything about it, is decided later by H2's code from fetched text |
| Offline | `RecordedWebTools` for every caller; `packages/core/tests/fixtures/openai/web_search_response.json` through `MockTransport` for the parser |

`OpenAIProvider.embed` (model `openai_embed_model`) exists to satisfy the `Provider` protocol. No H spec calls it.

For orientation, the other model calls in the hackathon (each spec owns its call, prompt, schema, validation and mock):
H1 `NteeSuggestionOut` (M1); H2 `QueryPlan`, `PageExtraction`, `FitAssessment` (M1) and `search` (M2);
H5 the "Hope grant writer" agent in `app/api/hope/draft/route.ts` (OpenAI Agents SDK, Zod `outputType`, `OPENAI_API_KEY`, outside the gateway).

### 8. Job runner (`hope_core/jobs.py`)

- `start_job(kind, fn, *args, job_id=None) -> job_id` runs `fn` in a background thread pool inside the API process,
  with `report(progress)` and `finish(result | error)` callbacks.
  - It creates the job record, unless `job_id` is given: then it adopts that record (created by `create_job` in a
    committed transaction, same `kind`, status `queued`) and returns the same id. One run has exactly one job id.
  - An exception in `fn` marks the job `failed` with a one-line message and no traceback (the traceback goes to the log).
- On startup, jobs left `running` are marked `failed` with "Interrupted by restart".
- `HOPE_JOBS_INLINE=1` runs jobs synchronously (tests).
- Kinds: `discovery` (H2). There are no brief or proposal jobs.

### 9. Routers and services

- Pillar routers, all mounted:
  - `auth.py`, `me.py`: H0, implemented;
  - `discovery.py` (H2) and `grants.py` (H3): empty;
  - `hope_profile.api.router` (H1).
- The pillar routes the hackathon doesn't use are unmounted; their code and tests stay.
- New uv workspace member `services/discovery` (`hope_discovery`, H2) with an import test and an empty `demo.seed()`.
  There is no `services/briefs` or `services/drafting`.
- `AGENTS.md`: add `services/discovery` to the layout table and the migration ranges H1 `0310-0319`,
  discovery `0700-0709`, grants `0710-0719`. `0720-0729` and `0800-0809` stay reserved (H4/H5 use none).
- OpenAPI snapshots per router: `services/pillar/tests/snapshots/openapi/<router>.json`. The pillar test skips mounted
  external routers; the profile snapshot lives in `services/profile/tests/snapshots/openapi.json` (H1).

### 10. `make demo`

- Starts Postgres only (`docker compose -f infra/docker-compose.yml up -d postgres`; no Kafka, Temporal or MinIO),
  runs `uv run hope-migrate` and `uv run hope-demo-seed`, then starts the API (`:8000`) and the web app (`:3000`)
  with `NEXT_PUBLIC_HOPE_API_URL=http://localhost:8000`.
- The seed creates `demo@hope.org` / `hope-demo` and calls `hope_profile.demo.seed()`, then `hope_discovery.demo.seed()`.
  Each seed is idempotent.
- With no `HOPE_OPENAI_API_KEY`, everything runs on `MockProvider` and `RecordedWebTools`, so the demo always works.
  When it is set, `make demo` also passes it to the web process as `OPENAI_API_KEY` (H5's route), unless that is already set.
- It sets `HOPE_COOKIE_SECURE=false` (plain `http://localhost`). If `.env` has no `HOPE_INVITE_CODE`, it writes one
  (`secrets.token_urlsafe(16)`) to `.env` and prints it once.
- `pnpm --filter @hope/web dev` alone (no API URL) is still the offline demo on browser state.

## Owns

```text
packages/core/**                    (settings, auth, store, web, jobs, model_gateway, schemas, tests + fixtures)
packages/schemas/**                 (generated)
db/migrations/0002_hackathon.sql
services/pillar/**                  (app wiring, CORS, auth.py, me.py, empty discovery.py/grants.py, snapshots, demo seed runner)
services/discovery/**               (skeleton only)
services/profile/**                 (import-only edits: get_principal, Principal)
apps/web/api/http.ts, apps/web/api/session/**
apps/web/app/hope/layout.tsx, apps/web/components/hope/ui.tsx (HopeNav user/Sign out only; SC00)
apps/web/lib/hope/sync/**           (index.ts stays H0's; profile/opportunities/decisions pass to H1/H2/H3 after H0)
apps/web/package.json, pnpm-lock.yaml, Makefile, pyproject.toml, uv.lock, infra/docker-compose.yml, AGENTS.md
docs/specs/README.md                (H0 status row only)
One-time, before H1-H5: lib/hope/store.ts, lib/hope/opportunities.ts, api/profile/types.ts, lib/hope/i18n.ts (section 3)
```

Never: `apps/web/app/globals.css`, `components/ui/**`, `features/onboarding/**`, any `app/**/page.tsx`.

## Acceptance criteria

- [ ] AC1 Sign-up, login, `/v1/me` and logout work. A wrong email and a wrong password both return 401 `invalid_credentials`. Protected routes return 401 `not_signed_in` without the cookie. Sign-up without the right invite code returns 403 `signup_closed` whatever the email, and is always closed when `HOPE_INVITE_CODE` is unset. Short passwords return 422 `weak_password`; a taken email 409 `email_taken`. The cookie is `HttpOnly`, `SameSite=Lax` and `Secure` unless `HOPE_COOKIE_SECURE=false`.
- [ ] AC2 `/v1/me` returns `onboarding_complete` false until the profile has a mission statement and a program. Every W1 response has the keys and value types of `contracts/mocks/w1/**`.
- [ ] AC3 Every contract in section 4 validates and exports to JSON Schema and TS; the generated outputs are fresh. `amount_max` is integer minor units.
- [ ] AC4 The store functions round-trip every table; `upsert_candidate` keeps `status` on a URL conflict; `count_candidates` matches the lists; RLS blocks another tenant's rows.
- [ ] AC5 `fetch` extracts text and links from the HTML and PDF fixtures, and rejects loopback, private, link-local and metadata addresses, other schemes and ports, and redirects to any of them, with `blocked_address`. `RecordedWebTools` replays the fixtures with the lookup rules of section 6. No test touches the network.
- [ ] AC6 (M2) `parse_search_response` keeps only `http(s)` URL citations, dedupes, caps at `max_results`, falls back to the domain for a missing title, and ignores the model's prose.
- [ ] AC7 (M1) `default_gateway()` is the mock without a key and OpenAI with one. `structured` validates with the response model, retries once on invalid output, then raises `ModelOutputError`. 429/5xx retry twice, then fail; the mock is never used as a fallback. Log lines carry tokens and cost, and never message text.
- [ ] AC8 `start_job` runs inline in tests, reports progress and stores the result. With `job_id=` it adopts that record and creates no second row. An exception marks the job `failed` with a one-line error. Jobs left `running` are marked failed on startup.
- [ ] AC9 All routers are mounted, each with its own snapshot; the unused pillar routes are unmounted; existing tests still pass.
- [ ] AC10 Offline (`NEXT_PUBLIC_HOPE_API_URL` unset): `/hope/*` renders exactly as before, with no `/v1` request and no Sign out.
- [ ] AC11 Online: the guard and Sign out behave as SC00 AC1-AC6.
- [ ] AC12 The no-op adapters leave `useHope()` / `useOpportunities()` behaviour unchanged. `decide`/`undo` call `onDecide`/`onUndo` once, `saveProfile` calls `profile.save`, `hydrateProfile` doesn't. An adapter that throws never breaks a page. The hook signatures are unchanged.
- [ ] AC13 `git diff main --stat` shows no change to `app/globals.css`, `components/ui/**`, `features/onboarding/**` or any `page.tsx`.
- [ ] AC14 `make demo` on a clean checkout works twice in a row with no key, and `demo@hope.org` can sign in.

## Test plan

All offline: `MockProvider`, `RecordedWebTools`, httpx `MockTransport`, `HOPE_JOBS_INLINE=1`. DB tests are `@pytest.mark.db`.

| AC | Test |
|---|---|
| AC1 | `services/pillar/tests/test_auth.py` (signup, login, logout, invalid_credentials, not_signed_in, signup_closed with and without a configured code, weak_password, email_taken, cookie flags) |
| AC2 | `services/pillar/tests/test_me.py`; `services/pillar/tests/test_contract_shapes.py` (loads `contracts/mocks/w1/**`) |
| AC3 | `packages/core/tests/test_hackathon_schemas.py` + the schema freshness check |
| AC4 | `packages/core/tests/test_store.py` |
| AC5 | `packages/core/tests/test_web_tools.py` (incl. `test_fetch_blocks_internal_addresses`, parametrized over addresses and a redirect, with a fake resolver; `test_recorded_lookup_rules`) |
| AC6 | `packages/core/tests/test_web_search_parse.py` |
| AC7 | `packages/core/tests/test_openai_provider.py` (`test_default_gateway_without_key`, `test_structured_validates`, `test_invalid_output_retries_then_raises`, `test_429_retries`, `test_no_mock_fallback`, `test_log_has_no_message_text`) |
| AC8 | `packages/core/tests/test_jobs.py` (incl. `test_adopts_existing_job_id`, `test_exception_marks_failed`) |
| AC9 | `services/pillar/tests/test_openapi.py::test_router_snapshots` + the full suite |
| AC10, AC11 | `apps/web/api/session/RequireSession.test.tsx`, `apps/web/api/http.test.ts`, `apps/web/components/hope/ui.test.tsx` (see SC00) |
| AC12 | `apps/web/lib/hope/sync/index.test.ts` |
| AC13 | CI diff check in the PR description |
| AC14 | manual, recorded in the PR |

Web checks: `pnpm --filter @hope/web typecheck && pnpm --filter @hope/web lint && pnpm --filter @hope/web test`.

## Out of scope

Roles and approvals, multi-tenant, password reset, email verification, Temporal, Kafka, MinIO, server-side
applications/eligibility/drafts (the H4/H5 backend track), and new UI primitives or restyling.
