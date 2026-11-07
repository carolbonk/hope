# SC28: Application workspace: draft

| | |
|---|---|
| Route | `/hope/applications/[oppId]` (stages `drafting`, `ready`; the "Application draft" panel) |
| Files | `apps/web/components/hope/draft/DraftPanel.tsx` (`DraftPanel`, `SectionEditor`), `apps/web/app/api/hope/draft/route.ts`, `apps/web/lib/hope/draft.ts` |
| Built by | H5 (ported in PR #34) |
| Primary users | The nonprofit's grant writer or executive director |
| Can act | Anyone in this browser |
| Status | Built (browser + Next.js route) |

## 1. Purpose and user goals

The panel turns an approved opportunity into a 6-section draft the team can edit and take to the funder's
portal. It answers:
1. What has been drafted, and by whom? (each section's origin: Empty / AI draft / Template / Human edit)
2. What must we still verify? (`[TO CONFIRM: …]` markers and the reviewer notes)
3. Is it ready for a person to submit?

**Primary action:** "Draft with AI". **Secondary actions:**
- "Use the built-in template instead"
- edit any section
- "Copy draft" and "Download .md"
- "Mark ready for human submission"

## 2. Layout

```text
┌ Application draft ───────────────────────────────────────────────┐
│ Ask [ 50,000 ] USD     [Draft with AI]  Use the built-in template │
│ Reviewer notes: • Confirm program outcomes …                      │
│ Program description             · AI draft                        │
│ [textarea ...............................................]       │
│ Alignment with mission & outcomes · Human edit                    │
│ … (6 sections)                                                     │
│ [Copy draft] [Download .md]          [Mark ready for human submission] │
│ Hope never submits. A person reviews and submits through the funder's portal. │
└───────────────────────────────────────────────────────────────────┘
```

## 3. Data and endpoints

| Trigger | Call | Notes |
|---|---|---|
| Draft with AI | `POST /api/hope/draft` `{ locale, mode: "agent", ask, profile, opportunity }` | 200 fills sections with `origin: "ai"`; 503/502/network errors change nothing |
| Template | `POST /api/hope/draft` `{ …, mode: "template" }` | Deterministic `hopeTemplate`; `origin: "template"` |
| Edit | none (browser state) | `origin: "human"`, `updatedAt` |

The route is a Next.js route handler, not part of the `/v1` mock contract. Its template mode is the offline stand-in.

## 4. States and exact copy

- **Locked:** "Drafting unlocks after program and director approval."
- **Busy:** "Drafting…" on the button. Both actions are disabled.
- **Confirm overwrite:** "This will overwrite sections you edited. Continue?"
- **Errors** (exact copy from H5): missing key, agent failed, network.
- **Copied:** "Copied".

## 5. Accessibility and responsive

- Textareas are labelled with the section titles, and the origin is given as text.
- Errors use `role="alert"`.
- Buttons wrap below `sm`.

## 6. Acceptance criteria

The same as H5 AC1-AC7.
