# SC25: Saved and Deadlines (the shortlist)

| | |
|---|---|
| Route | `/hope/saved` and `/hope/deadlines` (no query parameters) |
| Files | `apps/web/app/hope/saved/page.tsx`, `apps/web/app/hope/deadlines/page.tsx` (built by PR #34) |
| Built by | H3 (keeps them working, two small fixes, tests). Decisions are made on SC24 Discover |
| Primary users | Executive director or development lead of a small nonprofit, weekly |
| Can act | Anyone in this browser (no roles). The only action here is opening the workspace |
| Status | Built; fixes and tests to do |

## 1. Purpose and user goals

The user saved some opportunities on Discover (SC24). Each save created an application record. These two
pages answer:
1. **Saved:** what are we pursuing, how far along is each one, and where do I continue?
2. **Deadlines:** what is due next, and what's the next step for it?

**Primary action:** open an application workspace (`/hope/applications/{oppId}`, SC27/SC28).
**Secondary action:** go back to Discover when the list is empty.

Save, Pass and Undo happen only on the Discover deck. H3's `lib/hope/sync/decisions.ts` mirrors them to the
backend (H3 spec, Behaviour 1). These pages never call the API.

## 2. Information hierarchy

Saved card:
1. **Opportunity name** (display font), with the funder above it in small caps.
2. **Maximum amount and due date** on one line.
3. **Stage bar** (5 stages), showing how far along the application is.
4. **"Open workspace ↗"**. The whole card is the link.

Deadlines row: the **name**, then "stage · next step", then a **days pill** whose colour shows urgency.

## 3. Wireframe

`/hope/saved`, desktop (two columns from `sm`):

```text
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ [Hope]   Our profile   Discover   (Saved (2))   Deadlines                     [EN | ES]  │  <- HopeNav (H0)
│ ● Due soon: Back-to-School Event Sponsorship (9d) · General Operating Support (12d)       │  <- DeadlineReminder (H0)
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ FROM POSSIBILITY TO PROGRESS                                                              │  <- PageIntro eyebrow
│ Worth a closer look.                                                                      │  <- h1
│ Your shortlist, your next steps. Everything stays connected to one record.                │
│ ┌ glass-panel ─────────────────────────────┐ ┌ glass-panel ─────────────────────────────┐ │
│ │ TIDAL BANK GIVING (DEMO)     [Demo data] │ │ SUNRISE NEIGHBORS FOUNDATION (DEMO)  [Demo│ │
│ │ Back-to-School Event Sponsorship         │ │ General Operating Support                │ │
│ │ $10,000 · Due 2026-11-16 · 9 days        │ │ $30,000 · Due 2026-11-19 · 12 days       │ │
│ │ ▬▬▬▬ ──── ──── ──── ────                 │ │ ▬▬▬▬ ▬▬▬▬ ▬▬▬▬ ──── ────                 │ │  <- StageBar
│ │ Saved  Reviewing  Internal  Drafting Ready│ │ Saved  Reviewing  Internal  Drafting Read│ │
│ │ [ Open workspace ↗ ]                     │ │ [ Open workspace ↗ ]                     │ │
│ └──────────────────────────────────────────┘ └──────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

`/hope/deadlines`:

```text
│ KEEP MOMENTUM                                                                             │
│ Upcoming deadlines                                                                        │
│ ┌ glass-control, border gold ───────────────────────────────────────────────────────────┐ │
│ │ Back-to-School Event Sponsorship                                    [Due soon · 9d]   │ │
│ │ Saved · Start the eligibility review.                                                 │ │
│ └───────────────────────────────────────────────────────────────────────────────────────┘ │
│ ┌ glass-control, border line ───────────────────────────────────────────────────────────┐ │
│ │ Youth Mentoring Grants                                                     [21d]      │ │
│ │ Drafting · Complete and review each section.                                          │ │
│ └───────────────────────────────────────────────────────────────────────────────────────┘ │
```

Mobile (< 640 px): Saved is one column. Deadlines rows keep the pill on the right.

## 4. Content inventory

All values come from `useHope().state` and `useOpportunities()`, joined by `application.opportunityId`.

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Saved list | `state.applications` | one card per application | Drop an application whose opportunity isn't in `useOpportunities()`. **Fix 1:** drop one whose `decisions[oppId]?.decision === "passed"`. Sorted by `opportunity.deadline` ascending (ISO string compare) |
| Funder | `o.funder` | "TIDAL BANK GIVING (DEMO)" | Small caps (`uppercase tracking-[0.16em]`) |
| Name | `o.name` | "Back-to-School Event Sponsorship" | Display font |
| Demo badge | `h.demo` | "Demo data" | **Fix 2:** only when `o.source.kind === "demo"` |
| Amount | `o.amountMax`, `o.currency` | "$10,000" | `money()` in whole units (`components/hope/ui.tsx`). The backend sends integer `amount_minor`; H2's adapter has already divided by 100 |
| Due | `o.deadline`, `daysUntil(o.deadline, today)` | "Due 2026-11-16 · 9 days" | `h.discover.due` |
| Stage | `a.stage` | `StageBar` with `h.stage` labels | `saved → eligibility → approval → drafting → ready` |
| Deadlines list | `state.applications` | one row each | Drop stage `ready`. Drop a missing opportunity. Sorted by `days` ascending. Fix 1 applies here too |
| Row line 2 | `h.stage[a.stage]`, `h.app.next[a.stage]` | "Saved · Start the eligibility review." | |
| Days pill | `days` | `days < 0`: "Past due" (red); `days <= 14`: "Due soon · 9d" (gold); else "21d" (cream) | The border uses the same colours. These are the UI's thresholds, not the API's `urgency` |

## 5. Components

- `PageIntro`, `Panel`, `StageBar`, `ClientOnly`, `btnPrimary`, `focusRing` and `money`/`daysUntil`
  from `components/hope/ui.tsx` (H0). Liquid-glass classes `glass-panel` / `glass-control`.
- No new components. Don't restyle; `app/globals.css` and `components/ui/**` stay as they are.

## 6. Interactions

1. **Open workspace:** a card (Saved) or row (Deadlines) links to `/hope/applications/{o.id}`.
2. **Empty state CTA:** links to `/hope/discover`.
3. **Live updates:** the lists re-render when `hope:state:v1` changes in this tab or another (`useStoredJson`).
4. **Language:** the EN/ES toggle in the nav switches every string (`useHopeT()`).

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading (server render, before `today` is known) | `ClientOnly`: "Loading your workspace…" |
| Saved, empty | Panel "Nothing saved yet. Save cards in Discover to start an application." + "Discover" button |
| Deadlines, empty | Panel "No saved opportunities yet, so no deadlines." + "Discover" button |
| Overdue row | Pill "Past due", red border |
| Due within 14 days | Pill "Due soon · {n}d", gold border |
| Opportunity missing from the catalog | The application is not listed (no error) |
| ES | Same states with the `es` dictionary ("Aún no has guardado nada…", "Vencido", "Vence pronto") |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount | `useHope()` (`lib/hope/store.ts`) | `applications`, `decisions` | localStorage `hope:state:v1`, no polling |
| Mount | `useOpportunities()` (`lib/hope/opportunities.ts`) | `id, funder, name, amountMax, currency, deadline, source.kind` | H2's adapter |

Neither page calls `/v1`. For reference, H3's decisions adapter (not these pages) sends
`POST /v1/grants/{grant_id}/save`, `POST /v1/grants/{grant_id}/pass` and `POST /v1/grants/{grant_id}/reset`
when Discover saves, passes or undoes.

## 9. Responsive behaviour

- ≥ 640 px: Saved is a 2-column grid (`sm:grid-cols-2`).
- < 640 px: one column. Deadlines is always one column.

## 10. Accessibility

- One `h1` (PageIntro). Saved also has an `sr-only` `h2` "Saved opportunities".
- Each card or row is a single link with a visible focus ring (`focusRing`).
- The stage bar is an `ol` labelled with the current stage, and the current step has `aria-current="step"`.
- The days pill always has text. Colour is never alone.

## 11. Fixture data

Tests use `demoOpportunities(today)` with `vi.setSystemTime(new Date("2026-11-07T12:00:00"))`
(Tidal 9 days, Sunrise 12, Bayfront 21, Lumen 28, Coral 35, Harbor 48, County 60) and seed `hope:state:v1`:
- applications for Tidal (`saved`), Sunrise (`approval`), Bayfront (`drafting`) and Coral (`ready`)
- `decisions`: those four `saved`, plus Lumen with an application and decision `passed`
- one application whose `opportunityId` (`opp-gone`) isn't in the catalog

For the overdue case and Fix 2, mock `@/lib/hope/opportunities` with one `source.kind: "verified"` opportunity
whose deadline is 3 days ago.

## 12. Analytics and success measures

No analytics in the hackathon. Success: every saved opportunity shows on Saved with its stage, and every
open one on Deadlines in due order.

## 13. Acceptance criteria

- [ ] AC1 Saved shows one card per application, sorted by deadline, with funder, name, max amount, due line, stage bar and a link to `/hope/applications/{oppId}`.
- [ ] AC2 Saved leaves out applications with decision `passed` (Fix 1) and applications whose opportunity is missing.
- [ ] AC3 The "Demo data" badge shows only for `source.kind === "demo"` (Fix 2).
- [ ] AC4 Deadlines leaves out stage `ready` and passed ones, sorts by days left, and shows "Past due" / "Due soon · Nd" / "Nd" with the right colours.
- [ ] AC5 Both empty states render the exact copy and link to `/hope/discover`.
- [ ] AC6 ES renders the Spanish copy.
- [ ] AC7 Neither page imports `api/` or calls `fetch`.

## 14. Test plan

| AC | Test |
|---|---|
| AC1 | `app/hope/saved/page.test.tsx::lists applications by deadline with stage and link` |
| AC2 | `saved/page.test.tsx::hides passed and missing opportunities` |
| AC3 | `saved/page.test.tsx::demo badge only for demo data` |
| AC4 | `app/hope/deadlines/page.test.tsx::excludes ready and passed, sorts, labels urgency` |
| AC5 | `saved/page.test.tsx::empty state`, `deadlines/page.test.tsx::empty state` |
| AC6 | `deadlines/page.test.tsx::spanish copy` |
| AC7 | `saved/page.test.tsx::makes no network calls` (`fetch` spy never called) |

## 15. Open questions

- **Should Saved and Deadlines show grants saved in another browser?** Recommended default: no for the
  hackathon. The browser is the source; pulling server status is out of scope (H3).
