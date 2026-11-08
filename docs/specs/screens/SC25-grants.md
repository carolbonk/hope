# SC25: Saved and Deadlines (the shortlist)

| | |
|---|---|
| Route | `/hope/saved` and `/hope/deadlines` (no query parameters) |
| Files | `apps/web/app/hope/saved/page.tsx`, `apps/web/app/hope/deadlines/page.tsx` (PR #34), `apps/web/components/hope/deadlines/**` (Table/Calendar views, PRs #39 and #41) |
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
backend (H3 spec, Behaviour 1). After sign-in, `HopeSync` loads the server's saved and passed grants back
into `useHope()` (H3, Behaviour 1b), so a grant saved in another browser shows here too. These pages never
call the API.

## 2. Information hierarchy

Saved card:
1. **Opportunity name** (display font), with the funder above it in small caps.
2. **Maximum amount and due date** on one line.
3. **Stage bar** (5 stages), showing how far along the application is.
4. **"Open workspace ↗"**, the next action, in 35% liquid glass (`glass-nav`, PR #43). The whole card is the link.

Deadlines: a **Table / Calendar** tab switch (Table by default). Table row: **name** and funder, "stage · next step",
the date, then a **days pill** whose colour shows urgency. Calendar: a month grid with one chip per deadline.

## 3. Wireframe

`/hope/saved`, desktop (two columns from `sm`):

```text
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ hope✳        Discover   (Saved (2))   Deadlines                 [EN | ES] [Account ▾]     │  <- HopeNav (SC00)
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
│ KEEP MOMENTUM                                                      [ Table | Calendar ]  │  <- DeadlineViewTabs
│ Upcoming deadlines                                                                        │
│   OPPORTUNITY              STAGE                    DEADLINE          STATUS              │
│ ┌ glass-panel, gold left edge ──────────────────────────────────────────────────────────┐ │
│ │ Back-to-School Event…    Saved · Start the        Nov 17, 2026      [Due soon · 9d]   │ │
│ │ Tidal Bank Giving        eligibility review.                                          │ │
│ └───────────────────────────────────────────────────────────────────────────────────────┘ │
│ ┌ glass-panel ──────────────────────────────────────────────────────────────────────────┐ │
│ │ Youth Mentoring Grants   Drafting · Complete…     Nov 29, 2026               [21d]    │ │
│ └───────────────────────────────────────────────────────────────────────────────────────┘ │

Calendar tab: ‹ November 2026 › over a 7-column glass grid (Monday first in ES); each deadline is a glass chip
on its day, linking to its application. Opens on the month of the next deadline.
```

Mobile (< 640 px): Saved is one column. Table rows stack their fields; Calendar chips become dots with that month's
deadlines listed under the grid.

## 4. Content inventory

All values come from `useHope().state` and `useOpportunities()`, joined by `application.opportunityId`.

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Saved list | `state.applications` | one card per application | Drop an application whose opportunity isn't in `useOpportunities()`. **Fix 1:** drop one whose `decisions[oppId]?.decision === "passed"`. Sorted by `opportunity.deadline` ascending (ISO string compare), unknown dates last |
| Funder | `o.funder` | "TIDAL BANK GIVING (DEMO)" | Small caps (`uppercase tracking-[0.16em]`) |
| Name | `o.name` | "Back-to-School Event Sponsorship" | Display font |
| Demo badge | `h.demo` | "Demo data" | **Fix 2:** only when `o.source.kind === "demo"` |
| Amount | `o.amountMax`, `o.currency` | "$10,000" | `money()` in whole units (`components/hope/ui.tsx`). The backend sends integer `amount_minor`; H2's adapter has already divided by 100. `null` → "Amount not found" (`useGrantFacts`) |
| Due | `o.deadline`, `daysUntil(o.deadline, today)` | "Due 2026-11-16 · 9 days" | `h.discover.due`; `null` → "Deadline not found", or "Rolling, no fixed date" when the page said so |
| Stage | `a.stage` | `StageBar` with `h.stage` labels | `saved → eligibility → approval → drafting → ready` |
| Deadlines list | `state.applications` | one row each | Drop stage `ready`. Drop a missing opportunity. Sorted by `days` ascending. Fix 1 applies here too. A grant with no date (`deadline: null`) is left off the table, calendar and `DeadlineReminder` and listed after them in a "No date yet" panel (name link, funder, "Deadline not found" or "Rolling, no fixed date"; copy in `app/hope/deadlines/copy.ts`) |
| Row line 2 | `h.stage[a.stage]`, `h.app.next[a.stage]` | "Saved · Start the eligibility review." | |
| Days pill | `days` | `days < 0`: "Past due" (red); `days <= 14`: "Due soon · 9d" (gold); else "21d" (cream) | The border uses the same colours. These are the UI's thresholds, not the API's `urgency` |

## 5. Components

- `PageIntro`, `Panel`, `StageBar`, `ClientOnly`, `btnPrimary`, `focusRing` and `money`/`daysUntil`
  from `components/hope/ui.tsx` (H0). Liquid-glass classes `glass-panel` / `glass-nav`.
- `components/hope/deadlines/`: `DeadlineViewTabs` (tablist, sliding highlight), `DeadlineTable` (fixed 11rem Status
  column so columns line up), `DeadlineCalendar`, `DeadlineBadge`, `items.ts`. Views fade in with `animate-view-in`.

## 6. Interactions

1. **Open workspace:** a card (Saved), a table row or a calendar chip (Deadlines) links to `/hope/applications/{o.id}`.
5. **Deadlines view:** the Table / Calendar tabs switch views (click, or ←/→/Home/End); ‹ › page months in Calendar.
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
| Mount | `useHope()` (`lib/hope/store.ts`) | `applications`, `decisions` | localStorage `hope:state:v1`, no polling; updated once per page load from the server by H3's `HopeSync` load |
| Mount | `useOpportunities()` (`lib/hope/opportunities.ts`) | `id, funder, name, amountMax, currency, deadline, source.kind` | H2's adapter |

Neither page calls `/v1`. For reference, H3's decisions adapter (not these pages) sends
`POST /v1/grants/{grant_id}/save`, `POST /v1/grants/{grant_id}/pass` and `POST /v1/grants/{grant_id}/reset`
when Discover saves, passes or undoes.

## 9. Responsive behaviour

- ≥ 640 px: Saved is a 2-column grid (`sm:grid-cols-2`).
- < 640 px: one column. Deadlines Table rows stack; the Calendar shows dots plus a month list.
- Checked at the Tailwind breakpoints 375 / 640 / 768 / 1024 / 1280 / 1536 px with no horizontal overflow.

## 10. Accessibility

- One `h1` (PageIntro). Saved also has an `sr-only` `h2` "Saved opportunities".
- Each card or row is a single link with a visible focus ring (`focusRing`).
- The stage bar is an `ol` labelled with the current stage, and the current step has `aria-current="step"`.
- The days pill always has text. Colour is never alone.
- The view switch is a `role="tablist"` with roving `tabIndex`; each view is a `role="tabpanel"`.

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
- [ ] AC8 Deadlines switches between Table and Calendar by click and keyboard, every row and chip links to its application, and the Calendar pages months.

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
| AC8 | `components/hope/deadlines/DeadlineViews.test.tsx` (tab switching by click and keyboard, links, month paging) |

## 15. Open questions

- **Should Saved and Deadlines show grants saved in another browser?** Decided: yes. H3 loads the server's
  saved and passed grants after sign-in (H3, Behaviour 1b); a decision this browser hasn't sent yet wins.
