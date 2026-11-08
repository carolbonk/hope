# Deploying Hope

The web app runs on **Vercel** and the API, with its database, on **Railway**. The browser only ever talks to
the web origin: `next.config.ts` proxies `/v1/*` to the API, so the session cookie is first-party and
`SameSite=Lax` keeps working across the two hosts.

```
browser ── https://<web>/v1/* ──▶ Vercel (Next.js rewrite) ──▶ Railway API (FastAPI + job threads) ──▶ Railway Postgres (pgvector)
```

## API (Railway)

- Service built from the repo root: `railway.json` → `Dockerfile`. On start, `infra/deploy/start.sh` does the following:
  1. Creates or updates the `hope_app` (RLS) and `hope_system` (BYPASSRLS) roles (`infra/deploy/roles.py`).
  2. Runs `hope-migrate`.
  3. Runs `hope-demo-seed` when `HOPE_SEED_DEMO=1`.
  4. Starts `uvicorn` on `$PORT`.
- Database: a Postgres service with the `vector` extension (Railway's pgvector template). Its superuser URL
  is the admin URL.
- Run a single replica: jobs run in background threads in the API process, and a restart marks running jobs as failed.

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (admin; used for migrations and creating roles) |
| `HOPE_APP_DB_PASSWORD`, `HOPE_SYSTEM_DB_PASSWORD` | random; `HOPE_DATABASE_URL` / `HOPE_DATABASE_SYSTEM_URL` are built from these |
| `HOPE_SESSION_SECRET` | random, 32+ bytes |
| `HOPE_INVITE_CODE` | shared with people allowed to sign up |
| `HOPE_WEB_ORIGIN` | the production web URL, e.g. `https://hope.vercel.app` |
| `HOPE_MODEL_PROVIDER`, `HOPE_OPENAI_API_KEY` | `openai` and the key (leave unset for the offline mock) |
| `HOPE_SEED_DEMO` | `1` to keep `demo@hope.org` / `hope-demo` available |

## Web (Vercel)

- Project root directory: `apps/web`, Node 22, framework Next.js. Vercel detects the pnpm workspace.
- Pages are static: EN/ES is chosen in the browser (`components/I18nProvider.tsx`, `lang` cookie, then the browser
  language), so only `/api/hope/draft` and `/hope/applications/[oppId]` are functions. That keeps the deployment within
  the Hobby plan's 12-function limit; don't read `cookies()` / `headers()` in a layout, and don't add an `apps/web/api/` folder (Vercel deploys every file in it as a separate function; API clients live in `lib/api/`).

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_HOPE_API_URL` | `/` (same origin, via the rewrite) |
| `HOPE_API_ORIGIN` | the Railway API URL, e.g. `https://hope-api.up.railway.app` (read at build time) |
| `OPENAI_API_KEY` | server-only, for `/api/hope/draft` |

## Check locally

```bash
docker build -t hope-api .
docker run -d --name hope-db -e POSTGRES_PASSWORD=pw -p 5433:5432 pgvector/pgvector:pg16
docker run --network host -e DATABASE_URL=postgresql://postgres:pw@localhost:5433/postgres \
  -e HOPE_APP_DB_PASSWORD=a -e HOPE_SYSTEM_DB_PASSWORD=s -e HOPE_SESSION_SECRET=$(openssl rand -hex 32) \
  -e HOPE_SEED_DEMO=1 -e PORT=8001 hope-api
NEXT_PUBLIC_HOPE_API_URL=/ HOPE_API_ORIGIN=http://localhost:8001 pnpm --filter @hope/web build
PORT=3001 pnpm --filter @hope/web start
```

## Create accounts

The live site has no sign-up form. An admin adds each team member from a shell with database access:

```bash
railway run hope-create-user --email ana@example.org --name "Ana"    # or: uv run hope-create-user ...
railway run hope-create-user --email ana@example.org --reset-password # new password for an existing account
```

- The password is asked for twice at a hidden prompt. For scripts, pipe it in with `--password-stdin`.
  It is never an argument, and the command never prints it.
- The rules match sign-up: at least 8 characters, a lowercased email, one account per email in the single tenant.
  An existing email fails with a non-zero exit, and `--reset-password` fails for an unknown one.
- The output is only the email and the new account's user id.
