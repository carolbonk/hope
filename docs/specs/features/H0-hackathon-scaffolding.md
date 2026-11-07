# H0: Hackathon scaffolding

| | |
|---|---|
| Wave | Hackathon, runs alone first (about 3-4 h) |
| Depends on | - |
| Screens | app shell, `/` redirect |
| Migrations | `0002_hackathon.sql` |
| Status | Ready |

## Goal

Put every shared piece in place so H1-H5 can run in parallel without editing the same file:
auth, contracts, tables and their store functions, the web tools, the OpenAI provider, the job
runner, one API router and one web folder per spec, and `make demo`. There is no product
logic beyond auth.

## Behaviour

### 1. Single tenant and auth

- `HopeSettings` gains `tenant_id: UUID` (`HOPE_TENANT_ID`), `agency_id: UUID` (`HOPE_AGENCY_ID`),
  `session_secret` (`HOPE_SESSION_SECRET`), `openai_api_key`, `openai_model` (default `gpt-4o-mini`)
  and `openai_search_model` (default `gpt-4o-mini`).
- Table `users` (`user_id uuid pk`, `tenant_id`, `email citext unique`, `password_hash`, `display_name`,
  `created_at`), with RLS like every other tenant table. Passwords are hashed with `argon2-cffi`.
- `services/pillar/src/hope_pillar/api/auth.py`:
  - `POST /v1/auth/signup` `{email, password, display_name}` returns 201 `{user}` and sets the session
    cookie. Passwords must be at least 8 characters (422 `weak_password`); a taken email returns 409
    `email_taken`.
  - `POST /v1/auth/login` `{email, password}` returns 200 `{user}` and sets the cookie. A bad email or
    password returns 401 `invalid_credentials`, with the same response for both.
  - `POST /v1/auth/logout` returns 204 and clears the cookie.
  - The cookie is `hope_session`: signed (itsdangerous), `HttpOnly`, `SameSite=Lax`, 14 days.
- `hope_core/auth.py`: `Principal(tenant_id, user_id, email, display_name)` and `get_principal`, which
  reads the cookie and returns 401 `not_signed_in` when there is no valid session. `tenant_id` always
  comes from settings. Replace the header-based principal in the pillar and profile services with it.
  There are no roles in the hackathon: every signed-in user can do everything.
- `GET /v1/me` (`api/me.py`) returns `{user_id, email, display_name, agency_id, onboarding_complete}`.
  `onboarding_complete` is true when the profile has a mission statement and at least one program.
- Web: `apps/web/src/api/session/` (`me()`, `login()`, `signup()`, `logout()`). All requests use
  `credentials: "include"`. A `RequireSession` wrapper in the app layout sends a 401 to `/login`, and
  sends a signed-in user with `onboarding_complete: false` to `/onboarding`. Next.js rewrites
  `/v1/*` to the API, so the cookie is first-party.

### 2. Shared contracts (`hope_core/schemas/hackathon.py`, exported from `hope_core.schemas`)

