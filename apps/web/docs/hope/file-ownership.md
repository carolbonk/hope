# Hope web: file ownership (hackathon)

The specs in `docs/specs/` are the source of truth. This file is the short version for `apps/web`, so no two
agents edit the same file.

| Spec | Owns in `apps/web` |
| --- | --- |
| H0 | `app/layout.tsx`, `app/page.tsx`, `app/hope/layout.tsx` (session guard), `components/hope/ui.tsx`, `api/http.ts`, `api/session/**`, `lib/hope/sync/index.ts`, `package.json` |
| H1 | `app/login/**`, `app/onboarding/**`, `features/onboarding/**`, `api/profile/**`, `api/onboarding/**`, `lib/hope/fromOnboarding.ts`, `lib/hope/sync/profile.ts`, `app/hope/profile/**` |
| H2 | `app/hope/discover/**`, `components/hope/discovery/**`, `lib/hope/opportunities.ts`, `lib/hope/demo.ts`, `lib/hope/sync/opportunities.ts` |
| H3 | `app/hope/saved/**`, `app/hope/deadlines/**`, `lib/hope/sync/decisions.ts` |
| H4 | `app/hope/applications/[oppId]/page.tsx`, `lib/hope/store.ts` (eligibility, stage gates), `lib/hope/dossier.ts` |
| H5 | `components/hope/draft/**`, `lib/hope/draft.ts`, `app/api/hope/draft/**` |
| Shared: add keys, never rename | `lib/hope/types.ts`, `lib/hope/i18n.ts`, `docs/hope/data-contract.md` |
| Don't change without asking | `app/globals.css` (liquid glass), `components/ui/**` |

The seam: pages only call `useHope()` / `useOpportunities()` and `/api/hope/draft`. A backend replaces the
inside through `lib/hope/sync/*`, keeps the hook signatures, and needs no page edits.
