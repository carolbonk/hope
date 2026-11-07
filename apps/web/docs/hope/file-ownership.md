# Hope — proposed file ownership and merge order

Goal: the experience track and the backend track can work in parallel without two people (or agents) editing the same file.

| Track | Owners | Files |
| --- | --- | --- |
| Experience and visual direction | Carito (+ daughter) | `app/hope/**/page.tsx`, `app/hope/layout.tsx`, `components/hope/**`, `lib/hope/i18n.ts` (copy), Hope tokens in `app/globals.css` |
| Backend and data | Jimmy, Carol | `lib/hope/types.ts`, `lib/hope/store.ts`, `lib/hope/dossier.ts` (requirement rules), `lib/hope/opportunities.ts`, `lib/hope/demo.ts` (later replaced by a real catalog), `lib/hope/draft.ts`, `app/api/hope/**`, future `app/api/orgs/**`, `app/api/applications/**`, DB schema |
| Shared, change by PR with both tracks reviewing | all | `lib/hope/types.ts` (the contract), `docs/hope/data-contract.md` |
| Existing Nonprofit MRI (do not edit from Hope work) | — | `app/(intake…report)`, `lib/*.ts` outside `lib/hope`, `app/api/draft` |

Seam: pages only call `useHope()` / `useOpportunities()` and the `/api/hope/draft` route. When the backend replaces localStorage, it changes the inside of `lib/hope/store.ts` and keeps the hook's signatures, so no page edits are needed.

## Merge order

1. [ark305/nonprofit-mri#1](https://github.com/ark305/nonprofit-mri/pull/1): the Nonprofit MRI base (Next.js app, i18n, the `/api/draft` pattern).
2. [ark305/nonprofit-mri#2](https://github.com/ark305/nonprofit-mri/pull/2) (`devin/hope-discovery`): Hope discovery deck, application workspace, shared record, five-step profile.
3. `devin/hope-expediente`: document dossier, conditional requirements, review with pending items / Resolve, local-only review request. Stacked on #2.

Each PR is stacked on the previous one; merging in order lets GitHub retarget the next PR to `main`.

## Port to carolbonk/hope

Devin's GitHub app could not reach `carolbonk/hope` (clone "repository not found", API 404), so its `main`, open PRs and `docs/architecture/blueprint.md` have not been inspected. When access exists:

1. Inspect `main`, every open PR and the blueprint; note which files another agent owns.
2. Port only what is missing, in one branch, keeping attribution (`git cherry-pick -x` of the Hope commits, or `git format-patch` from this repo + `git am`). Hope-only paths: `app/hope/**`, `components/hope/**`, `lib/hope/**`, `app/api/hope/**`, `docs/hope/**`, Hope tokens in `app/globals.css`.
3. Do not bring Nonprofit MRI pages, `.env*` files or anything from Bored Billionaires.
4. Re-run `npx tsc --noEmit`, `npm run lint`, `npm run build` and the browser journey there; open one PR, no merge or deploy.