```python
class Citation(Contract):
    citation_id: str                 # "c1", "c2"... unique within its parent document
    kind: Literal["web", "profile"]
    url: str | None = None           # web
    title: str | None = None         # web page title
    quote: str                       # exact text supporting the claim (<= 500 chars)
    profile_path: str | None = None  # profile, e.g. "mission.mission_statement"
    retrieved_at: datetime | None = None

class DiscoveryProgress(Contract):
    queries_total: int = 0; queries_done: int = 0
    pages_read: int = 0; candidates_found: int = 0
    current_step: str = ""           # human text: "Searching: youth mentoring grants Ohio"

class DiscoveryJob(Contract):
    job_id: UUID
    status: Literal["queued", "running", "done", "failed"]
    queries: list[str] = []
    progress: DiscoveryProgress
    error: str | None = None
    started_at: datetime; finished_at: datetime | None = None

class GrantCandidate(Contract):
    grant_id: UUID
    title: str
    funder: str
    url: str                         # canonical grant page
    summary: str                     # 1-3 plain-English sentences
    amount_text: str | None = None   # quoted, e.g. "up to $50,000"
    amount_max: Money | None = None  # parsed by code from amount_text
    deadline_text: str | None = None
    deadline: date | None = None     # parsed by code; None for rolling or unknown
    eligibility_summary: str | None = None
    fit_score: int = Field(ge=0, le=100)
    fit_reasons: list[str] = []      # each <= 140 chars
    concerns: list[str] = []
    citations: list[Citation] = []
    status: Literal["new", "saved", "passed"] = "new"
    found_by_job_id: UUID | None = None
    discovered_at: datetime

class BriefItem(Contract):
    item_id: str
    text: str                        # plain English
    detail: str | None = None
    citation_ids: list[str] = []

class EligibilityCheck(Contract):
    requirement: str
    meets: Literal["yes", "no", "unknown"]
    why: str
    citation_ids: list[str] = []     # web and/or profile citations

class GrantQuestion(Contract):
    question_id: str
    text: str
    word_limit: int | None = None
    citation_ids: list[str] = []

class ApplicationBrief(Contract):
    grant_id: UUID
    overview: str                    # "What this grant is, in two sentences"
    how_to_apply: BriefItem          # the portal or method, with a link
    steps: list[BriefItem]
    required_documents: list[BriefItem]
    questions: list[GrantQuestion]
    deadlines: list[BriefItem]
    eligibility: list[EligibilityCheck]
    citations: list[Citation]
    generated_at: datetime
    content_hash: str

class ProposalSection(Contract):
    section_id: str                  # equals question_id when it answers a question
    title: str
    body_md: str                     # inline markers [c1], [c2] refer to citations
    citation_ids: list[str] = []
    unverified_claims: list[str] = []
    edited_by_user: bool = False

class ProposalDraft(Contract):
    grant_id: UUID
    status: Literal["drafting", "ready", "failed"]
    sections: list[ProposalSection]
    citations: list[Citation]
    generated_at: datetime | None = None
    content_hash: str
```

Also add `Mission.values: list[str] = []` and, if missing, `AgencyProfile.service_area: list[str] = []`
(state or county names). Regenerate the JSON Schema and TS types.

### 3. Tables and store (`0002_hackathon.sql`, `hope_core/store.py`)

- Tables (all with `tenant_id` + RLS):
  - `jobs` (`job_id`, `kind`, `status`, `progress jsonb`, `result jsonb`, `error`, `created_by`, `started_at`, `finished_at`);
  - `grant_candidates` (one row per `GrantCandidate`, `unique (tenant_id, url)`);
  - `application_briefs` (`grant_id` pk, `brief jsonb`, `content_hash`, `generated_at`);
  - `proposal_drafts` (`grant_id` pk, `draft jsonb`, `content_hash`, `updated_at`);
  - `proposal_section_versions` (append-only history).
- Typed store functions, each taking `tx`:
  - jobs: `create_job`, `update_job_progress`, `finish_job`, `get_job`, `latest_job(kind)`;
  - candidates: `upsert_candidate` (on URL conflict, update the fields but keep `status`), `list_candidates(status, sort, limit, offset)`, `get_candidate`, `set_candidate_status`;
  - briefs: `save_brief`, `get_brief`;
  - proposals: `save_draft`, `get_draft`, `save_section(grant_id, section, expected_hash)`, which raises `StaleArtifactError(current_hash)` when the hash doesn't match.

### 4. Web tools (`hope_core/web.py`)

- `search(query: str, max_results: int = 8) -> list[SearchResult(url, title, snippet)]` uses the OpenAI
  Responses API with the `web_search` tool and returns the URLs it cites.
- `fetch(url) -> Page(url, final_url, title, text, links: list[Link(url, text)], content_type)`:
  - uses httpx with a 15 s timeout, a 5 MB cap and a Hope user agent;
  - extracts HTML text with `trafilatura` and PDF text with `pypdf`;
  - respects `robots.txt`;
  - returns nothing that is persisted, and stores nothing.
- `WebTools` protocol with `RealWebTools` and `RecordedWebTools(fixture_dir)`. The recorded tools
  replay JSON fixtures from `packages/core/tests/fixtures/web/`. H0 records about 6 real grant pages
  (with their "how to apply" pages) and 3 searches for the demo profile. Tests always use the recorded tools.

### 5. OpenAI provider and job runner

- `OpenAIProvider` implements `Provider` (`complete_json` with a JSON-schema response format, and
  `embed`). `default_gateway()` returns OpenAI when the key is set and `MockProvider` otherwise. Each
  call logs its tokens and estimated cost.
- `hope_core/jobs.py`:
  - `start_job(kind, fn, *args) -> job_id` runs `fn` in a background thread pool inside the API
    process, with `report(progress)` and `finish(result | error)` callbacks;
  - on startup, jobs left `running` are marked `failed`, with the error "Interrupted by restart";
  - a `HOPE_JOBS_INLINE=1` setting runs jobs synchronously for tests.

