# API catalog (`/v1`)

> **Hackathon agents (H0-H5): this map is the long-term ("Later") product, not your build target.** Use the H0-H5 table in [`README.md`](README.md), your feature spec, [`contracts/`](../../contracts/) and `apps/web/docs/hope/file-ownership.md`. The hackathon web app lives under `/hope/*` and `/onboarding`, with no `src/`.

The one list of Hope's HTTP endpoints. All of them are served by the pillar app
(`uvicorn hope_pillar.api:app`), one router module per spec (see `FOLDERS.md`). The MVP is
single-tenant: clients never send a tenant; the server uses `HOPE_TENANT_ID` (S00). Until S01
adds OIDC, dev requests identify the user with `X-Hope-User` / `X-Hope-Roles`. Errors use the
`application/problem+json` model from `hope_core.errors` (S00), with a machine-readable `code`;
a stale artifact returns `409` with `code: "stale_artifact"` and `current_hash`.

Request and response shapes are defined in the owning spec. Status: `Built` is on main,
`S00` means S00 moves or changes it, `New` means the owning spec adds it.

| Method | Path | Purpose | Owning spec | Status | Called by |
|---|---|---|---|---|---|
| POST | `/v1/ingest/opportunities` | Submit a raw opportunity (Idempotency-Key) | pillar | Built | connectors |
| POST | `/v1/ingest/artifacts` | Upload a source document | pillar | Built | connectors, SC11 |
| GET | `/v1/me` | Current user, roles, the agency | S01 | New | every screen (shell) |
| GET | `/v1/users` | List users and roles | S01 | New | SC17 |
| POST | `/v1/users` | Invite a user | S01 | New | SC17 |
| PATCH | `/v1/users/{user_id}` | Change roles / deactivate | S01 | New | SC17 |
| GET | `/v1/approvals` | Approval inbox (`status`, `gate`, `assignee=me`) | S02 | New | SC05, SC02 |
| GET | `/v1/approvals/{request_id}` | One HITL request with artifact preview | S02 | New | SC06 |
| POST | `/v1/workflows/{workflow_id}/signals/{gate}` | Approve / reject a gate (hash-checked) | pillar | Built | SC06, SC13, SC20, SC21 |
| GET | `/v1/opportunities` | Search and list opportunities | S03 | New | SC04, SC02 |
| GET | `/v1/opportunities/{opportunity_id}` | One opportunity | pillar | Built | SC04, SC03 |
| GET | `/v1/opportunities/{opportunity_id}/documents` | Source documents and versions | S03 | New | SC04 |
| GET | `/v1/artifacts/{sha256}/download` | Short-lived download URL | S03 | New | SC04, SC12, SC22 |
| POST | `/v1/opportunities/{opportunity_id}/pursue` | Start a lifecycle workflow (to HITL-1) | S04 | New | SC03, SC04 |
| GET | `/v1/workflows` | List workflows (`agency_id`, `state`) | S04 | New | SC07, SC02 |
| GET | `/v1/workflows/{workflow_id}` | Workflow state, gates, timeline | pillar, S04 adds transitions | Built | SC08 |
| GET | `/v1/workflows/{workflow_id}/history` | State transitions and events | S04 | New | SC08 |
| GET | `/v1/agencies/{agency_id}/matrix` | Opportunity matrix (S05 adds scores, eligibility) | pillar, S05 | Built | SC03, SC02 |
| GET | `/v1/agencies/{agency_id}/matrix/{opportunity_id}/explanation` | Per-dimension evidence | S05 | New | SC03 |
| PUT | `/v1/agencies/{agency_id}/matrix/{opportunity_id}/disposition` | Watch / skip / pursue-later | S05 | New | SC03 |
| GET | `/v1/frameworks/{framework_id}` | Framework + budget ledger | pillar | Built | SC13, SC19 |
| GET | `/v1/frameworks/{framework_id}/budget` | Budget lines, totals, cap checks, SF-424A | S06 | New | SC13 |
| PUT | `/v1/frameworks/{framework_id}/budget/lines` | Edit line bases; engine recomputes | S06 | New | SC13 |
| POST | `/v1/frameworks/{framework_id}/recompute` | Recompute budget (emits framework.recompute_requested) | S06 | Built (501) | SC13 |
| GET | `/v1/rules` | Draft eligibility rules (`status`) | S08 | New | SC14 |
| POST | `/v1/rules/{rule_id}/approve` and `/reject` | Approve / reject an LLM-drafted rule | S08 | New | SC14 |
| POST | `/v1/agencies` | Create agency (S09: via HITL-0) | profile, S09 | Built | SC11 |
| GET | `/v1/agencies/{agency_id}/profile` | Current or as-of profile | profile | S00 | SC09 |
| PATCH | `/v1/agencies/{agency_id}/profile` | Propose changes (protected fields go to HITL-0) | profile | S00 | SC09 |
| GET | `/v1/agencies/{agency_id}/profile/history`, `/diff`, `/completeness` | History, diff, completeness | profile | Built | SC09 |
| GET | `/v1/agencies/{agency_id}/profile/proposals` | Pending HITL-0 proposals | profile | Built | SC10 |
| POST | `/v1/agencies/{agency_id}/profile/proposals/{proposal_id}/approve` and `/reject` | HITL-0 decision | profile | Built | SC10 |
| POST | `/v1/agencies/{agency_id}/sources` | Upload a 990 / audit / NICRA (emits profile.source_uploaded) | S09 | New | SC09, SC11 |
| GET | `/v1/agencies/{agency_id}/registration` | Live SAM.gov registration check | S09 | New | SC09, SC11 |
| GET | `/v1/parse-reviews` | Documents that need a human parse review | S10 | New | SC12 |
| GET | `/v1/parse-reviews/{review_id}` | Extraction, evidence spans, conflicts | S10 | New | SC12 |
| POST | `/v1/parse-reviews/{review_id}/resolve` and `/discard` | Correct fields or discard | S10 | New | SC12 |
| GET | `/v1/sources/schedules` and PUT `/v1/sources/schedules/{source}` | Discovery polling schedule | S10 | New | SC17 |
| GET | `/v1/notifications` | In-app notifications | S12 | New | SC16, shell |
| POST | `/v1/notifications/{notification_id}/read` | Mark read | S12 | New | SC16 |
| GET | `/v1/me/notification-preferences` and PUT | Channels per event type | S12 | New | SC16 |
| GET | `/v1/audit` | Audit trail (`entity_type`, `entity_id`, `actor`, `from`, `to`) | S13 | New | SC15, SC08 |
| GET | `/v1/frameworks/{framework_id}/narratives` | Narrative sections | S17 | New | SC19 |
| POST | `/v1/frameworks/{framework_id}/narratives/draft` | Draft / redraft sections | S17 | New | SC19 |
| PUT | `/v1/frameworks/{framework_id}/narratives/{section_id}` | Human edit of a section | S17 | New | SC19 |
| GET | `/v1/frameworks/{framework_id}/verification` | Verifier findings | S18 | New | SC19, SC21 |
| GET | `/v1/frameworks/{framework_id}/compliance` | Compliance checklist and findings | S19 | New | SC20 |
| POST | `/v1/frameworks/{framework_id}/compliance/run` | Re-run compliance checks | S19 | New | SC20 |
| GET | `/v1/integrations` | Connected integrations | S24 | New | SC18 |
| POST | `/v1/integrations/{kind}/connect`, DELETE `/v1/integrations/{kind}` | Connect / disconnect (OAuth) | S24 | New | SC18 |
| POST | `/v1/integrations/{kind}/sync` | Run a sync now | S24 | New | SC18 |
| POST | `/v1/frameworks/{framework_id}/package` | Assemble the application package | S21 | New | SC22 |
| GET | `/v1/packages/{package_id}` | Package manifest, files, checks | S21 | New | SC22 |
| POST | `/v1/packages/{package_id}/authorize` | HITL-5 submission authorization | pillar | Built | SC22 |
| GET | `/v1/packages/{package_id}/submission` | Submission status and tracking number | S22 | New | SC22 |
| GET | `/v1/awards` and `/v1/awards/{award_id}` | Awards and their milestones and reports | S23 | New | SC23 |
| POST | `/v1/awards` | Record an award outcome | S23 | New | SC23 |
| PUT | `/v1/awards/{award_id}/reports/{report_id}` | Update a funder report | S23 | New | SC23 |

S00 removes the pillar's duplicate `GET/PATCH /v1/agencies/{agency_id}/profile` and mounts
the profile service's router as the one owner of `/v1/agencies/**`.
