# H3: Curated grant list, save/pass/undo, shortlist and grant overview

| | |
|---|---|
| Wave | Hackathon (parallel with H1, H2, H4, H5 after H0) |
| Depends on | H0 |
| Screens | SC25 `/grants`, SC26 `/grants/[grantId]` |
| Migrations | none (see Decisions 1; `0710-0719` stays reserved) |
| Status | Draft |

## Goal

Discovery (H2) finds dozens of grants. H3 turns them into a decision the user can make in a
few minutes. Each grant is a card with a fit score, money, deadline and the top reasons and
concerns, every one with a citation. The user saves or passes with a button, a swipe or a
key, and can undo. The shortlist then feeds the application brief (H4) and the proposal (H5).

## Current state (after H0)

- `GrantCandidate` (in `hope_core.schemas`) holds `title`, `funder`, `url`, `summary`, `amount_text` / `amount_max`, `deadline_text` / `deadline`, `eligibility_summary`, `fit_score`, `fit_reasons`, `concerns`, `citations`, `status` (`new` | `saved` | `passed`), `found_by_job_id` and `discovered_at`.
- `hope_core.store` provides `list_candidates(tx, status, sort, limit, offset)`, `get_candidate(tx, grant_id)` and `set_candidate_status(tx, grant_id, status)`. The `grant_candidates` table is H0's, and H2 fills it.
- `services/pillar/src/hope_pillar/api/grants.py` is an empty mounted router. `/grants` and `/grants/[grantId]` render `ComingSoon`.
- `components/ui` provides `CitationChip`, `CitationPopover`, `Tabs`, `Drawer`, `Toast`, `Progress` and `MarkdownView`. `lib/problem.ts` maps error codes to messages.
- **H3 makes no LLM or web calls.** All of its text was produced by H2 and is shown as-is. So H3 has no prompts and no LLM response models.

## Behaviour

1. **Listing.** `GET /v1/grants` reads every candidate with the requested `status` via `store.list_candidates(tx, status, "fit", limit=500, offset=0)`, then applies `q`, `deadline_within_days`, `sort`, `limit` and `offset` in Python. The hackathon has at most about 200 candidates, so this stays under 20 ms. `counts` are computed from three status-only lists, so the tab badges are always right.
2. **Derived fields** are computed by code on every read and never stored:
   - `days_left = (deadline - today_utc).days`. It's `None` when `deadline` is `None`.
   - `urgency`:
     - `past` if `days_left < 0`
     - `urgent` if `days_left <= 7`
     - `soon` if `<= 21`
     - `later` otherwise
     - `rolling` if `deadline` is `None` and `deadline_text` matches `/rolling|ongoing|open until/i`
     - `unknown` otherwise
   - `fit_band`: `strong` (≥ 75), `good` (≥ 55), `weak` (< 55).
   - `domain`: the host of `url` without `www.`.
3. **Past deadlines.** Rows with `urgency = past` are left out of `new` and `saved` by default (`include_past=false`), and their count is returned as `hidden_past`. They always appear in `passed`, labelled "Deadline passed".
4. **Citations on reasons and concerns.** H2 ends each reason or concern string with its citation markers, for example `"Funds youth mentoring in Ohio [c2]"` (see Requests to H2). H3 parses trailing markers with `/\s*\[(c\d+)\](?=\s*(\[c\d+\]\s*)*$)/` into `citation_ids`, and strips them from the displayed text.
   - A marker with no matching `citation_id` in `citations` is dropped, and the item becomes `unverified: true`.
   - An item with no markers is `unverified: true`, and the UI shows an "Unverified" chip. It's never hidden.
   - The API returns each reason and concern as `{text, citation_ids, unverified}`, keeping H2's order, top 3 for list items and all of them for the detail.
   - The summary's citations are any `[cN]` markers inside `summary`. The amount and deadline citations are the citation whose `quote` contains `amount_text` / `deadline_text` (first match), or none.
5. **Save, pass and reset.**
   - `POST /v1/grants/{id}/save` and `POST /v1/grants/{id}/pass` call `set_candidate_status`.
   - `POST /v1/grants/{id}/reset` sets the status back to `new`. It's used for Undo, and from the Shortlist and Passed tabs.
   - All three are idempotent: setting the current status again returns 200 with `changed: false`.
   - Pass accepts an optional `{reason, reason_text}`. The reason is validated, and if `store.set_candidate_status` accepts `reason` (Requests to H0) it is passed through; otherwise it's written to the structured log as `grant.passed {grant_id, reason}`. The UI is the same either way.
   - Changing status never changes `fit_score` or anything else H2 produced.
6. **Detail.** `GET /v1/grants/{id}` returns the full candidate with derived fields, parsed reasons and concerns, `citations` and `view_original_url = url`. It doesn't call the web; the overview shows only what's stored. H4 fetches pages live.
7. **Auth.** Every endpoint needs H0's session (401 `not_signed_in`). There are no roles. The tenant always comes from settings.

## Contracts