### 6. Routers, services, web folders

- Pillar routers (empty and mounted unless noted):
  - `auth.py`, `me.py` (H0, implemented);
  - `discovery.py` (H2), `grants.py` (H3), `briefs.py` (H4), `proposals.py` (H5);
  - mount `hope_profile.api.router` (H1).
- Remove the pillar routes the hackathon doesn't use from the app; keep their code and tests.
- New uv workspace members with an import test: `services/discovery` (`hope_discovery`, H2),
  `services/briefs` (`hope_briefs`, H4) and `services/drafting` (`hope_drafting`, H5).
- `AGENTS.md` migration ranges: discovery `0700-0709`, grants `0710-0719`, briefs `0720-0729`,
  drafting `0800-0809`.
- Per-router OpenAPI snapshots: `services/pillar/tests/snapshots/openapi/<router>.json`.
- Web:
  - `nav.ts` entries: Grants `/grants`, Discover `/discover`, Profile `/profile`, plus a user menu
    with Sign out;
  - `/` redirects to `/grants`;
  - `ComingSoon` placeholder pages for `/login`, `/onboarding`, `/discover`, `/grants`,
    `/grants/[grantId]`, `/grants/[grantId]/brief` and `/grants/[grantId]/proposal`;
  - empty `features/<f>/` and `api/<f>/` folders for `session`, `onboarding`, `profile`, `discover`,
    `grants`, `brief` and `proposal`;
  - restyle all of `components/ui` to the liquid-glass system (README "Design system"): replace the
    liquid-glass CSS in `globals.css` with the `glass-*` tokens, including the reduced-transparency
    and no-`backdrop-filter` fallbacks;
  - shared primitives in `components/ui`: `Drawer`, `Toast`, `Tabs`, `Progress`, `MarkdownView`
    (react-markdown), and `CitationChip` plus `CitationPopover`. A citation chip shows `[c1]`; the
    popover shows the quote, the page title, the domain and an "Open source" link, or the profile field
    for a profile citation. H4 and H5 both use these.
  - remove the matrix, approvals and workflows routes from the nav (keep their code).
- `lib/problem.ts` maps problem codes to messages.

### 7. `make demo`

- Starts Postgres only (no Kafka, Temporal or MinIO), migrates, runs `uv run hope-demo-seed`, and
  starts the API (`:8000`) and the web app (`:3000`).
- The seed creates a demo user (`demo@hope.org` / `hope-demo`) and calls each package's
  `demo.seed()`, in the order `hope_profile`, `hope_discovery`, `hope_briefs`, `hope_drafting`.
  Each seed is idempotent.
- With no `HOPE_OPENAI_API_KEY`, everything runs on the mock and the recorded web tools, so the demo
  always works.

## Owns

`packages/core/**`, `packages/schemas/**`, `db/migrations/0002_hackathon.sql`, `services/pillar/**`
(app wiring, `auth.py`, `me.py`, empty routers, snapshots), `services/{discovery,briefs,drafting}/**`
(skeletons), import-only edits in `services/profile`, `apps/web/src/{api/session,components,lib,nav.ts}`,
`apps/web/src/app/**` (layout and placeholder pages only), `apps/web/next.config.*`, `apps/web/package.json`,
`pnpm-lock.yaml`, `Makefile`, `pyproject.toml`, `uv.lock`, `infra/docker-compose.yml`, `AGENTS.md`,
`docs/specs/README.md` (status row).

## Acceptance criteria

- [ ] AC1 Sign up, log in, `/v1/me` and log out work; a bad email or password both return 401 `invalid_credentials`; protected routes return 401 `not_signed_in` without the cookie.
- [ ] AC2 Every contract in section 2 validates, exports to JSON Schema and TS, and the generated outputs are fresh.
- [ ] AC3 The store functions round-trip every table; `save_section` with a stale hash raises `StaleArtifactError`; RLS blocks another tenant's rows.
- [ ] AC4 `RecordedWebTools` replays the search and fetch fixtures; `fetch` extracts text and links from HTML and PDF fixtures; no test touches the network.
- [ ] AC5 `default_gateway()` is the mock without a key; `OpenAIProvider` structured and web-search calls work against an httpx `MockTransport`.
- [ ] AC6 `start_job` runs inline in tests, reports progress and stores the result; restarted jobs are marked failed.
- [ ] AC7 All routers are mounted and each has its own snapshot; existing tests still pass.
- [ ] AC8 Web: unauthenticated users are sent to `/login`; users who haven't onboarded go to `/onboarding`; the nav and all placeholders render; the citation chip and popover render both web and profile citations.
- [ ] AC10 Every primitive renders with `glass-*` classes; under `prefers-reduced-transparency` panels are solid; axe finds no contrast violations on the shell over the backdrop.
- [ ] AC9 `make demo` on a clean checkout works twice in a row, with no key, and `demo@hope.org` can sign in.

