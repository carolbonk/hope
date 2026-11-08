# H7: Opportunity matrix and My bids

| | |
|---|---|
| Wave | After H6 (a bid prepares an H6 application) |
| Depends on | H0 (auth, store); H3 save (`save_grant`); H6 application, checklist and requirements read |
| Screens | SC30 `/hope/matrix`, SC31 `/hope/bids`, SC32 `/hope/bids/[oppId]` |
| Migrations | `db/migrations/0730_bids.sql` (range 0730-0739) |
| Status | Built (PR #78 backend, PR #80 web) |

Written from the code on main; it describes what is built.

## Goal

Help a team choose which grants to prepare and get each one ready on time:
1. **Matrix:** every opportunity in one ranked table with a sample score, so the team picks what to prepare.
2. **My bids:** for each grant being prepared, every funder requirement gets an owner, an internal due date, a status,
   an evidence reference and a review. Code decides what blocks the final review.
3. **Receipt:** staff submit on the funder's portal, then record the receipt. **Hope never submits.**

## Rules

- **Code decides.** Blockers, the plan, stale reviews and every transition are code; there is no model call in H7.
- **The funder's wording is the source.** Bid items come from the H6 checklist and keep its quote and URL.
- **Reviews are simulated.** Anyone signed in can review any item (H6 roles are out of scope).
- **Names, not emails.** `GET /v1/members` returns `user_id` and `display_name` only.
- **Tenancy.** `tenant_tx` as `hope_app`; `bids` and `bid_items` have forced RLS.

## Behaviour: backend (`services/pillar/src/hope_pillar/api/bids.py`)

### A. Starting a bid

`POST /v1/bids {grant_id}` calls H3 `save_grant` (which creates the H6 application and starts its requirements read),
then inserts the bid: 201 the first time, 200 with the same bid after that. Unknown grant: 404 `grant_not_found`.

### B. Items

One item per H6 checklist item, except the informational kinds `deadline` and `submission`. Each item has `owner`
(a user), `due` (date), `status` (`missing`/`working`/`ready`), `note` (≤ 2000), `evidence_ref` (≤ 500, a text
reference, not a file) and `review`.

- `PUT .../items/{key}` changes only the fields sent; `owner: null` / `due: null` clear them. An unknown owner is
  422 `unknown_member`. Changing status, note or evidence clears the item's review; owner or due date keep it.
- `POST .../items/{key}/review` with `approved` or `changes_requested`. The item must be `ready` (else 409
  `bid_blocked`). `changes_requested` needs a comment (422 `comment_required`) and moves the item back to `working`.
- A review stores the content hash of the funder's wording (`label`, `quote`, `url`, `limit`). When a new
  requirements read changes that wording, the review is shown as `stale` and blocks again.

### C. Blockers, plan and final review

Blockers (`blocker_list`), in order: `no_requirements` (not read yet), `checklist_incomplete` (H6 ready gate),
then per item `no_owner`, `not_ready`, `not_reviewed`, `stale_review`, and `deadline_passed`.

The plan counts back from the deadline (the requirements read's deadline, else the grant's): owners by D-14, drafts
by D-7, reviews by D-3, final review by D-1. No deadline, no plan.

`POST .../final-review` is refused with 409 `bid_blocked` and the blockers in `errors[]` while any remain. Any later
change to an item undoes the final review (event `final_review_undone`).

### D. Receipt

`POST .../submission {receipt, portal, submitted_at}` needs the final review (else 409 `bid_blocked`). It stores
`sent_by_hope: false`; after it the bid is read-only and every write is 409 `bid_submitted`.

### E. Concurrency and history

Every write needs `If-Match: "<version>"`; a stale copy is 412 `version_mismatch`. `GET` returns `ETag`. Every
change writes an `application_events` row of kind `bid` (`started`, `item`, `review`, `final_review`,
`final_review_undone`, `submission`).

### F. API summary

| Method | Path | Result |
|---|---|---|
| GET | `/v1/bids` | `{items: BidSummary[], total}`, submitted last, then by deadline |
| POST | `/v1/bids` | `BidView` (201 new, 200 existing) |
| GET | `/v1/bids/{grant_id}` | `BidView` |
| PUT | `/v1/bids/{grant_id}/items/{key}` | `BidView` |
| POST | `/v1/bids/{grant_id}/items/{key}/review` | `BidView` |
| POST | `/v1/bids/{grant_id}/final-review` | `BidView` |
| POST | `/v1/bids/{grant_id}/submission` | `BidView` |
| GET | `/v1/members` | `{items: [{user_id, display_name}]}` |

Shapes and scenarios: `contracts/manifest.json` workflow W7, `contracts/mocks/w7/**`.

## Data (`0730_bids.sql`)

`bids (application_id PK → applications, tenant_id, version, final_review jsonb, submission jsonb, created_by, ...)`
and `bid_items (application_id, item_key) PK, owner → users, due, status, note, evidence_ref, review jsonb, ...)`,
both with forced tenant RLS. The migration adds `bid` to `application_events.kind`.

## Behaviour: web

### SC30 `/hope/matrix`

- Every opportunity from `useOpportunities()`, scored in the browser (`components/hope/bids/score.ts`): focus 35%,
  geography 20%, size against the budget 20%, effort (pending profile documents) 15%, time to deadline 10%; an
  unknown value counts as 50. Labelled "Sample score"; it is not a chance of winning.
- Recommendation: Pursue ≥ 70, Consider ≥ 55, else Watch; not qualified or closed is always Skip.
- Sort by score or deadline; filter by recommendation, eligibility and deadline window (30/60/90 days).
- "Prepare bid" calls `POST /v1/bids` and opens the bid; enabled only online, for server grant UUIDs, not for Skip.
  A grant that already has a bid shows "Open bid". Offline the table works and says to sign in.

### SC31 `/hope/bids`

Counts by phase (preparing, final review done, submitted) and one card per bid with its deadline, ready/total and
blockers. Empty: a link to the matrix. Offline: "My bids needs the Hope server."

### SC32 `/hope/bids/[oppId]`

Three tabs: **Requirements** (a card per item with the funder's quote, owner, due date, status, evidence, note,
approve / request changes, stale review), **Preparation plan** (milestones and items by due date) and **Final
review** (blockers with Resolve links, the final review, then the receipt form). Every write sends `If-Match`; a
412 reloads and shows a notice that scrolls into view and takes focus; 409/422 show the server's message. After the
receipt the bid is read-only and each item's note and evidence stay visible.

Links in: the nav (Matrix, My bids), the matrix, and "Open bid" on the Saved card and the application workspace
header when the grant has a bid.

## Owns

```text
db/migrations/0730_bids.sql
services/pillar/src/hope_pillar/api/bids.py
services/pillar/tests/test_bids_api.py
services/pillar/tests/snapshots/openapi/bids.json
apps/web/app/hope/matrix/**
apps/web/app/hope/bids/**
apps/web/components/hope/bids/**
contracts/mocks/w7/**
```

## Acceptance criteria

- [x] AC1 Starting a bid saves the grant and creates one bid; starting again returns it (200).
- [x] AC2 Items match the H6 checklist minus `deadline`/`submission`.
- [x] AC3 Writes without the current version are 412; unknown owner 422; unknown item or bid 404.
- [x] AC4 Changing status, note or evidence clears a review; owner/due keep it; changed funder wording makes it stale.
- [x] AC5 The final review is refused while blockers remain and undone by any later change.
- [x] AC6 The receipt needs the final review and makes the bid read-only; `sent_by_hope` is always false.
- [x] AC7 Another tenant can't see a bid (RLS); every route needs a session.
- [x] AC8 `/v1/members` never returns emails.
- [x] AC9 Responses match the W7 contract mocks.
- [x] AC10 The matrix ranks by the sample score, filters, and only prepares server grants online.

## Test plan (offline)

API: `services/pillar/tests/test_bids_api.py` (every route, 401/404/409/412/422, RLS, contract shapes; refresh the
mocks with `UPDATE_CONTRACT_MOCKS=1`). OpenAPI snapshot `snapshots/openapi/bids.json`. Web (vitest, mocked API):
`components/hope/bids/*.test.ts(x)`, `app/hope/matrix/page.test.tsx`, `app/hope/bids/page.test.tsx`,
`app/hope/bids/[oppId]/page.test.tsx`.

## Out of scope

Submitting to funders, file upload for evidence, real reviewer roles, reminders and notifications, a server-side
matrix score, demo seed bids.

## Decisions needed

1. One ready gate or two: the application's "Mark ready" and the bid's final review are separate, and the receipt
   doesn't move the application's stage. Default: keep both.
