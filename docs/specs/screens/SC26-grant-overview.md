# SC26: Grant overview

| | |
|---|---|
| Route | `/grants/[grantId]` (query: `from=cards\|list` to return to SC25 at the same place) |
| Feature folder | `apps/web/features/grants/` |
| Built by | H3 |
| Primary users | Executive director or development lead, deciding whether to invest in applying |
| Can act | Any signed-in user: Save, Pass, Reset, Build application brief, Draft proposal |
| Status | Draft |

> **Aligned after PR #34/#35. This box is authoritative: where anything below disagrees (routes, `apps/web/src/...` paths, building a screen from scratch), this box wins.**
> - The UI already exists: the Hope frontend under `/hope/*` (zip port, liquid glass) plus SC11 `/onboarding`. Don't rebuild or restyle screens; keep `app/globals.css` and `features/onboarding/**` as they are.
> - `apps/web` has no `src/`: `app/`, `components/`, `lib/`, `features/`, `api/` sit at the package root, and `@/*` maps to `./*`.
> - Pages only call `useHope()` (`lib/hope/store.ts`) and `useOpportunities()` (`lib/hope/opportunities.ts`). A backend plugs in through its own adapter in `lib/hope/sync/<name>.ts`. Keep the hook signatures and don't edit pages for wiring.
> - The `/v1` contract in `contracts/` still holds for the backend. On the wire, money is `amount_minor` (integer) + ISO currency; the adapters convert to the UI's whole units.
> - **No separate page.** The content lives on the Discover card and the workspace header (`/hope/applications/[oppId]`). Don't build `/grants/[grantId]`.

## 1. Purpose and user goals

Users arrive from a card or row in SC25 ("Details"), or from a link in a brief or proposal.
This page is "everything Hope knows about this grant, with proof", and the jumping-off point
for applying.

Within 5 seconds it must answer:
1. What is this grant, who funds it, how much is it, and when is it due?
2. Why does Hope think we fit, and what are the risks, with sources?
3. What's my next step: do we have a brief or a draft yet?

**Primary action:** "Build application brief" (H4 route), or "Open brief" once it exists.
**Secondary actions:** "Draft proposal" (H5 route), "View original", Save / Pass / Reset, back to the list.

## 2. Information hierarchy

1. **Title, funder, fit score and status.** These tell the user what the grant is and how good a fit it is.
2. **Key facts strip:** amount, deadline urgency and eligibility, each with its citation.
3. **The next step panel:** brief and proposal status with their CTAs. It's always visible on the right on desktop, and sticky at the bottom on mobile, because moving forward is the point of this page.
4. **Why it fits / Watch out:** every reason and concern, not just the top 3.
5. **Sources:** every citation, listed, so the user can audit them.

