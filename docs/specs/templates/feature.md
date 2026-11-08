# Sxx: <Title>

| | |
|---|---|
| Wave | <n> |
| Depends on | <spec IDs, all must be Done> |
| Screens | <SCxx list or "-"> |
| Migrations | <reserved numbers, e.g. `0410_matrix_explain.sql`> |
| Blueprint | <section numbers in docs/architecture/blueprint.md> |
| Status | Draft / Ready / In progress / Done |

## Goal

Two or three sentences: the user-visible outcome and why it matters.

## Current state

What exists on `main` today, with file paths and symbol names, and what's missing or stubbed.

## Behaviour

Numbered, step-by-step description of what happens, including every branch:
validation failures, permission failures, stale hashes, retries, timeouts, idempotency,
tenant isolation, and what the LLM may and may not do.

## Contracts

- **Shared models used** (from `hope_core.schemas`): ...
- **Shared contract additions** (these go into the wave's contracts spec, not this PR): exact
  field names, types and docstrings.
- **Events**: event type, topic, payload model, producer, consumers.
- **Endpoints**: for each, method + path, auth/roles, request body, query params, response
  body (JSON example), status codes and error `code` values.
- **Database**: tables, columns, indexes, RLS policy, in the reserved migration file.

## Owns

Exact list of paths this PR may create or change. Nothing else.

```text
services/<svc>/src/hope_<svc>/<module>.py
services/<svc>/tests/test_<feature>.py
services/pillar/src/hope_pillar/api/<router>.py
services/pillar/tests/snapshots/openapi/<router>.json
apps/web/features/<feature>/**
apps/web/lib/api/<feature>/**
apps/web/app/<route>/page.tsx
db/migrations/<reserved>.sql
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 ... (each one testable, and each one named in the test plan)

## Test plan

| AC | Test (file::name) | Type (unit / db / api / property / e2e) |
|---|---|---|

Commands: the CI commands in `AGENTS.md`, plus any extra commands this spec needs.

## Out of scope

## Decisions needed

Open questions that block starting, with a recommended default.

## References

Code, blueprint sections and external docs, with links.
