# Hope specs

Spec-driven development for Hope. Every feature and every screen has a spec here, with
everything an agent needs to build it: the behaviour, the acceptance criteria, the tests,
the exact files it may touch, the contracts and endpoints, and its dependencies.

**To build something, tell an agent:** "Implement spec `S07` from `docs/specs/` in carolbonk/hope."
The agent reads this README, `FOLDERS.md`, the spec, and every spec it links. Then it opens
one PR that touches only the paths the spec owns.

| File | What it holds |
|---|---|
| [`FOLDERS.md`](FOLDERS.md) | Target folder layout and who owns each path |
| [`API.md`](API.md) | Every `/v1` endpoint: owning spec, status, and the screens that call it |
| [`SCREENS.md`](SCREENS.md) | Every screen: route, implementing spec, endpoints it calls |
| [`features/`](features) | Feature specs `S00`-`S31` |
| [`screens/`](screens) | Screen specs `SC01`-`SC29` |
| [`templates/`](templates) | Templates for new feature and screen specs |

## Rules for implementing a spec

1. **Check the dependencies first.** Every spec in the spec's `Depends on` list must be `Done`
   in the status table below. If one isn't, stop and report.
2. **Touch only what the spec owns.** The spec's `Owns` list is the full set of paths the PR
   may create or change. If you need anything else (for example a change in `hope_core`, a
   shared UI primitive, or another spec's folder), don't make it. Add it under "Requests"
   in the PR description and stop. This is what keeps parallel PRs free of merge conflicts.
3. **Use the migration numbers reserved for the spec** (listed in the spec and in the table below).
4. **Contracts live in `hope_core.schemas`.** A spec never defines a shared model itself.
   All shared contract changes for a wave go into that wave's contracts spec (`S00` for
   wave 1; `C2`, `C3`, `C4` are added before waves 2-4).
5. **Settings.** New configuration goes in a `BaseSettings` class in the spec's own folder,
   with the `HOPE_` env prefix, not in `hope_core/settings.py`.
6. **Lockfiles.** If `uv.lock` or `pnpm-lock.yaml` conflicts, take `main`'s version and rerun
   `uv lock` / `pnpm install`.
7. **Every acceptance criterion maps to a test** named in the spec's test plan. All CI commands
   in `AGENTS.md` must pass. Tests run offline with mocks (no API keys).
8. **Screens follow the design system.** Use the liquid-glass primitives in
   `apps/web/components/ui` (`glass-panel`, `glass-inset`, `glass-active`), with WCAG AA
   contrast, visible focus rings, status shown by icon or text and not only by colour, and
   `prefers-reduced-motion` support.
9. **Done means:** the PR is merged, CI is green, and the spec's status row is set to `Done` in the same PR.

## Design system: liquid glass

Every screen uses the liquid-glass utilities defined in `apps/web/app/globals.css`:

| Token / class | Use | Look |
|---|---|---|
| `glass-backdrop` | app background | soft, slowly shifting colour gradient (static under reduced motion) |
| `glass-panel` | cards, sections, table rows, calendar cells | 62% white tint (`--glass-fill`), `--glass-blur` (`blur(18px) saturate(170%)`), 1 px top highlight, soft shadow |
| `glass-control` | buttons, toggles, tabs, chips | 78% tint (`--glass-fill-strong`), same blur |
| `glass-chrome` | wizard top/bottom bars, listboxes | 78% tint, same blur |
| `glass-nav` | the `HopeNav` bar, Saved's "Open workspace" action | 35% tint (`--glass-fill-nav`), same blur |
| `glass-inset` | inputs, wells, notices | 40% tint (`--glass-fill-inset`) with an inner shadow |
| `glass-active` | selected nav item, active segment, pressed button | brighter tint, an accent edge, and slight scale-down when pressed |
| `glass-overlay` | modals | strongest tint with a dimmed backdrop |

Rules:
- **Readable first.** Body text sits only on `glass-panel` or stronger, and contrast is checked against the worst-case background (WCAG AA 4.5:1). Never put text directly on `glass-backdrop`.
- **Fallbacks.** `@media (prefers-reduced-transparency: reduce)` and browsers without `backdrop-filter` get solid panels with the same layout. `prefers-reduced-motion` stops the background motion and the highlight shimmer.
- **Status is never shown by colour alone.** Use an icon and text, and give every boundary a 1 px border at 3:1 or better.
- **Blur must compile.** Declare `-webkit-backdrop-filter` before `backdrop-filter`; the CSS build keeps only the last one, and Chrome needs the standard property. Verify with the computed `backdropFilter`, not by eye.
- **Notices are brief.** Notifications, alerts and validation messages disappear within 5 s (`components/ui/AutoDismiss`, `NOTICE_MS`); dismissible bars also have a × button.
- Dark mode is optional for the hackathon (tokens only; not tested).

## Product decisions that apply to every spec