There's no raw page text. Pages are never stored, and "View original" opens the live page.

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ ← Back to grants                                                                           │
│ Youth Development Grants 2027                               ● 86 Strong fit   [★ Saved]   │  <- title row
│ The Cleveland Foundation · clevelandfoundation.org · Found Nov 7    [View original ↗]     │
├──────────────────────────────────────────────────────────┬────────────────────────────────┤
│ ┌ Key facts (Card raised) ────────────────────────────┐  │ ┌ Next steps (Card raised) ────┐│
│ │ Amount     Up to $50,000 per year            [c5]   │  │ │ 1 Application brief          ││
│ │ Deadline   ⏱ 116 days · Mar 3, 2027          [c6]   │  │ │   ✓ Ready · Nov 7, 3:10 PM   ││
│ │ Eligibility 501(c)(3)s serving Cuyahoga County [c7] │  │ │   [ Open brief → ]           ││
│ └─────────────────────────────────────────────────────┘  │ │ 2 Proposal draft             ││
│ Summary                                                   │ │   ○ Not started              ││
│ Two-year grants for out-of-school programs… [c1]          │ │   [ Draft proposal → ]       ││
│ Why it fits                                               │ │ ─────────────────────────── ││
│  ✓ Funds youth mentoring, matches Mentor Futures [c1][c4] │ │ [✕ Pass]  [↶ Move to New]    ││
│  ✓ Serves Cuyahoga County, in your service area [c2]      │ └──────────────────────────────┘│
│  ✓ Award size fits your budget  (Unverified)              │                                │
│ Watch out                                                 │                                │
│  ▲ Requires a 2025 audited financial statement [c3]       │                                │
│ Sources (7)                                               │                                │
│  c1 Youth Development | The Cleveland Foundation ↗  "supports mentoring…"                  │
│  c4 Profile · Programs › Mentor Futures             "Mentor Futures pairs 150 youth…"      │
│  …                                                                                         │
└──────────────────────────────────────────────────────────┴────────────────────────────────┘
```

Mobile (<= 640 px): a single column (title row, key facts, summary, reasons, concerns,
sources). The Next steps panel becomes a sticky bottom bar with the primary CTA, plus a
"Steps" button that opens a bottom `Drawer` showing both statuses and Save/Pass.

## 4. Content inventory

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Title | `GET /v1/grants/{id}` -> `title` | H1, "Youth Development Grants 2027" | Wraps; no truncation |
| Funder line | `funder`, `domain`, `discovered_at` | "The Cleveland Foundation · clevelandfoundation.org · Found Nov 7" | Date in local time |
| Fit | `fit_score`, `fit_band` | "● 86 Strong fit" | As in SC25 |
| Status | `status` | Badge "★ Saved" / "New" / "✕ Passed" | Icon + text |
| View original | `view_original_url` | "View original ↗" | `target="_blank" rel="noopener noreferrer"`. The domain is shown in the tooltip |
| Amount | `amount_max` / `amount_text`, `amount_citation_id` | "Up to $50,000 per year [c5]" | Rules as in SC25. If there's no citation, an "Unverified" chip |
| Deadline | `deadline`, `days_left`, `urgency`, `deadline_text`, `deadline_citation_id` | "⏱ 116 days · Mar 3, 2027 [c6]" | Urgency styling as in SC25. `past`: red "Deadline passed", and both CTAs are disabled with the hint "This deadline has passed" |
| Eligibility | `eligibility_summary` | 1-2 sentences | "Eligibility not stated. Check the original." when null. Citations from inline `[cN]` markers |
| Summary | `summary`, `summary_citation_ids` | Paragraph with chips | `[cN]` markers rendered as `CitationChip` |
| Reasons | `reasons[]` (all) | "✓ … [c1][c4]" | Order as returned. Unverified items show the chip |
| Concerns | `concerns[]` (all) | "▲ … [c3]" | "No concerns found." when empty |
| Sources | `citations[]` | Web: "c1 {title} ↗ "{quote}"" with the domain. Profile: "c4 Profile · {profile_path in words} "{quote}"" | Ordered by `citation_id` number. The quote is cut to 160 chars, and the popover has the full quote. `retrieved_at` shows as "Retrieved Nov 7" |
| Application stage | `useHope().state.applications[applicationId(ORG_ID, id)].stage` (H4/H5, `lib/hope/store.ts`) | `saved` / `eligibility` / `approval` / `drafting` / `ready`, shown with the `StageBar` labels | Browser state; updates live across tabs |

## 5. Components

- Page header: a text "Back" link, an H1, `Badge`s, and a `Button` variant "link" for View original.
- Key facts: `Card` (`glass-panel`) with a definition list (`dl`).
- Reasons, concerns and summary: lists with `CitationChip` + `CitationPopover` (H0).
- Sources: a list. Each item is a `Card` `glass-inset` row. Web sources have an external link; profile sources link to `/profile`.
- Next steps: `Card` (`glass-panel`) with two numbered step rows, each with a status `Badge` and a primary or secondary `Button`. Save/Pass/Reset `Button`s sit below.
- `Toast` for action results, and `Drawer` for the mobile steps sheet.

## 6. Interactions

1. **Open application workspace:** if `status` is `new`, first save it (toast "Saved to shortlist"), then navigate to `/hope/applications/{id}` (SC27/SC28, H4/H5). The label follows the stage: "Start eligibility review" for `saved`, "Continue application" otherwise.
4. **Save / Pass / Move to New:** `POST /v1/grants/{id}/save|pass|reset`. Optimistic badge update, and a toast with Undo for 8 s. Undo sends `reset`, or the previous status's action. Pass shows the same optional reason sheet as SC25.
5. **Citation chip:** opens `CitationPopover` (quote, page title, domain, "Open source ↗", or the profile field with "Open profile"). Esc closes it and focus returns to the chip. Clicking a source in the Sources list highlights every chip with that ID for 2 s.
6. **Back to grants:** returns to `/grants` with the saved tab, mode, filters and position (`from` + session storage).
7. **Keyboard:** `b` builds or opens the brief, `p` drafts or opens the proposal (when enabled), `s` saves, `x` passes, `Esc` goes back to the list. Keys are inactive in inputs.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading | Title bar skeleton, a 3-line key-facts skeleton, and the Next steps panel with "Checking status…" |
| Not found (404 `grant_not_found`) | "We couldn't find this grant. It may have been removed when Hope refreshed its search." + "Back to grants" |
| Error | "We couldn't load this grant. Try again." + Retry |
| Brief or proposal status error | In the panel only: "Status unavailable" (muted). The CTA stays enabled |
| Deadline passed | Red banner "The deadline for this grant has passed ({date}). You can still read what Hope found." Both CTAs disabled |
| Passed grant | Muted banner "You passed on this grant." + "Move back to New" |
| No citations at all | "Hope couldn't find sources for these details. Check the original before relying on them." above Key facts |
| Not signed in | `RequireSession` redirects to `/login` |
| Offline | Banner "You're offline." Actions disabled |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount | `api.grants.get(id)` -> `GET /v1/grants/{id}` | all `GrantDetail` fields | Refetch on focus if older than 60 s |
| Mount | `useHope()` (`lib/hope/store.ts`) | `applications[applicationId(ORG_ID, id)].stage` | Browser state, no polling |
| Save / Pass / Reset | `api.grants.save\|pass\|reset(id)` | `status`, `previous_status` | Optimistic; rolled back on error |

## 9. Responsive behaviour

- ≥ 1280 px: two columns (content 2/3, Next steps 1/3 sticky at `top: 24px`).
- 1024-1279 px: the same, with the Next steps column at 320 px.
- 641-1023 px: a single column. Next steps moves above the summary.
- ≤ 640 px: as in section 3, with a sticky bottom bar.

## 10. Accessibility

- Landmarks: `main` holds an `article` (the grant) and an `aside` ("Next steps").
- The H1 is the title. Section headings are H2s.
- Status badges and the urgency always have text. Disabled CTAs keep their focus order and use `aria-disabled` with the hint text linked by `aria-describedby`.
- Polling updates are announced politely once, when they change ("Application brief is ready").
- External links say "(opens in a new tab)" to screen readers.
- Popovers trap focus and return it to their chip. Reduced motion: no slide on the drawer.

## 11. Fixture data

`api/grants/fixture.ts` `get(id)` returns the SC25 fixtures with full detail. Fixture #1 has 7
citations: 5 web and 2 profile. Fixture #8 is past its deadline. Fixture #3 has no citations.

SC26 tests seed `hope:state:v1` with an application at each stage.

## 12. Analytics and success measures

Events:
- `grant_overview_viewed {grant_id, fit_score, brief_status, proposal_status}`
- `grant_brief_cta {grant_id, from_status}`
- `grant_proposal_cta {grant_id}`
- `grant_source_opened {grant_id, citation_kind}`
- `grant_view_original {grant_id}`

Success: at least 60 % of overview visits on saved grants end in "Build application brief",
and at least 1 source is opened in 30 % of visits (users check the proof).

## 13. Acceptance criteria

- [ ] AC1 The page shows the title, funder line, fit, status, key facts (amount, deadline, eligibility with citations), summary, all reasons and concerns, and the sources list.
- [ ] AC2 "View original" opens `view_original_url` in a new tab with `rel="noopener noreferrer"`.
- [ ] AC3 The workspace CTA saves a `new` grant first, then goes to `/hope/applications/{id}`. The label follows the application stage.
- [ ] AC7 Save, Pass and Move to New are optimistic with Undo, and roll back on error.
- [ ] AC8 A past deadline disables both CTAs with the banner copy. An unknown id shows the not-found copy.
- [ ] AC9 Citation chips open popovers for web and profile citations. Clicking a source highlights its chips.
- [ ] AC10 Every state in section 7 renders with the exact copy.
- [ ] AC11 Mobile shows the sticky bottom bar and the steps drawer.
- [ ] AC12 axe finds no violations.

## 14. Test plan

| AC | Test |
|---|---|
| AC1 | `features/grants/GrantOverview.test.tsx::renders everything with citations` |
| AC2 | `GrantOverview.test.tsx::view original link` |
| AC3 | `GrantOverview.test.tsx::brief cta saves then navigates` |
| AC4 | `GrantOverview.test.tsx::proposal cta gated by brief` |
| AC5 | `GrantOverview.test.tsx::polls status until ready` (fake timers) |
| AC6 | `GrantOverview.test.tsx::status error does not block` |
| AC7 | `GrantOverview.test.tsx::status actions optimistic with undo` |
| AC8 | `GrantOverview.test.tsx::past deadline and not found` |
| AC9 | `GrantOverview.test.tsx::citation popovers and source highlight` |
| AC10 | `GrantOverview.test.tsx::state copy` |
| AC11 | `GrantOverview.test.tsx::mobile layout` |
| AC12 | `GrantOverview.a11y.test.tsx` |

## 15. Open questions

- **Should the overview fetch the live page to show more?** Recommended default: no. H4's brief does live fetching; the overview shows only what H2 stored, and that keeps it instant.
- **Should "Draft proposal" be allowed without a brief?** Recommended default: no (see AC4), because H5 needs the brief's questions.
- **Should passing from the overview go back to the list?** Recommended default: no. Stay on the page with the "You passed" banner, so Undo is easy.