## Test plan

| AC | Test |
|---|---|
| AC1 | `services/pillar/tests/test_auth.py` (signup, login, logout, invalid, not_signed_in) |
| AC2 | `packages/core/tests/test_hackathon_schemas.py` + schema freshness check |
| AC3 | `packages/core/tests/test_store.py` (`@pytest.mark.db`) |
| AC4 | `packages/core/tests/test_web_tools.py` |
| AC5 | `packages/core/tests/test_openai_provider.py` |
| AC6 | `packages/core/tests/test_jobs.py` |
| AC7 | `services/pillar/tests/test_openapi.py::test_router_snapshots` + full suite |
| AC8 | `apps/web/src/components/RequireSession.test.tsx`, `nav.test.ts`, `components/ui/Citation.test.tsx` |
| AC9 | manual, recorded in the PR |
| AC10 | `components/ui/glass.test.tsx` + `AppShell.a11y.test.tsx` (vitest-axe) |

## Out of scope

Roles and approvals, multi-tenant, password reset, email verification, Temporal, Kafka.

## Integration decisions (from the H1-H5 requests; these are part of H0)

The H specs may rely on all of these:

1. **Contracts:**
   - `Legal.hq_city`, `Legal.hq_state` and `Legal.website` (all optional). H1 drops its extras table.
   - `BriefItem.due_on: date | None = None`.
   - Docstrings: an item in `GrantCandidate.fit_reasons`, `concerns` or `ApplicationBrief.overview` may contain `[cN]` markers that refer to the parent's `citations`; an item without one renders as "Unverified".
2. **Jobs:**
   - `jobs.subject_id text null` and `jobs.created_by`;
   - `create_job(tx, kind, subject_id=None, created_by=...)`, `latest_job(tx, kind, subject_id=None)`, `list_jobs(tx, kind, limit)`;
   - an exception in `fn` marks the job `failed`, with a one-line message and no traceback.
   - Kinds: `discovery`, `brief` (subject `grant_id`), `proposal` (subject `grant_id`) and `proposal-section` (subject `"{grant_id}:{section_id}"`).
3. **Store:**
   - `get_profile(tx) -> AgencyProfile` (current version);
   - `list_candidates(..., job_id=None)` and `count_candidates(tx) -> {"new", "saved", "passed"}`;
   - `set_candidate_status(tx, grant_id, status, *, reason=None, reason_text=None, actor=None)`, with the columns `status_changed_at`, `status_changed_by`, `pass_reason` and `pass_reason_text`.
   - `save_section`'s `expected_hash` is the `ProposalDraft.content_hash`; the store recomputes it and stores the new hash.
4. **Web tools:**
   - `RecordedWebTools`: an unknown query returns `[]`, an unknown URL raises `FetchError`, and query lookup ignores case and extra whitespace.
   - Specs may keep their own fixture dirs.
   - `Page.content_type` is always set.
   - H0's recorded fixtures are for H1's demo profile (Riverbend, Wenatchee WA, NTEE E32/F30): 3 searches and about 6 grants, 2 of them with linked guideline pages (one a PDF).
5. **Web:**
   - `RequireSession` lets `/login` render without a session, never redirects `/onboarding` to itself, and sends signed-in users away from `/login` to `/grants` (or `/onboarding`).
   - `Toast` survives client navigation.
   - `lib/problem.ts` keeps `errors[]` (`field`, `code`, `message`) and includes the messages for `brief_missing`, `drafting_in_progress`, `unknown_citation`, `draft_not_ready`, `section_not_found` and `bad_format`.
   - `MarkdownView` takes an optional `citations` prop and renders `[cN]` as `CitationChip`s.
6. **Snapshots:** the profile router's OpenAPI snapshot lives in `services/profile/tests/snapshots/openapi.json` (owned by H1). The pillar's snapshot test skips mounted external routers.
7. **Parsing:** `parse_amount`/`parse_deadline` stay in `hope_discovery.parse` for now. H4 computes its dates from quotes with its own helper.
