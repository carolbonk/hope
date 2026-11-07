# H5: Application draft (6 sections, AI or template)

| | |
|---|---|
| Wave | Hackathon (parallel with H1-H4, after H0) |
| Depends on | H0; H4's stage gate (drafting unlocks after both simulated approvals) |
| Screens | SC28 `/hope/applications/[oppId]` (stages `drafting`, `ready`) |
| Migrations | none (0800-0809 stays reserved) |
| Status | Built by PR #34 (Next.js route + panel); this spec covers what it must keep doing, plus its tests |

## Goal

Once a saved opportunity has both internal approvals, Hope drafts the application in 6 fixed sections from
the organization profile and the opportunity. The user edits each section, copies the draft or downloads it
as Markdown, and marks it ready for **human** submission. Hope never submits. This replaces the earlier
"cited answers to the grant's questions".

## Behaviour

### Sections
`SECTION_IDS` = `program`, `alignment`, `logicModel`, `objectives`, `budget`, `budgetNarrative`:
- `program`: Program description
- `alignment`: Alignment with mission & outcomes
- `logicModel`: Logic model (inputs, activities, outputs, outcomes, impact)
- `objectives`: 3-5 measurable objectives (target, date and measure)
- `budget`: line items that sum exactly to the ask
- `budgetNarrative`: Budget narrative

Each section is stored as `{ text, origin: empty | ai | template | human, updatedAt }` on the application.
Editing a section sets `origin: "human"`.

### Drafting route: `POST /api/hope/draft` (Next.js, server-only key)

Request (Zod-validated, ≤ 40 000 chars):
```json
{ "locale": "en", "mode": "agent", "ask": 50000, "profile": { }, "opportunity": { "id": "opp-bayfront-youth", "funder": "...", "name": "...", "currency": "USD", "amountMin": 25000, "amountMax": 50000 } }
```

Responses:
- `200 { source: "agent" | "template", model?, sections: {6}, reviewerNotes: string[] }`
- `400 { error: "invalid_request" }`
- `503 { error: "missing_openai_key" }`
- `502 { error: "agent_failed" }`

Modes:
- `mode: "agent"` runs one OpenAI Agents SDK agent ("Hope grant writer") with a Zod `outputType`.
  - Settings: `maxTurns: 4`, `maxDuration = 60`, model `OPENAI_MODEL` or the SDK default.
  - Instructions: use **only** facts in the input and write `[TO CONFIRM: ...]` for anything missing. The output is a draft a person reviews; `reviewerNotes` lists what to verify.
- `mode: "template"` returns `hopeTemplate(req)`. This is deterministic, built only from the profile and opportunity. It runs only when the user clicks "Use the built-in template instead". There is no silent fallback.
- On any error, nothing in the application changes, and the UI shows the exact message:
  - missing key: "AI drafting is unavailable: OPENAI_API_KEY is not configured on the server. Nothing was changed."
  - agent failure: "The AI agent failed to produce a draft. Nothing was changed — try again."
  - network failure: "Network error — nothing was changed."

### Rules
- **Never overwrite human edits silently.** If any section has `origin: "human"` with text, the user must
  confirm "This will overwrite sections you edited. Continue?" first.
- **The ask** defaults to the opportunity's `amountMax` and must be > 0. The budget lines must sum to it; code
  checks the template, and the agent is instructed to. **Known gap:** `ask` and `amountMin/Max` are whole currency
  units (numbers), not integer minor units. The backend version must send `ask_minor` (integer) + ISO currency.
- Locale `es` drafts in Latin American Spanish.
- "Mark ready for human submission" moves `drafting → ready`. The page always shows "Hope never submits. A person
  reviews and submits through the funder's portal."
- Export: "Copy draft" (clipboard) and "Download .md" (client-side, all six sections with headings).

## Owns: only edit these paths

```text
apps/web/components/hope/draft/**        (DraftPanel, SectionEditor)
apps/web/lib/hope/draft.ts               (request/result types, hopeTemplate)
apps/web/app/api/hope/draft/**           (route + route.test.ts)
apps/web/lib/hope/draft.test.ts          (new)
```

`lib/hope/types.ts` and `lib/hope/i18n.ts` are shared; add keys, never rename them.

## Acceptance criteria

- [ ] AC1 The draft panel is locked ("Drafting unlocks after program and director approval.") until stage `drafting`.
- [ ] AC2 "Draft with AI" with no `OPENAI_API_KEY` returns 503 and shows the exact message; no section changes.
- [ ] AC3 "Use the built-in template instead" fills all 6 sections with `origin: "template"`; the budget lines sum to the ask.
- [ ] AC4 An AI or template draft over human-edited sections asks for confirmation first; Cancel changes nothing.
- [ ] AC5 Invalid or oversized bodies return 400 `invalid_request`.
- [ ] AC6 Copy and Download .md include all six sections; "Mark ready" moves the stage to `ready`.
- [ ] AC7 The key never reaches the client (`server-only` module, no `NEXT_PUBLIC_` variable).

## Test plan (Vitest, offline, no key)

- `lib/hope/draft.test.ts`: `hopeTemplate` for en / es; the budget sums to the ask; `[TO CONFIRM]` where the profile is empty.
- `app/api/hope/draft/route.test.ts`: 400 / 503 / template 200; mock `@openai/agents` `run` for 200 and the 502 path.
- `components/hope/draft/DraftPanel.test.tsx`: locked state, the overwrite confirm and the error copy.

## Out of scope

Citations per claim, per-question answers from funder pages, DOCX/PDF export, and submission.