- **The MVP is single-tenant: one organization per deployment.** The `tenant_id` columns and
  row-level security stay in the database (already built), but the server always uses the one
  tenant set in `HOPE_TENANT_ID`. No spec adds tenant IDs to URLs, tenant headers from the
  client, a tenant picker or switcher, or per-tenant settings. The MVP has one agency;
  `GET /v1/me` returns its `agency_id`, and the `agency_id` path segments stay so that
  multi-tenant can be added later without changing URLs.
- Hope is free for nonprofits to use. Paid hosting, LLM and other services behind it are fine.
- LLMs suggest; deterministic code decides eligibility, money, deadlines, state transitions
  and submission. No LLM output contains a money amount.
- Every approval is bound to the exact artifact hash; any change voids it (HTTP 409).
- Nothing is submitted to a funder without HITL-5 approval by the authorized representative.
- Cost-share lines are excluded from every indirect-cost base.

## Hackathon MVP (2 days, single tenant): build these first

Discovery was never the hard part; **applying is.** The demo flow:

1. **Sign in** with email and password (one organization).
2. **Tell Hope about the nonprofit:** mission, values, EIN, NTEE codes, location, budget size, programs, people served.
3. **Discover:** an agent turns the profile into web searches (OpenAI web search), reads each result,
   extracts the grant (funder, amount, deadline, eligibility, link), and scores the fit against the
   profile, with reasons. This runs as a background job with a progress screen.
4. **Curate:** the user reviews grant cards (fit score, reasons, concerns) and saves or passes. Saved grants make the shortlist.
5. **Application brief:** for a shortlisted grant, an agent fetches the grant's pages live and explains
   in plain English how to apply: portal, steps, required documents, questions, deadlines and eligibility.
   Every item cites its source (link + quote).
6. **Proposal review:** the agent drafts answers to the grant's questions from the profile and the grant
   pages, with an inline citation on every claim, so the user can verify each one. The user edits it, then
   exports the final brief to apply with.

**Data rule:** raw pages are never stored; they are fetched live each time. Hope stores only what it
produced: the candidate summary, the brief, the drafts and their citations (URL, title, quote, time retrieved).

Schedule: **H0** runs alone on day 1 morning (about 3-4 h). **H1-H5** then run in parallel, one agent
each, and finish by day 2 noon. Day 2 afternoon is integration and demo rehearsal (orchestrator).

