# SC26: Grant overview (folded into Discover and the workspace)

| | |
|---|---|
| Route | none. Don't build `/grants/[grantId]` or `/hope/grants/*` |
| Where it lives | the Discover card and its details dialog (`app/hope/discover/page.tsx`, H2) and the workspace header (`app/hope/applications/[oppId]/page.tsx`, H4) |
| Built by | PR #34 (UI). H3 owns only the backend detail endpoint |
| Primary users | Executive director or development lead deciding whether to pursue one opportunity |
| Status | Built; no web work for H3 |

## 1. Purpose and user goals

The overview used to be its own page: "everything Hope knows about this grant, and the next step". In the
Hope frontend that content is split across two places that already exist:
1. **Before deciding** (Discover card + "Eligibility & opportunity details" dialog): what is it, how much,
   when, why it could fit, does the org qualify, and where it comes from.
2. **After saving** (workspace header): the same facts plus the stage and the next action.

This spec maps each overview element to where it lives now, so no agent builds a second overview.

## 2. Where each element lives

| Element | Where | Owner | Data | Rules |
|---|---|---|---|---|
| Name and funder | Card + workspace `h1` | H2 / H4 | `o.name`, `o.funder` | |
| Amount | Card ("$25,000–$50,000", "Funding range") + header | H2 / H4 | `o.amountMin`, `o.amountMax`, `o.currency` | Whole units in the UI; integer `amount_minor` on the wire (H2's adapter divides by 100). `null` → "Amount not found" |
| Deadline | Card ("21 days", "Due … · 21 days") + header (red when ≤ 14 days) | H2 / H4 | `o.deadline`, `daysUntil` | `null` → "Deadline not found" / "Rolling, no fixed date", never red |
| Why it could fit | Card | H2 (page), H4 (`matchReasons`) | `matchReasons(o, profile)` | Code, not a model: shared focus, geography, purpose, award ≤ 40 % of budget. "No clear match with your profile yet." when empty |
| Eligibility | Card badge + details dialog rows | H2 (page), H4 (`eligibility`, `requirementStatus`) | `o.requirements`, profile, evidence | "Meets known requirements" / "Needs review" / "Does not qualify" |
| Funder context | Details dialog | H2 | `o.funderContext` | Empty state "No sourced information on previous grantees…" |
| Source / view original | Card + dialog | H2 | `o.source` | Demo: "Fictional demo opportunity — not a real program". Verified: the URL and "Verified {date}" |
| Stage and next step | Workspace `StageBar` + "Next action" | H4 | `application.stage` | |
| Save / Pass / Undo | Discover deck buttons, swipe, ← → U | H2 (page), H4 (`decide`/`undo`) | `useHope()` | Mirrored to the backend by H3's `lib/hope/sync/decisions.ts` |

H2's LLM reasons, concerns and citations (`GrantCandidate.fit_reasons`, `concerns`, `citations`) are in the
API but not shown in the hackathon UI. `Opportunity` has no field for them.

## 3. Wireframe

None: see SC24 (Discover card) and SC27 (workspace header).

## 4. Backend detail (H3)

`GET /v1/grants/{grant_id}` stays in the contract for API consumers and H2's adapter. No hackathon page
calls it. It returns `GrantDetail` exactly as `contracts/mocks/w4/grants.get/ok.json`, or 404
`grant_not_found` (`not_found.json`). The rules (derived fields, citation markers, `view_original_url`) are
in H3 Behaviour 2. It makes no model or web call.

## 5. States

The empty, not-found and loading states are those of SC24 and SC27:
- The workspace without an application shows "This application isn't in this browser. It may have been
  saved in another browser or cleared."
- Discover with no cards shows its empty state.

## 6. Acceptance criteria

- [ ] AC1 No `/grants` or `/hope/grants` route exists in `apps/web/app`.
- [ ] AC2 `GET /v1/grants/{grant_id}` matches the contract mock and returns 404 `grant_not_found` for an unknown id (H3 AC6, AC8).

## 7. Test plan

| AC | Test |
|---|---|
| AC1 | Checked in review: `apps/web/app/` has no `grants` folder |
| AC2 | `services/pillar/tests/test_grants_api.py::test_detail_and_not_found`, `::test_matches_contract_mocks` |

## 8. Open questions

- **Show H2's cited LLM reasons on the card later?** Recommended default: yes after the hackathon. Add an
  optional `Opportunity.fit` (`{score, reasons[{text, citationIds, unverified}]}`) through `lib/hope/types.ts`
  and H2's adapter, then render it on the card next to `matchReasons`.
