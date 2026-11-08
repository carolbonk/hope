# H3: Save/pass backend, decision sync, Saved and Deadlines

| | |
|---|---|
| Wave | Hackathon (parallel with H1, H2, H4, H5 after H0) |
| Depends on | H0 (auth, `hope_core.store`, `api/http.ts`, the `lib/hope/sync/` seam); H2 (fills `grant_candidates` and maps them into `useOpportunities()`) |
| Screens | SC25 `/hope/saved` and `/hope/deadlines` (built by PR #34). SC26 has no page (see SC26) |
| Migrations | none (`0710-0719` stays reserved; H0 already adds the status/reason columns) |
| Status | Built (backend and sync PR #48, grants API test PR #52; UI by PR #34) |

## Goal

The user saves or passes opportunities on the Discover deck (SC24, H2's page). Saving creates the
application record H4 and H5 work on. The browser already does all of this in `hope:state:v1`.

H3 adds three things and rebuilds nothing:
1. **The real `/v1/grants` backend:** list, detail, and save / pass / reset of `grant_candidates`.
2. **`lib/hope/sync/decisions.ts`:** mirrors each browser `decide` / `undo` to that backend, so the
   server knows what the team is pursuing (app-shell badge, H2's "known URL" skip, discovery job view).
3. **The Saved and Deadlines pages** keep working, with two small fixes and tests.

The browser record stays the source of truth for the workspace. The server mirror never rolls back or
rewrites browser state.

## Ground truth in `apps/web` (main)

- `useHope()` (`lib/hope/store.ts`, H4) has `decide(opp, "saved" | "passed")` and `undo()`.
  - `decide` writes `decisions[opp.id] = { decision, at }` and appends to `history`.
  - Saving creates `applications["app:org-local-1:<oppId>"]` at stage `saved`. Saving again reuses it.
  - `undo()` removes the last decision. It deletes the application only when nothing was done
    (`activity.length <= 1` and stage `saved`).
- `useOpportunities()` (`lib/hope/opportunities.ts`, H2) returns the catalog, today the demo list
  (`lib/hope/demo.ts`, ids `opp-*`, `source.kind = "demo"`). H2's adapter adds backend grants.
- `app/hope/saved/page.tsx` and `app/hope/deadlines/page.tsx` join `state.applications` with
  `useOpportunities()` by `opportunityId`. SC25 describes them exactly.
- The nav badge "Saved (n)" (`components/hope/ui.tsx`, H0) counts `decisions` with `saved`.

## Behaviour

### 1. Decision sync (`lib/hope/sync/decisions.ts`)

**Interface** (called by `store.ts`; H0 wires the two calls once, H3 never edits `store.ts`):

```ts
export type DecisionStatus = "saved" | "passed" | "new";
export function mirrorDecision(oppId: string, status: DecisionStatus): void; // never throws, returns at once
export function flushDecisions(): Promise<void>;                              // never rejects
```

- `decide(opp, d)` calls `mirrorDecision(opp.id, d)`. `undo()` calls `mirrorDecision(lastId, "new")`.
- `lib/hope/sync/index.ts` (H0) calls `flushDecisions()` once after the session loads. The adapter also
  flushes on the window `online` event.

**Rules (all code, no model):**
1. **Off switch.** When H0's sync switch is off (no API base URL), both functions do nothing. The app
   works offline exactly as it does today.
2. **Only backend grants.** An id is mirrored only if it is a UUID (`/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i`).
   Demo ids (`opp-*`) are never sent. This relies on H2's adapter setting `Opportunity.id = grant_id`.
3. **Outbox.** `mirrorDecision` writes the wanted status into localStorage `hope:sync:decisions:v1`:
   `{ version: 1, pending: { [grantId]: { status, attempts, at } } }`. A newer status for the same grant
   replaces the older one (last intent wins), so save → undo → pass sends a single `pass`.
   Then it starts a flush.
4. **Flush.** One request at a time, oldest `at` first:
   - `saved` → `POST /v1/grants/{grant_id}/save` with an empty body.
   - `passed` → `POST /v1/grants/{grant_id}/pass` with `{}`. The UI has no reason picker.
   - `new` → `POST /v1/grants/{grant_id}/reset`.
5. **Responses** (through H0's `api/http.ts`, `credentials: "include"`, `ProblemError`):
   - `200` (`changed` true or false): remove the entry. The endpoints are idempotent, so replays are safe.
   - `404 grant_not_found` or any `422`: remove the entry and `console.warn("decision sync dropped", {grantId, code})`.
   - `401 not_signed_in`: stop this flush and keep every entry. H0's session guard handles the redirect.
   - Network error or `5xx`: keep the entry and add 1 to `attempts`. Retry after 2 s, 8 s, 30 s, 60 s.
     After 5 attempts, stop retrying until the next page load or `online` event.
6. **Never touches browser state.** No rollback, no toast, no page change. A failed mirror only leaves
   the entry in the outbox.

### 2. Backend (`services/pillar/src/hope_pillar/api/grants.py`)

All endpoints need H0's session (401 `not_signed_in`). There are no roles. The tenant comes from settings
(single tenant), and every query runs in `hope_core.db.tenant_tx` through `hope_core.store` only (no SQL
in `grants.py`).

1. **Listing.** `GET /v1/grants` reads every candidate with the requested `status` via
   `store.list_candidates(tx, status, "fit", limit=500, offset=0)`, then applies `q`, `deadline_within_days`,
   `include_past`, `sort`, `limit` and `offset` in Python (at most about 200 candidates in the hackathon).
   `counts` comes from `store.count_candidates(tx)`, so the tab counts are right whatever the filter.
2. **Derived fields**, computed on every read and never stored. `_today()` returns the UTC date, and
   tests monkeypatch it:
   - `days_left = (deadline - today).days`, or `None` when `deadline` is `None`.
   - `urgency`: `past` if `days_left < 0`, `urgent` if `<= 7`, `soon` if `<= 21`, `later` otherwise;
     with no `deadline`: `rolling` if `deadline_text` matches `/rolling|ongoing|open until/i`, else `unknown`.
     These thresholds are the API's. The web pages compute their own days (SC25).
   - `fit_band`: `strong` (≥ 75), `good` (≥ 55), `weak` (< 55).
   - `domain`: the host of `url` without `www.`.
3. **Past deadlines.** With `include_past=false` (the default), `new` and `saved` leave out `urgency = past`
   rows and return their number as `hidden_past`. `passed` always includes them.
4. **Citation markers.** H2 ends each `fit_reasons` / `concerns` string with markers (`"… [c1][c3]"`).
   - Trailing markers are parsed with `/\s*\[(c\d+)\](?=\s*(\[c\d+\]\s*)*$)/` into `citation_ids` and
     stripped from `text`.
   - A marker with no matching `citation_id` in `citations` is dropped, and the item is `unverified: true`.
     An item with no markers is `unverified: true`. No item is ever dropped or reordered.
   - List items return the first 3 reasons and concerns. The detail returns all of them.
   - `citations` on a list item holds only the ids its reasons, concerns and summary use.
   - Detail only: `summary_citation_ids` are the `[cN]` markers inside `summary`.
     `amount_citation_id` / `deadline_citation_id` are the first citation whose `quote` contains
     `amount_text` / `deadline_text`, or `null`.
5. **Save, pass, reset.** `POST /v1/grants/{grant_id}/save|pass|reset` call
   `store.set_candidate_status(tx, grant_id, status, reason=..., reason_text=..., actor=principal.user_id)`.
   - `reset` sets `new`. It is what Undo sends.
   - Idempotent: setting the current status returns 200 with `changed: false` and writes nothing.
   - Pass takes an optional body `{reason, reason_text}`. `reason` must be one of `not_a_fit`, `too_small`,
     `deadline_too_soon`, `not_eligible`, `other`. `reason_text` (≤ 300 chars) is allowed only with `other`.
     Anything else returns 422 `invalid_reason`.
   - A status change never changes `fit_score`, the reasons, or anything else H2 produced.
6. **Detail.** `GET /v1/grants/{grant_id}` returns the card fields plus everything in item 4,
   `eligibility_summary`, all `citations`, `found_by_job_id` and `view_original_url = url`. It makes no
   web call.

### 3. Saved and Deadlines pages

They are built. H3 keeps them as they are, except for two fixes in its own files:
1. **Passed ones are hidden.** `/hope/saved` and `/hope/deadlines` list only applications whose
   `decisions[oppId]?.decision` is not `"passed"`. A worked-on application whose decision was undone stays listed, because undo never deletes edits.
2. **The Demo badge only for demo data.** The "Demo data" badge on a Saved card shows only when
   `o.source.kind === "demo"`.

Everything else (layout, copy, sorting, liquid-glass classes) stays. SC25 has the details.

## AI / LLM steps

**H3 makes no model or web calls.** `grants.py` and `lib/hope/sync/decisions.ts` contain no prompts and no
response models. They don't import `ModelGateway`, `hope_core.web` or `@openai/agents`, and a test checks this.
Every value H3 decides, it decides in code.

H3 serves text that a model wrote upstream. H3 doesn't re-validate it, but here is the full chain so
nobody adds a model call here:

| Step | Owner | Input | Structured output | Validated by | What code decides | Offline fixture |
|---|---|---|---|---|---|---|
| Score fit | H2 | `ProfileDigest` (`P#` ids) + verified page quotes (`W#` ids) | `FitAssessment {fit_score, reasons[Point], concerns[Point], eligibility_blocker}` | `ModelGateway.structured` (Pydantic) + H2's fit post-processing | clamp 0-100, blocker cap 30, keep 4 reasons / 3 concerns, map refs to `c1..cn`, append markers | `hope_discovery.mock.register` (MockProvider) |
| Serve fit (this spec) | H3 | stored `GrantCandidate` | none (no model) | `grants.py` code | `fit_band`, `urgency`, `days_left`, `unverified`, `hidden_past`, sort, counts, status, idempotency, pass-reason check | `store.upsert_candidate` seed in `test_grants_api.py` (below) |
| Match reasons on the card | H4 (`store.ts`) | `Opportunity` + `OrgProfile` | none (no model) | — | `matchReasons`, `eligibility` | the demo catalog |

The Discover card's "Why it could fit" comes from `matchReasons` (code), not from H2's LLM reasons.
Showing the LLM reasons would need a new optional field on `Opportunity` and a page edit, which is out of scope.

## Contracts

- **Shared models used:** `GrantCandidate`, `Citation`, `Money`, `hope_core.auth.get_principal`,
  `hope_core.store.*`, `hope_core.errors`. No new shared contract.
- **Endpoint models**, in `hope_pillar/api/grants.py` only: `CitedItem{text, citation_ids, unverified}`, `GrantCard`,
  `GrantDetail`, `GrantListPage`, `StatusChange`, `PassBody`.
- **Money:** `amount_max` is `{amount_minor: int, currency}` on the wire, and is never a float.
  `sort=amount` compares `amount_minor` integers. Discovery parses only USD (H2), so a non-USD row sorts
  with the unknown ones. H3 never converts money; H2's adapter divides by 100 for the UI.
- **Endpoints**, exactly as in `contracts/manifest.json` W4 and `contracts/mocks/w4/**`:

  | Endpoint | Request | 200 body | Errors |
  |---|---|---|---|
  | `GET /v1/grants` | query below | `GrantListPage {items[GrantCard], total, limit, offset, counts{new, saved, passed}, hidden_past}` (`mocks/w4/grants.list/new.json`) | 422 `invalid_query` (`detail` names the parameter) |
  | `GET /v1/grants/{grant_id}` | — | `GrantDetail` (`mocks/w4/grants.get/ok.json`) | 404 `grant_not_found` |
  | `POST /v1/grants/{grant_id}/save` | empty | `StatusChange {grant_id, status, previous_status, changed}` | 404 `grant_not_found` |
  | `POST /v1/grants/{grant_id}/pass` | optional `PassBody {reason, reason_text}` | `StatusChange` with `status: "passed"` | 404 `grant_not_found`, 422 `invalid_reason` |
  | `POST /v1/grants/{grant_id}/reset` | empty | `StatusChange` with `status: "new"` | 404 `grant_not_found` |

  `GET /v1/grants` query:

  | Query | Type | Default | Rule |
  |---|---|---|---|
  | `status` | `new`, `saved`, `passed` | `new` | |
  | `sort` | `fit`, `deadline`, `amount`, `newest` | `fit` | `fit`: score desc, then deadline asc. `deadline`: soonest first, then rolling, then unknown. `amount`: `amount_minor` desc, unknown last. `newest`: `discovered_at` desc |
  | `q` | string, 1-100 chars | none | Case-insensitive match on title, funder, summary and domain |
  | `deadline_within_days` | int 1-365 | none | Keeps `0 <= days_left <= n` |
  | `include_past` | bool | `false` | |
  | `limit` | int 1-100 | 20 | The app-shell badge sends `?status=new&limit=1` and reads `counts.new` |
  | `offset` | int ≥ 0 | 0 | |

- **Callers in the hackathon:** H0's app-shell badge (`GET /v1/grants`), H2's opportunities adapter
  (`GET /v1/grants`), and this spec's decisions adapter (save / pass / reset). No page calls `/v1/grants` directly.
- **Events and database:** none. H0 owns the `grant_candidates` columns.

## Owns: only edit these paths

```text
services/pillar/src/hope_pillar/api/grants.py
services/pillar/tests/test_grants_api.py
services/pillar/tests/snapshots/openapi/grants.json
apps/web/lib/hope/sync/decisions.ts
apps/web/lib/hope/sync/decisions.test.ts            (new)
apps/web/app/hope/saved/**                           (page.tsx + page.test.tsx)
apps/web/app/hope/deadlines/**                       (page.tsx + page.test.tsx)
```

Don't edit `lib/hope/store.ts` (H4), `lib/hope/opportunities.ts` and `app/hope/discover/**` (H2),
`lib/hope/sync/index.ts` and `components/hope/ui.tsx` (H0), `app/globals.css` or `components/ui/**`.
`lib/hope/types.ts` and `lib/hope/i18n.ts` are shared: add keys, never rename them. H3 needs no new keys.

## Test seed

The API tests seed their own rows with `store.upsert_candidate`, and `_today()` is fixed to `2026-11-07`:
- the two items of `contracts/mocks/w4/grants.list/new.json` (fit 88 strong, `later`; fit 74 good, `rolling`)
- six more built in the test: fit 62 `urgent` (6 days, amount text only), fit 48 weak with no amount
  (`unknown`, `deadline_text` "Spring 2027"), fit 77 `soon` (18 days) with one unknown marker, fit 70 `saved`,
  fit 40 `passed`, and fit 80 `past` (−3 days)

The web tests use the demo catalog with a fixed clock (`vi.setSystemTime(new Date("2026-11-07T12:00:00"))`)
and a seeded `hope:state:v1`. The adapter tests answer `fetch` with the bodies in `contracts/mocks/w4/**`.
No test uses the network or an API key.

## Acceptance criteria

- [ ] AC1 `GET /v1/grants` returns the requested status, sorted by each `sort` exactly as specified, with `total`, `counts` and `hidden_past` right.
- [ ] AC2 `q`, `deadline_within_days`, `include_past`, `limit` and `offset` filter and page correctly. Bad values return 422 `invalid_query` naming the parameter.
- [ ] AC3 `days_left`, `urgency` (all 6 values) and `fit_band` are derived by code with the fixed clock.
- [ ] AC4 Reasons and concerns parse into `{text, citation_ids, unverified}`. An unknown or missing marker gives `unverified: true`, and no item is dropped.
- [ ] AC5 Save, pass and reset change only `status` (and H0's status/reason columns), are idempotent (`changed: false`), and pass validates `reason` (422 `invalid_reason`).
- [ ] AC6 `GET /v1/grants/{grant_id}` returns the full detail. An unknown id returns 404 `grant_not_found`.
- [ ] AC7 Without a session, every endpoint returns 401 `not_signed_in`.
- [ ] AC8 Every response has the same keys and value types as its `contracts/mocks/w4/**` scenario. `amount_minor` is an integer.
- [ ] AC9 `grants.py` has no SQL and imports no `ModelGateway` or `hope_core.web`. Only `openapi/grants.json` changes.
- [ ] AC10 `mirrorDecision` sends save / pass / reset for UUID ids only, coalesces per grant, retries network and 5xx errors with the backoff, drops 404/422, keeps entries on 401, and is a no-op with sync off. It never throws and never changes `hope:state:v1`.
- [ ] AC11 The outbox survives a reload: entries left in `hope:sync:decisions:v1` are sent by `flushDecisions()`.
- [ ] AC12 SC25's acceptance criteria pass (Saved and Deadlines, including the two fixes).

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/pillar/tests/test_grants_api.py::test_list_sorts_counts_hidden_past` | api (db) |
| AC2 | `test_grants_api.py::test_list_filters_paging` (parametrized), `::test_invalid_query` | api (db) |
| AC3 | `test_grants_api.py::test_derived_urgency_and_band` (parametrized over the 6 urgencies) | api (db) |
| AC4 | `test_grants_api.py::test_reason_citation_parsing` | unit |
| AC5 | `test_grants_api.py::test_save_pass_reset_idempotent`, `::test_pass_reason_validation` | api (db) |
| AC6 | `test_grants_api.py::test_detail_and_not_found` | api (db) |
| AC7 | `test_grants_api.py::test_requires_session` | api |
| AC8 | `test_grants_api.py::test_matches_contract_mocks` (parametrized over the W4 scenarios) | api (db) |
| AC9 | `test_grants_api.py::test_router_has_no_sql_or_model_calls` (AST), `test_openapi.py::test_router_snapshots` | unit |
| AC10 | `apps/web/lib/hope/sync/decisions.test.ts`: `maps status to endpoint`, `skips demo ids`, `coalesces per grant`, `retries with backoff` (fake timers), `drops 404 and 422`, `keeps entries on 401`, `no-op when sync is off`, `never throws` | web unit |
| AC11 | `decisions.test.ts::replays the outbox after reload` | web unit |
| AC12 | `apps/web/app/hope/saved/page.test.tsx`, `apps/web/app/hope/deadlines/page.test.tsx` (SC25 section 14) | web unit |

Checks: `uv run pytest services/pillar -q` and `pnpm --filter @hope/web typecheck && pnpm --filter @hope/web lint && pnpm --filter @hope/web test`.

## Out of scope

- A grant list, filter bar or overview page in the web app: the Discover deck and the workspace cover them.
- A pass-reason picker in the UI (the API accepts a reason; nothing sends one yet).
- Pulling the server status back into the browser (two browsers can disagree; the browser wins locally).
- Showing H2's LLM reasons, concerns and citations on the card.
- Re-scoring, editing grant facts, bulk actions, sharing and notifications.

## Requests to other specs

- **H0:** `lib/hope/sync/index.ts` exposes the sync on/off switch and calls `flushDecisions()` after the
  session loads. `store.ts` calls `mirrorDecision(opp.id, d)` in `decide` and `mirrorDecision(lastId, "new")` in `undo`.
- **H2:** the opportunities adapter sets `Opportunity.id = grant_id`. It loads `status=new` and
  `status=saved&include_past=true`, so a saved grant (even an overdue one) stays in `useOpportunities()`
  and on Saved and Deadlines after a reload.

## Decisions (recommended defaults, applied above)

1. **Server status is a mirror, never the source.** The browser decides. The adapter pushes only.
2. **Undo maps to `reset`.** It also applies when the previous status was `passed`.
3. **Pass reasons:** stored by the API (H0's columns), but not asked for in the hackathon UI.