| Spec | Delivers | Screens (route) | Depends on | Migrations | Status |
|---|---|---|---|---|---|
| [H0](features/H0-hackathon-scaffolding.md) | Email/password auth, `/v1/me`, all shared contracts + tables + store, web search/fetch tools, OpenAI provider, job runner, routers/clients/nav split, `make demo` | app shell | - | 0002 | Built |
| [H1](features/H1-sign-in-and-profile.md) | Sign-in screen, profile backend + `lib/hope/sync/profile.ts` (onboarding and profile UI built) | SC01 `/login`, SC11 `/onboarding`, SC09 `/hope/profile` | H0 | 0310-0319 | Built (PR #49) |
| [H2](features/H2-discovery-agent.md) | Discovery agent backend + `lib/hope/sync/opportunities.ts` + run panel (deck UI built) | SC24 `/hope/discover` | H0 | 0700-0709 | Built (PR #50) |
| [H3](features/H3-curated-list.md) | Save/pass backend + `lib/hope/sync/decisions.ts` (Saved/Deadlines UI built; SC26 folded into the card + workspace) | SC25 `/hope/saved`, `/hope/deadlines` | H0 | 0710-0719 | Built (PR #48, #52) |
| [H4](features/H4-eligibility-and-approval.md) | Eligibility checklist, required documents, simulated Program/Director approval | SC27 `/hope/applications/[oppId]` | H0 | none | Built (PR #34) |
| [H5](features/H5-application-draft.md) | 6-section draft (`POST /api/hope/draft`, AI or template), edit, copy/.md, mark ready | SC28 `/hope/applications/[oppId]` | H0 | none | Built (PR #34) |
| [H6](features/H6-application-help.md) | Application help: reads each saved grant's own questions, limits and attachments, drafts answers from the profile, stores the application on the server (`/v1/applications`) | SC27/SC28 `/hope/applications/[oppId]` (SC29 workspace) | H0-H3 | 0720-0729 | Built (PR #53) |
| [H7](features/H7-bids.md) | Opportunity matrix (sample score) and My bids: owners, internal dates, reviews, blockers, final review, recorded receipt (`/v1/bids`, `/v1/members`) | SC30 `/hope/matrix`, SC31 `/hope/bids`, SC32 `/hope/bids/[oppId]` | H0, H3, H6 | 0730-0739 | Built (PR #78, #80) |

**Frontend (PR #34):** `apps/web` follows the Hope frontend zip: `app/`, `components/`, `lib/` at the package root, routes under `/hope/*` (`/hope/discover`, `/hope/saved`, `/hope/deadlines`, `/hope/profile`, `/hope/applications/[oppId]`), plus SC11 `/onboarding` and the liquid-glass CSS. H4/H5 follow the zip's application flow; their state lives in the browser (`hope:state:v1`) until the backend track lands.

MVP rules on top of the rules above:

- **Single tenant.** One organization; all users belong to it. There's no tenant anywhere in the API or UI.
- **No submission.** Hope produces the brief and the proposal; the user applies on the funder's site.
- **OpenAI only** (one key, `HOPE_OPENAI_API_KEY`) for the LLM and for web search. Tests and CI use
  `MockProvider` and the recorded web fixtures from H0; there's no network in CI.
- **Every factual claim shown to the user has a citation**, either a web `Citation` or a profile
  reference. A claim without one is shown as "Unverified" and is never silently dropped.
- **Amounts and dates come from quotes.** The LLM returns the quoted text, and code parses it into
  `Money`/`date`. An amount the code can't parse is shown as the quoted text.
- **All shared tables, contracts and store functions come from H0.** H1-H5 never create a table that
  another H spec reads.
- **Seed data is per spec:** each spec owns `demo.py:seed()` in its own package; H0's runner calls them in the order H1, H2, H3, H4, H5.
- The M0-M7 specs below are superseded for the hackathon; keep them for later.

## Later (after the hackathon)

The S-specs below are the full roadmap. They stay Draft and are not built during the
hackathon. WIP drafts are on the `specs/<area>` branches.


Status values: `Draft` (the spec is being written), `Ready` (reviewed; can start once its
dependencies are Done), `In progress` (there is a PR), `Done`.

| Spec | Title | Wave | Depends on | Migrations | Screens | Status |
|---|---|---|---|---|---|---|
| [S00](features/S00-shared-contracts-and-scaffolding.md) | Shared contracts and scaffolding | 0 | - | `0002` | - | Ready |
| S01 | Sign-in, users, roles and `/v1/me` (single tenant) | 1 | S00 | `0110` | SC01, SC17 | Draft |
| S02 | Approval inbox API and screens | 1 | S00 | - | SC05, SC06 | Draft |
| S03 | Opportunity search and detail | 1 | S00 | - | SC04 | Draft |
| S04 | Pursue, workflow list and history | 1 | S00 | `0610` | SC07, SC08 | Draft |
| S05 | Matrix explainability and disposition | 1 | S00 | `0410` | SC03 | Draft |
| S06 | Budget API and HITL-2 budget review | 1 | S00 | `0510` | SC13 | Draft |
| S07 | Wire real agents into the lifecycle workflow | 1 | S00 | - | - | Draft |
| S09 | Profile hardening and onboarding via HITL-0 | 1 | S00 | `0310` | SC09, SC10, SC11 | Draft |
| S10 | Scheduled discovery and parse-review queue | 1 | S00 | `0210` | SC12 | Draft |
| S11 | OCR engine for scanned documents | 1 | S00 | - | - | Draft |
| S12 | Notification delivery and notification centre | 1 | S00 | `0700` | SC16 | Draft |
| S13 | Audit trail API and screen | 1 | S00 | `0120` | SC15 | Draft |
| S16 | Real LLM and embedding providers, usage metering | 1 | S00 | `0010` | - | Draft |
| S28 | Cloud environments, IaC and deploy pipeline | 1 | S00 | - | - | Draft |
| S29 | Observability and LLM cost tracking | 1 | S00 | - | - | Draft |
| S08 | Persistent matching state and rule approval | 2 | S05 | `0420` | SC14 | Draft |
| S14 | USAspending past-awards signal | 2 | S05, S10 | `0220`, `0430` | - | Draft |
| S15 | IRS exempt-org and 990 import | 2 | S09 | `0320` | - | Draft |
| S17 | Narrative drafting agent | 2 | S16, S06 | `0800` | - | Draft |
| S18 | Verifier: claims, citations and numbers | 2 | S16, S06 | `0900` | - | Draft |
| S19 | Compliance packs and HITL-3 attestation | 2 | S06 | `1000` | SC20 | Draft |
| S24 | Integrations framework and CRM connector | 2 | S01 | `1300` | SC18 | Draft |
| S27 | Foundation and state portal connectors | 2 | S10, S11 | `0230` | - | Draft |
| S30 | Security hardening: secrets, AV, backups, WAF | 2 | S28 | - | - | Draft |
| S31 | Dashboard | 2 | S02, S04, S05 | - | SC02 | Draft |
| S20 | Proposal workspace and HITL-4 executive approval | 3 | S17, S18, S19 | - | SC19, SC21 | Draft |
| S21 | Application package assembly | 3 | S18, S19 | `1100` | SC22 | Draft |
| S23 | Post-award tracking and outcome loop | 3 | S04 | `1400` | SC23 | Draft |
| S25 | ERP / accounting connector for cost basis | 3 | S24, S06 | `1310` | - | Draft |
| S26 | Calendar sync for deadlines | 3 | S24, S12 | `0710` | - | Draft |
| S22 | Grants.gov S2S submission and status | 4 | S21 | `1200` | - | Draft |

Open decisions that block specific specs are listed in each spec under "Decisions needed".