- **Shared models used:** `GrantCandidate`, `Citation`, `Money`, `hope_core.auth.get_principal`, `hope_core.store.*`, `hope_core.errors`.
- **Endpoint models**, defined in `api/grants.py` (endpoint shapes, not shared contracts): `CitedItem{text: str, citation_ids: list[str], unverified: bool}`, `GrantCard`, `GrantDetail`, `GrantListPage`, `StatusChange`, `PassBody`. TS types are hand-written in `apps/web/src/api/grants/types.ts`.
- **Endpoints:**

  **`GET /v1/grants`**

  | Query | Type | Default | Rule |
  |---|---|---|---|
  | `status` | `new`, `saved` or `passed` | `new` | |
  | `sort` | `fit`, `deadline`, `amount` or `newest` | `fit` | `fit`: score desc, then deadline asc. `deadline`: soonest first; rolling, then unknown, last. `amount`: `amount_max` desc, unknown last. `newest`: `discovered_at` desc |
  | `q` | string, 1-100 chars | none | Case-insensitive match on title, funder, summary and domain |
  | `deadline_within_days` | int 1-365 | none | Keeps rows with `0 <= days_left <= n` |
  | `include_past` | bool | `false` | |
  | `limit` | int 1-100 | 20 | |
  | `offset` | int ≥ 0 | 0 | |

  A bad value returns 422 `invalid_query`, and `detail` names the parameter. Response 200:

  ```json
  {
    "items": [{
      "grant_id": "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10",
      "title": "Youth Development Grants 2027",
      "funder": "The Cleveland Foundation",
      "url": "https://www.clevelandfoundation.org/grants/youth-development",
      "domain": "clevelandfoundation.org",
      "summary": "Two-year grants for out-of-school programs that build skills for youth 12-18 in Cuyahoga County.",
      "amount_text": "up to $50,000 per year", "amount_max": {"amount_minor": 5000000, "currency": "USD"},
      "deadline_text": "Applications due March 3, 2027", "deadline": "2027-03-03", "days_left": 116, "urgency": "later",
      "fit_score": 86, "fit_band": "strong",
      "reasons": [
        {"text": "Funds youth mentoring, which matches your Mentor Futures program", "citation_ids": ["c1", "c4"], "unverified": false},
        {"text": "Serves Cuyahoga County, inside your service area", "citation_ids": ["c2"], "unverified": false},
        {"text": "Award size fits your $1.2M budget", "citation_ids": [], "unverified": true}],
      "concerns": [{"text": "Requires a 2025 audited financial statement", "citation_ids": ["c3"], "unverified": false}],
      "citations": [
        {"citation_id": "c1", "kind": "web", "url": "https://www.clevelandfoundation.org/grants/youth-development",
         "title": "Youth Development | The Cleveland Foundation", "quote": "supports mentoring and out-of-school programs for youth ages 12-18",
         "profile_path": null, "retrieved_at": "2026-11-07T14:02:11Z"},
        {"citation_id": "c4", "kind": "profile", "url": null, "title": null,
         "quote": "Mentor Futures pairs 150 youth a year with trained adult mentors", "profile_path": "programs[0].description", "retrieved_at": null}],
      "status": "new", "discovered_at": "2026-11-07T14:02:30Z"
    }],
    "total": 23, "limit": 20, "offset": 0,
    "counts": {"new": 23, "saved": 4, "passed": 6},
    "hidden_past": 2
  }
  ```

  `citations` on list items includes only the citations referenced by the returned reasons, concerns and summary.

  **`GET /v1/grants/{grant_id}`** returns 200 `GrantDetail`: the `GrantCard` fields plus `eligibility_summary`, all `reasons` and `concerns`, `summary_citation_ids`, `amount_citation_id`, `deadline_citation_id`, all `citations`, `found_by_job_id` and `view_original_url`. Errors: 404 `grant_not_found`.

  **`POST /v1/grants/{grant_id}/save`** and **`POST /v1/grants/{grant_id}/reset`** take an empty body and return 200 `{"grant_id": "3f6b…", "status": "saved", "previous_status": "new", "changed": true}`. Errors: 404 `grant_not_found`.

  **`POST /v1/grants/{grant_id}/pass`** takes an optional body: `{"reason": "not_a_fit" | "too_small" | "deadline_too_soon" | "not_eligible" | "other", "reason_text": "≤ 300 chars, only with other"}`. It returns the same response as save, with `"status": "passed"`. Errors: 404 `grant_not_found`, 422 `invalid_reason`.

- **Events and database:** none.

## Owns

```text
services/pillar/src/hope_pillar/api/grants.py
services/pillar/tests/snapshots/openapi/grants.json
services/pillar/tests/test_grants_api.py
apps/web/src/features/grants/**
apps/web/src/api/grants/**
apps/web/src/app/grants/page.tsx
apps/web/src/app/grants/[grantId]/page.tsx
db/migrations/0710-0719 (reserved, unused)
docs/specs/README.md (this spec's status row only)
```

## Demo seed

