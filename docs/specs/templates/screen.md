# SCxx: <Screen name>

| | |
|---|---|
| Route | `/path/[param]` |
| Feature folder | `apps/web/src/features/<feature>/` |
| Built by | Sxx |
| Roles | who can see it; who can act on it |
| Status | Draft / Ready / Done |

## Purpose

One or two sentences: who uses this screen and what they come to do.

## Layout

Regions from top to bottom, with the neumorphic primitive each one uses (`Card`
`neu-raised`, `Table`, `Input` `neu-inset`, `Button` `neu-pressed` when active, `Badge`).
Desktop and mobile (<= 640 px) layouts.

## Data and endpoints

For each call: when it fires, method + path, query/body, the fields the screen uses from the
response, and caching or refetch rules. Use the exact shapes from the owning feature spec.

| Trigger | Call | Uses |
|---|---|---|

## Interactions

Numbered list: each user action, what it calls, the optimistic or pending UI, and the
result on success and on each error `code` (for example `stale_artifact` -> reload the
artifact and explain that it changed).

## States

Loading, empty (with the expected reason), error, permission-denied, and stale-artifact states.

## Accessibility

Keyboard order, focus management on dialogs, ARIA labels, status not by colour alone,
reduced motion.

## Fixture data

What `api/<feature>/fixture.ts` returns so the screen works with no backend.

## Acceptance criteria

- [ ] ... (each one maps to a Vitest + Testing Library test)

## Test plan

| AC | Test (file::name) |
|---|---|
