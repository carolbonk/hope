# Screens

> **Hackathon agents (H0-H5): this map is the long-term ("Later") product, not your build target.** Use the H0-H5 table in [`README.md`](README.md), your feature spec, [`contracts/`](../../contracts/) and `apps/web/docs/hope/file-ownership.md`. The hackathon web app lives under `/hope/*` and `/onboarding`, with no `src/`.

Every screen in the web app (`apps/web`), the spec that builds it, and the endpoints it calls.
Each screen has its own spec in `screens/` with layout, states, interactions and an exact
request/response per call. The endpoints are defined in [`API.md`](API.md).

| Screen | Route | Feature folder | Built by | Endpoints called | Status |
|---|---|---|---|---|---|
| SC01 Sign-in | `/login` | `session` | S01 | `GET /v1/me` | Draft |
| SC02 Dashboard | `/` | `dashboard` | S31 | `GET /v1/approvals?assignee=me`, `GET /v1/workflows`, `GET /v1/agencies/{id}/matrix?limit=5`, `GET /v1/opportunities?deadline_before=` | Draft |
| SC03 Opportunity matrix | `/matrix` | `matrix` | S05 | `GET /v1/agencies/{id}/matrix`, `GET .../matrix/{opp}/explanation`, `PUT .../matrix/{opp}/disposition`, `POST /v1/opportunities/{id}/pursue` | Built (basic), Draft |
| SC04 Opportunity detail | `/opportunities/[opportunityId]` | `opportunities` | S03 | `GET /v1/opportunities/{id}`, `GET .../documents`, `GET /v1/artifacts/{sha}/download`, `POST .../pursue` | Draft |
| SC05 Approval inbox | `/approvals` | `approvals` | S02 | `GET /v1/approvals` | Built (fixture), Draft |
| SC06 Approval detail and decision | `/approvals/[requestId]` | `approvals` | S02 | `GET /v1/approvals/{id}`, `POST /v1/workflows/{id}/signals/{gate}` | Draft |
| SC07 Workflows | `/workflows` | `workflow` | S04 | `GET /v1/workflows` | Built (fixture), Draft |
| SC08 Workflow timeline | `/workflows/[workflowId]` | `workflow` | S04 | `GET /v1/workflows/{id}`, `GET .../history`, `GET /v1/audit?entity_id=` | Built (basic), Draft |
| SC09 Agency profile | `/profile` | `profile` | S09 | `GET/PATCH /v1/agencies/{id}/profile`, `GET .../completeness`, `GET .../registration`, `POST .../sources` | Built (basic), Draft |
| SC10 Profile change review (HITL-0) | `/profile/proposals` | `profile` | S09 | `GET .../profile/proposals`, `POST .../approve`, `POST .../reject`, `GET .../profile/diff` | Draft |
| SC11 Agency onboarding | `/onboarding` | `onboarding` | S09 | `POST /v1/agencies`, `POST .../sources`, `GET .../registration`, `GET .../profile/proposals` | Draft |
| SC12 Parse review | `/parse-review`, `/parse-review/[reviewId]` | `parse-review` | S10 | `GET /v1/parse-reviews`, `GET .../{id}`, `POST .../resolve`, `POST .../discard`, `GET /v1/artifacts/{sha}/download` | Draft |
| SC13 Budget review (HITL-2) | `/frameworks/[frameworkId]/budget` | `budget` | S06 | `GET /v1/frameworks/{id}/budget`, `PUT .../budget/lines`, `POST .../recompute`, `POST /v1/workflows/{id}/signals/HITL-2` | Draft |
| SC14 Eligibility rule review | `/rules` | `rules` | S08 | `GET /v1/rules`, `POST /v1/rules/{id}/approve`, `/reject` | Draft |
| SC15 Audit trail | `/audit` | `audit` | S13 | `GET /v1/audit` | Draft |
| SC16 Notifications | `/notifications` | `notifications` | S12 | `GET /v1/notifications`, `POST .../read`, `GET/PUT /v1/me/notification-preferences` | Draft |
| SC17 Team, roles and settings | `/settings/team` | `session` | S01 | `GET/POST/PATCH /v1/users`, `GET/PUT /v1/sources/schedules` | Draft |
| SC18 Integrations | `/settings/integrations` | `integrations` | S24 | `GET /v1/integrations`, `POST .../connect`, `DELETE`, `POST .../sync` | Draft |
| SC19 Proposal workspace | `/frameworks/[frameworkId]/draft` | `proposal` | S20 | `GET /v1/frameworks/{id}`, `GET/POST/PUT .../narratives`, `GET .../verification` | Draft |
| SC20 Compliance attestation (HITL-3) | `/frameworks/[frameworkId]/compliance` | `compliance` | S19 | `GET .../compliance`, `POST .../compliance/run`, `POST /v1/workflows/{id}/signals/HITL-3` | Draft |
| SC21 Executive approval (HITL-4) | `/frameworks/[frameworkId]/approve` | `proposal` | S20 | `GET /v1/frameworks/{id}`, `GET .../verification`, `POST /v1/workflows/{id}/signals/HITL-4` | Draft |
| SC22 Package and submission (HITL-5) | `/packages/[packageId]` | `packages` | S21, S22 | `GET /v1/packages/{id}`, `POST .../authorize`, `GET .../submission`, `GET /v1/artifacts/{sha}/download` | Draft |
| SC23 Awards and reporting | `/awards`, `/awards/[awardId]` | `awards` | S23 | `GET /v1/awards`, `GET .../{id}`, `POST /v1/awards`, `PUT .../reports/{id}` | Draft |
| SC30 Opportunity matrix (hackathon) | `/hope/matrix` | `components/hope/bids` | H7 | `GET /v1/bids`, `POST /v1/bids` | Built |
| SC31 My bids | `/hope/bids` | `components/hope/bids` | H7 | `GET /v1/bids` | Built |
| SC32 Bid workspace | `/hope/bids/[oppId]` | `components/hope/bids` | H7 | `GET /v1/bids/{grant_id}`, `PUT .../items/{key}`, `POST .../items/{key}/review`, `POST .../final-review`, `POST .../submission`, `GET /v1/members` | Built |

The app shell (nav, user menu, notification bell) calls `GET /v1/me` and
`GET /v1/notifications?unread=true`. S00 pre-fills `apps/web/nav.ts` with every
route above; a route whose screen isn't built yet shows a "Coming soon" state.
