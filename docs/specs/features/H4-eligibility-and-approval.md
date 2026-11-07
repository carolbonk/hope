# H4: Eligibility and internal approval

| | |
|---|---|
| Wave | Hackathon (parallel with H1-H3, H5, after H0) |
| Depends on | H0; the Hope frontend from PR #34 (`apps/web` = the zip's structure) |
| Screens | SC27 `/hope/applications/[oppId]` (stages `saved`, `eligibility`, `approval`) |
| Migrations | none (0720-0729 stays reserved) |
| Status | Built in the browser by PR #34; this spec covers what it must keep doing, plus its tests |

## Goal

When a nonprofit saves an opportunity, Hope opens one **application workspace** for that pair. H4 owns
the first half of the workspace:
1. An **eligibility checklist** for this call, from recorded evidence and the profile.
2. The **documents this call asks for**, read from the shared dossier.
3. A **simulated internal approval** (Program review, then Director review).

Drafting (H5) unlocks only after both approvals. This replaces the earlier live-fetched "application
brief". The flow comes from the Hope frontend (`apps/web/docs/hope/data-contract.md`).

## Behaviour

### Application record
- One `Application` per org/opportunity: `id = applicationId(ORG_ID, oppId)` = `app:org-local-1:<oppId>`.
- It is created when the user saves the opportunity (Discover / Saved). Passing and saving again reuses the
  same record, and undo never deletes edits.
- Stages, in order (`STAGES` in `lib/hope/store.ts`): `saved → eligibility → approval → drafting → ready`.
  `StageBar` shows them. `activity[]` keeps the last 50 events.
- Storage: `localStorage` key `hope:state:v1`, shape `{ version: 1, profile, decisions, history, applications }`.
  The UI says it is saved in this browser only.

### Eligibility (code decides, no LLM)
- `requirementStatus(req, profile, app)`: recorded evidence (`app.evidence[req.id]`) wins. Otherwise a known
  profile fact (`req.field` / `req.expect`, e.g. `has501c3 = yes`, `annualBudget ≥ 250000`). Otherwise `unknown`.
- `eligibility(opp, profile, app)`: `meets` when every requirement is Yes, `not_qualified` when any is No,
  and `needs_review` when any is Unknown.
- Each requirement row has Yes / No / Unknown buttons and an "Evidence / note" field. A row decided by the
  profile shows "From your profile · {status}".
- `unknown` and `""` are never shown as "No".
- Eligibility is per call. It is separate from "profile complete" and "documentation reviewed".

### Required documents
- `oppDocs(opp, profile)` lists the documents this call asks for (`opp.docs[]`, `federal`). Each one shows its
  status from the organization dossier (`pending | declared | not_applicable`, and expired).
- Documents are never copied into the application. "Update in your dossier →" links to `/hope/profile`.

### Internal approval (simulated)
- **Stage gate:** `eligibility → approval` only when no requirement is No or Unknown. Otherwise the button
  is disabled with "Resolve unknown or failed requirements first."
- Program review: Approve or Send back. Director review is enabled only after the program approves.
- Send back requires a comment ("Add a comment explaining what to change.") and returns the stage to `eligibility`.
- Both approved → stage `drafting`, and the H5 draft panel unlocks.
- These are always labelled **"Approved (simulated)"**, with the note "Simulated roles — this prototype has no
  sign-in, so anyone in this browser can click these." They are internal readiness steps, never funder approval.

### Comments and activity
- "Internal review comments" (author "You (local)") and the activity log are on the same page. Both are owned here.

## Owns: only edit these paths

```text
apps/web/app/hope/applications/[oppId]/page.tsx   (Workspace, EligibilityPanel, ApprovalPanel, CommentsPanel)
apps/web/lib/hope/store.ts                        (eligibility, requirementStatus, stage gates; shared types with H3 by agreement)
apps/web/lib/hope/dossier.ts                      (oppDocs, applicability)
apps/web/lib/hope/**/*.test.ts and apps/web/app/hope/applications/**/*.test.tsx  (new)
```

H5 owns `components/hope/draft/**`, `lib/hope/draft.ts` and `app/api/hope/draft/**`. `lib/hope/types.ts`
and `lib/hope/i18n.ts` are shared; add keys, never rename them.

## Acceptance criteria

- [ ] AC1 Saving an opportunity creates `app:org-local-1:<oppId>` at stage `saved`; pass + save again keeps the same record and edits.
- [ ] AC2 Evidence beats the profile, the profile beats Unknown; `meets` / `not_qualified` / `needs_review` follow the rule above.
- [ ] AC3 "Send to internal approval" is disabled while any requirement is No or Unknown.
- [ ] AC4 Director review is disabled until program approval; Send back without a comment shows the exact error.
- [ ] AC5 Both approvals move the stage to `drafting`. The UI says "Approved (simulated)" and never "verified".
- [ ] AC6 Required documents come from the dossier with their status; no file is stored.
- [ ] AC7 EN and ES copy both render (toggle in the header).

## Test plan (Vitest, offline)

- `lib/hope/store.test.ts`: the `requirementStatus` / `eligibility` truth table and the stage-gate transitions.
- `lib/hope/dossier.test.ts`: `oppDocs` and `applicability` for US / non-US / no-country, `w9`, `sam` / `uei`, `child_protection`.
- `app/hope/applications/[oppId]/page.test.tsx`: renders with a seeded `hope:state:v1`, and runs approve / send back / gate disabled.

## Later (backend track, not the hackathon)

`GET /api/orgs/:orgId/applications`, `PATCH /api/applications/:appId` (section-level patch + `updatedAt`) and
`POST /api/applications/:appId/approvals`, with sign-in and server-enforced roles. Only then may "simulated" go.

## Out of scope

Real reviewer identity, funder submission (Hope never submits), and fetching funder pages.