H3 has no Python package, so it has no `demo.seed()`. The candidates come from H2's seed,
which runs discovery on `RecordedWebTools`. For the demo, the curation happens live.
`api/grants/fixture.ts` (SC25 11 / SC26 11) covers every UI state offline. The API tests
seed their own rows with `store.upsert_candidate`, using the 8 fixture candidates listed in SC25 11.

## Acceptance criteria

- [ ] AC1 `GET /v1/grants` returns the requested status tab sorted by each `sort` option exactly as specified, with `total`, `counts` and `hidden_past` correct.
- [ ] AC2 `q`, `deadline_within_days`, `include_past`, `limit` and `offset` filter and page correctly. Bad values return 422 `invalid_query`.
- [ ] AC3 `days_left`, `urgency` (all 6 values) and `fit_band` are derived by code, using a fixed clock in tests.
- [ ] AC4 Reasons and concerns are parsed into `{text, citation_ids, unverified}`. An unknown marker or a missing marker gives `unverified: true`, and no item is ever dropped.
- [ ] AC5 Save, pass and reset change the status, are idempotent (`changed: false`), and never change other fields. Pass validates `reason` (422 `invalid_reason`).
- [ ] AC6 `GET /v1/grants/{id}` returns the full detail with every citation and `view_original_url`. An unknown id returns 404 `grant_not_found`.
- [ ] AC7 Without a session, every endpoint returns 401 `not_signed_in`.
- [ ] AC8 The router uses only `hope_core.store` functions (no SQL in `grants.py`), and only `openapi/grants.json` changes.
- [ ] AC9 SC25 and SC26 acceptance criteria pass.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/pillar/tests/test_grants_api.py::test_list_sorts_counts_hidden_past` | api (db) |
| AC2 | `test_grants_api.py::test_list_filters_paging` (parametrized), `::test_invalid_query` | api |
| AC3 | `test_grants_api.py::test_derived_urgency_and_band` (parametrized over the 6 urgencies) | api |
| AC4 | `test_grants_api.py::test_reason_citation_parsing` | api |
| AC5 | `test_grants_api.py::test_save_pass_reset_idempotent`, `::test_pass_reason_validation` | api |
| AC6 | `test_grants_api.py::test_detail_and_not_found` | api |
| AC7 | `test_grants_api.py::test_requires_session` | api |
| AC8 | `test_grants_api.py::test_router_uses_store_only` (AST: no `execute(` in `grants.py`), `test_openapi.py::test_router_snapshots` | unit/api |
| AC9 | `apps/web/src/features/grants/*.test.tsx` (SC25 14, SC26 14) | web unit |

## Out of scope

- Re-scoring.
- Editing grant facts.
- Bulk actions.
- Sharing.
- Notifications.
- Live page fetching on the overview (H4 does that).

## Requests to H0

1. `store.set_candidate_status(tx, grant_id, status, *, reason: str | None = None, reason_text: str | None = None, actor: str | None = None)`, plus `status_changed_at` / `status_changed_by` / `pass_reason` / `pass_reason_text` columns on `grant_candidates`. Without this, H3 logs pass reasons instead of storing them.
2. `store.count_candidates(tx) -> dict[str, int]`. Without it, H3 counts from the three lists.

## Requests to H2

- End every `fit_reasons` and `concerns` string with its citation markers (`… [c2]` or `… [c1][c4]`), keep each string at most 140 characters before the markers, and put the most important reason first.
- Put `[cN]` markers inside `summary` where a sentence is sourced.
- Make `citations[].quote` contain `amount_text` and `deadline_text` verbatim, so H3 can attach them.

## Requests to H4 and H5

- **H4.** `apps/web/src/api/brief/` exports `getBriefStatus(grantId: string): Promise<BriefStatus>`, where `BriefStatus = { status: "none" | "generating" | "ready" | "failed"; generated_at: string | null; job_id: string | null; error: string | null }`. It's backed by H4's GET endpoint; a 404 maps to `status: "none"`. The route is `/grants/[grantId]/brief`.
- **H5.** `apps/web/src/api/proposal/` exports `getProposalStatus(grantId: string): Promise<ProposalStatus>`, where `ProposalStatus = { status: "none" | "drafting" | "ready" | "failed"; updated_at: string | null; sections_total: number; sections_edited: number; unverified_count: number }`. It's backed by H5's GET endpoint; a 404 maps to `none`. The route is `/grants/[grantId]/proposal`.
- Both functions throw `ProblemError` (from `lib/problem.ts`) on other errors. SC26 shows "Status unavailable" in that case and keeps the CTA enabled.

## Decisions needed (recommended defaults)

1. **Pass-reason storage.** Recommended default: Request to H0 item 1. Until it lands, reasons are logged only, and H3 adds no migration.
2. **Does "Build application brief" require saving first?** Recommended default: no, but clicking it on a `new` grant saves the grant first, because building a brief means the user is interested.
3. **"Draft proposal" before a brief exists.** Recommended default: disabled until the brief is `ready`, with the hint "Build the application brief first: Hope needs the grant's questions."
4. **Past-deadline grants.** Recommended default: hidden from New and Shortlist, with a count and a "Show" link.
