# Hope security model

The threat model Devin security scans start from. It was drafted from the code at `1ee3162`; the attackers, accepted risks and open questions below are still assumptions until a maintainer confirms or edits them.

## Threat-feed check (2026-11-18)
The first scan covered 19 threat feeds published 2026-11-18: nginx (NGINX2Root), PGPainless, @openeudi/openid4vp, SharpIppNext, Dell AWCC, Gortex, Music Assistant, IBM Engineering AI Hub, mini-snmpd, MyMangaDB, OpenVPN (Windows), MISP, DrayTek Vigor2960, Open OnDemand, temporal-proxy, Wavelog, PHPGurukul News Portal, Relaticle and SGLang.

What ships, checked before the launch (the scan found nothing):
- **`Dockerfile`**: `python:3.13-slim` plus `uv`. It runs only uvicorn (`infra/deploy/start.sh`). There is no nginx.
- **`uv.lock`**: 108 packages. None of the affected products are in it. `temporalio` 1.35.0 is the Temporal SDK, not temporal-proxy.
- **`pnpm-lock.yaml`**: no `@openeudi/openid4vp`.
- **Languages**: no Go, PHP, Java/Kotlin, .NET or C sources.
- **Web**: Vercel runs the Next.js app, so the edge is managed by Vercel.
- **Database**: Railway Postgres comes from a pgvector template. Its image is defined outside the repo, and that unknown is why the scan still ran.
- **Dev only**: `infra/docker-compose.yml` (Postgres, Redpanda, Redis, Temporal dev server, MinIO) is for local development and is not deployed.

## System overview and trust boundaries
- Browser → Vercel (Next.js, `apps/web`). Same-origin `/v1/*` requests are rewritten to the Railway API (`apps/web/next.config.ts`).
- Railway API: FastAPI `hope_pillar.api:app` (`services/pillar`) with in-process job threads. It talks to Railway Postgres through `hope_app`, where RLS is enforced via `hope_core.db.tenant_tx`. Cross-tenant workers use `hope_system`, which has BYPASSRLS.
- Outbound: the discovery agent fetches arbitrary funder web pages through `hope_core.web.fetch`, which has an SSRF guard, port allowlist, 5 MB cap and redirect limit. It also calls the OpenAI API (`hope_core.openai_provider`, `ModelGateway`).
- Vercel function `POST /api/hope/draft` (`apps/web/app/api/hope/draft/route.ts`) calls OpenAI with the server-only `OPENAI_API_KEY`.

## Components
| Component | Code |
|---|---|
| Web | `apps/web/**` (pages, `lib/`, `features/`), excluding the draft route |
| Draft function | `apps/web/app/api/hope/draft/**` |
| API | `services/pillar/**` (routers under `hope_pillar/api/`), `services/profile/**` |
| Auth | `services/pillar/src/hope_pillar/api/auth.py`, `accounts.py`, `packages/core/src/hope_core/auth.py` |
| Discovery | `services/discovery/**`, `packages/core/src/hope_core/web.py`, `model_gateway.py`, `openai_provider.py` |
| Core/Data | `packages/core/**` (other files), `db/migrations/**` |
| Infrastructure | `Dockerfile`, `railway.json`, `infra/**`, `.github/**` |
| Out-of-scope services | `services/ingestion`, `services/matching`, `services/budget`, `services/workflow` (not mounted by the hackathon API; legacy routes only with `legacy=True`) |

## Entry points and who can reach them
- **`/v1/auth/signup`**: anyone with the invite code (`HOPE_INVITE_CODE`, at least 16 chars, compared with `hmac.compare_digest`).
- **`/v1/auth/login`**: anyone. If `HOPE_OPEN_LOGIN=true`, any new email creates an account.
- **Other `/v1/*` routes** (grants, discovery jobs, applications, bids, profile, me): need a signed-in `hope_session` cookie (HttpOnly, SameSite=Lax, signed with `HOPE_SESSION_SECRET`). The app has a single tenant, so every member sees the same agency data.
- **`/api/hope/draft`** (Vercel): unauthenticated. It spends OpenAI credit.
- **Legacy pillar routes** (`hope_pillar/api/routes.py`, X-Hope-* header auth): mounted only with `legacy=True` (tests). They are not reachable in production.
- **Indirect input**: text of fetched web pages and pasted requirements reaches the LLM (prompt injection). It is wrapped with `model_gateway.untrusted(...)`.

## Assets
- Nonprofit profile, application answers, bids and evidence (confidential to the agency).
- User accounts and password hashes.
- `HOPE_SESSION_SECRET`, the DB passwords (`hope_app`/`hope_system`, admin `DATABASE_URL`) and the OpenAI keys.
- OpenAI spend.

## Attacker profiles (draft assumptions, unconfirmed)
1. Anonymous internet user hitting Vercel and the Railway API.
2. Signed-in member (invite code holder) trying to exceed their rights.
3. Hostile funder web page influencing the discovery agent (prompt injection, SSRF via redirects/links).

## Existing controls
- Invite-only sign-up, a constant-time invite check and a dummy-hash login timing equalizer.
- RLS through `tenant_tx`.
- CORS limited to `HOPE_WEB_ORIGIN`.
- The SSRF-guarded fetch.
- "LLMs suggest, code decides": no money amounts or lifecycle transitions come from LLM output.
- Request size caps on the draft route (40 KB).

## Out of scope / accepted risk (user-confirmed)
- None yet.

## Open questions
- Which attackers matter (are signed-in members trusted)?
- Is any infrastructure config kept outside this repo (Railway/Vercel project settings)? None is known, so the threat model uses only in-repo config.
- Are the dev-only services, out-of-scope services, `HOPE_OPEN_LOGIN` or the demo account accepted risk?
