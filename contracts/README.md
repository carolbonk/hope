# Hope contracts: the frontend/backend agreement

This folder is the contract between the web app and the API for the hackathon MVP (H0-H5).
Frontend people build screens against the mock API; backend people make the real endpoints
return the same shapes. The shapes come from the H0-H5 feature specs in `docs/specs/features/`;
if a spec and a mock disagree, fix both in the same PR.

## Run the mock API

```bash
pnpm install
pnpm mock                      # http://localhost:8000/v1, list of endpoints at /__mock
MOCK_PORT=8010 pnpm mock       # another port
```

Point the web app at it: `NEXT_PUBLIC_HOPE_API_URL=http://localhost:8000 pnpm --filter web dev`.
CORS allows any origin with credentials, and sign-in sets a fake `hope_session` cookie.

The mock has no state: saving a grant returns the "saved" response but the list doesn't change.

### Pick a scenario (loading, empty, error...)

Every endpoint has named scenarios (`mocks/<workflow>/<endpoint id>/<scenario>.json`). The first match wins:

1. `?mock=<scenario>` on the request, e.g. `GET /v1/grants?mock=empty`
2. Header `x-mock-scenario: grants.list=empty, me.get=not_onboarded`
3. Env `MOCK_SCENARIOS="grants.list=empty,brief.get=no_brief_running" pnpm mock`
4. A query value that names a scenario: `?status=saved`, `?format=md`
5. The endpoint's `default` in `manifest.json`

Each response carries `x-mock-scenario: <endpoint>=<scenario>`, so you can see which one you got.

## Files

| Path | What |
|---|---|
| `manifest.json` | Workflows -> screens -> endpoints, owners (spec + ticket), the code-vs-LLM step map, and each endpoint's scenarios |
| `mocks/<w>/<endpoint>/<scenario>.json` | `{status, headers, body}` (or `body_text` for downloads) |
| `mocks/<w>/<endpoint>/request.json` | Example request body |
| `mock-server.mjs` | Zero-dependency Node server for the manifest |
| `test/contracts.test.mjs` | Runs in CI (`pnpm -r run test`) |

## Rules

- **One demo nonprofit everywhere.** Riverbend Community Health Alliance, grant
  `3f6b1c2e-…` (Rural Oral Health Access Grant 2027). Keep IDs consistent across mocks.
- **Errors** are `application/problem+json` with a stable `code`; the UI branches on `code`, never on `title`.
- **Money** is `{amount_minor, currency}` with integer minor units. Profile form budgets are whole dollars (`annual_operating_budget_usd`).
- **Changing a shape?** Edit the spec section, the mock and the backend test in the same PR. The tests fail
  when a hackathon screen spec calls an endpoint that isn't here.
- **Backend tests** should load the matching mock (`contracts/mocks/...`) and assert the real response has the
  same keys and value types (the extra keys are fine).

## Canonical endpoints (resolved from older specs)

- The profile is `GET/PUT/PATCH /v1/profile`. `/v1/agencies/{agency_id}/profile` is Phase 1, not the hackathon.
- The app-shell grant badge is `GET /v1/grants?status=new&limit=1` -> `counts.new` (`limit` is 1-100).
- There are no separate brief/proposal status endpoints. SC26's `getBriefStatus` / `getProposalStatus` are
  client helpers over `GET /v1/grants/{id}/brief` (404 `no_brief` carries the job) and `GET /v1/grants/{id}/proposal`.
