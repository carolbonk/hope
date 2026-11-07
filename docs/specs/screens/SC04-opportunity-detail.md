# SC04: Opportunity detail

> **Out of scope for the hackathon. Don't build this.** This screen belongs to the earlier design. Hackathon agents build only the H0-H5 screens (SC00, SC01, SC09, SC11, SC24-SC28); see [`README.md`](../README.md).

| | |
|---|---|
| Route | `/opportunities/[opportunityId]` (query: `doc`, `page`). Also the small list at `/opportunities` (query: `q`, `closed`) |
| Feature folder | `apps/web/src/features/opportunities/` |
| Built by | [M1](../features/M1-opportunities.md) (hackathon MVP; the full version is S03) |
| Primary users | Development director / grant writer (before every go/no-go), program director (to check fit), finance director (to check money rules) |
| Can act | View and open documents: every M0 `Role`. Pursue: `development_director`, `program_director`, `executive_director` (through M4's endpoint) |
| Status | Draft |

## 1. Purpose and user goals

This is the "read the RFP" page: the normalized opportunity, checked against its source. In the
demo, people arrive from a matrix row's "View full opportunity", from an evidence link in the matrix
drawer ("View in document"), or from the `/opportunities` list.

Within 5 seconds the screen must answer:
1. Is it worth our time? (award, deadline, who can apply)
2. Can we trust what Hope extracted? (parse confidence, missing fields, evidence links)
3. What's the next step? (Pursue, or open the existing workflow)

**Primary action:** Pursue (or "Open workflow" if one exists).
**Secondary actions:** open a source document, open the opportunity on Grants.gov.

## 2. Information hierarchy

1. **Title and status.** What it is, and whether we're already pursuing it.
2. **Key facts strip.** Award, deadline countdown, cost share, number of awards, submission channel: the facts
   that settle most go/no-go conversations.
3. **Eligibility.** First among the sections, because an ineligible opportunity makes the rest moot.
4. **Requirements, then overview.**
5. **Documents and source.** In a side column: needed to check, not to decide.

Evidence quotes live in tooltips and page links rather than inline, so the page stays readable.
Provenance details (content hash, pipeline) sit at the bottom.

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ ‹ Back                                                                                    │
│ OJJDP FY 2026 Mentoring for Youth Impacted by Opioids and Other     ● Pursue 87  [Pursue ▶]│  <- header (PageHeader)
│ Substance Use                                                       (or ◷ In workflow [Open workflow])
│ Office of Juvenile Justice Delinquency Prevention · Federal · ALN 16.726                  │
│ Grants.gov O-OJJDP-2026-172743 ↗ · Parsed with 91% confidence                             │
├────────────┬──────────────┬──────────────┬──────────────┬─────────────────────────────────┤
│ Award      │ Due          │ Cost share   │ Awards       │ Submit via                      │  <- key facts (Card raised, 5 Wells)
│ Up to $2M  │ 8 days  !    │ Not required │ ~10          │ Grants.gov                      │
│            │ Nov 16 ET    │              │              │                                 │
├────────────┴──────────────┴──────────────┴──────────────┴──────┬──────────────────────────┤
│ Eligibility                                                    │ Documents (2)            │
│ Who can apply  Nonprofits with 501(c)(3) status (not higher ed)│ 📄 ojjdp-2026-172743.pdf │
│ Where          Nationwide                                      │    PDF · 1.8 MB [Open ↗] │
│ Registrations  SAM.gov · UEI · Grants.gov                      │ 🌐 Grants.gov synopsis   │
│ Clauses                                                        │    HTML · [Download]     │
│  ? Needs review  Applicants must serve youth aged 17 or… p.5 ↗ │                          │
│  ◌ Draft rule    Must partner with a substance-use…     p.6 ↗ │ Source                   │
│                                                                │ View on Grants.gov ↗     │
│ Requirements                                                   │                          │
│ ┌ Section ───────────── Page limit ─ Points ─┐                 │                          │
│ │ Program narrative        20         40     │ p.12 ↗          │                          │
│ │ Budget narrative          5         15     │                 │                          │
│ └────────────────────────────────────────────┘                 │                          │
│ Forms        SF-424, SF-424A, SF-LLL                           │                          │
│ Attachments  Logic model; Letters of support                   │                          │
│                                                                │                          │
│ Overview                                                       │                          │
│ OJJDP seeks applications for mentoring services for youth…     │                          │
│                                                                │                          │
│ About this record                                              │                          │
│ Version 1 · Updated Nov 8 · Hash sha256:5d1e… ⧉                │                          │
└────────────────────────────────────────────────────────────────┴──────────────────────────┘
```

Mobile (<= 640 px):

```text
┌──────────────────────────────┐
│ ‹ Back                       │
│ OJJDP FY 2026 Mentoring for  │
│ Youth Impacted by Opioids…   │
│ OJJDP · Federal · ● Pursue 87│
│ ┌────────────┬─────────────┐ │
│ │ Up to $2M  │ 8 days !    │ │  <- key facts, 2 columns
│ │ Cost: none │ ~10 awards  │ │
│ └────────────┴─────────────┘ │
│ Eligibility                  │
│ …                            │
│ Requirements                 │
│ …                            │
│ Documents (2)                │
│ …                            │
├──────────────────────────────┤
│ [        Pursue ▶        ]   │  <- sticky bottom bar
└──────────────────────────────┘
```

List page `/opportunities` (desktop):

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ Opportunities                                       6 open from Grants.gov │
│ [🔍 Search title, funder or opportunity number ]  [ ] Include closed       │
├───────────────────────────────────────────────────────────────────────────┤
│ Opportunity                                     │ Award     │ Due     │    │
│ OJJDP FY 2026 Mentoring for Youth Impacted…     │ Up to $2M │ 8 days !│ ●87│
│ Office of Juvenile Justice · O-OJJDP-2026-…     │           │ Nov 16  │    │
│ …                                                                         │
│                                                     [ Load more ]          │
└───────────────────────────────────────────────────────────────────────────┘
```

## 4. Content inventory

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Title | `GET /v1/opportunities/{id}` -> `title` | "OJJDP FY 2026 Mentoring for Youth…" | `h1`; wraps, never truncated |
| Funder line | `normalized.funder.name`, `.type`, `.aln[]` | "Office of … · Federal · ALN 16.726" | Type labels: `federal` "Federal", `private_foundation` "Private foundation", etc. Up to 3 ALNs, then "+n" |
| Source line | `provenance.source_id`, `normalized.source.url` | "Grants.gov O-OJJDP-2026-172743 ↗" | External link in a new tab; no link if `url` is null |
| Parse confidence | `normalized.parse_quality.overall_confidence` | "Parsed with 91% confidence" | Rounded down to a whole percent. < 0.80 -> `warn` `Badge` "Low confidence (72%)" |
| Recommendation | `tenant.recommendation`, `tenant.composite_score` | `● Pursue 87` | Same badge styles as SC03 (`RecommendationBadge` in `features/status.tsx`). Links to `/matrix?selected={id}`. Hidden when `tenant` is null or `recommendation` is null |
| Status / action | `tenant.workflow_id`, `tenant.state` | "◷ In workflow · Awaiting go/no-go" + "Open workflow" | `humanizeState()` from `lib/lifecycle.ts`. With no workflow: "Pursue" button (role-gated). Terminal states (`TERMINAL_STATES`) show the chip only |
| Award | `normalized.funding.award_ceiling`, `.award_floor` | "Up to $2M", "$50k–$250k" | `formatMoney(…, {compact: true})`. Neither present: "Not stated" |
| Due | `normalized.deadlines.application_due.value` + `.timezone`, `.rolling` | "8 days" over "Nov 16 ET" | `countdown()` from `lib/time.ts`: past -> "Closed", <= 7 days `bad` with "!", <= 14 days `warn`. Rolling -> "Rolling". Missing -> "Not stated". Shown in the funder's timezone, with the hour only if it isn't midnight |
| Cost share | `normalized.funding.cost_share` | "Required 20%", "Not required" | `formatBps`. `required: true` and no ratio -> "Required (amount not stated)". Null -> "Not stated" |
| Awards | `normalized.funding.expected_awards` | "~10" | Null -> "Not stated" |
| Submit via | `normalized.requirements.submission_channel` | "Grants.gov" | Null -> "Not stated" |
| Who can apply | `normalized.eligibility.applicant_types[]` | One line per type | Empty -> "Not restricted in the RFP" |
| Where | `normalized.eligibility.geographic_restrictions[]` | Comma list | Empty -> "Nationwide" |
| Registrations | `normalized.eligibility.required_registrations[]` | "SAM.gov · UEI · Grants.gov" | Hidden if empty |
| Clauses | `normalized.eligibility.clauses[]` (`text`, `rule_status`, `evidence[]`) | Badge + text + page links | Order: `needs_review`, `draft`, `approved`. Badges: `approved` `good`/`check` "Rule approved", `needs_review` `warn`/`alert` "Needs review", `draft` `neutral`/`dot` "Draft rule". Text clamps at 3 lines with "Show more". Section hidden if there are no clauses |
| Evidence link | `Evidence.artifact_id`, `.page`, `.quote` | "p.5 ↗" | Tooltip = `quote` (max 500 chars). Hidden if the artifact isn't in the documents list |
| Sections table | `normalized.requirements.sections[]` | Section, Page limit, Points, Evidence | "–" for nulls; sorted by `scoring_weight_points` desc, then document order; hidden if empty |
| Forms / attachments | `requirements.forms[]`, `requirements.attachments[]` | Comma list / semicolon list | Hidden if empty |
| Overview | `normalized.summary` | Paragraphs | Plain text only (never rendered as HTML). Clamped at 8 lines with "Show more" |
| Missing fields | `normalized.parse_quality.missing_critical_fields[]` | Banner text | Labels: `deadlines.application_due` "the application deadline", `funding.award_ceiling` "the award ceiling" |
| Documents | `GET .../documents` -> `documents[]` | Icon by type, `filename`, type + size ("PDF · 1.8 MB") | PDF and text -> "Open ↗" (inline, new tab); others -> "Download". `available: false` -> greyed "Not available", no action |
| About this record | `provenance.version`, `.recorded_at`, `.content_hash` | "Version 1 · Updated Nov 8 · Hash sha256:5d1e… ⧉" | Hash shows the first 4 hex after `sha256:`; copy button copies the whole hash |

## 5. Components

- Header: `PageHeader` (title, description = funder and source lines, actions = recommendation `Badge` + `Button`).
- Key facts: `Card` (`glass-panel`) with five `Well` (`glass-inset`) cells.
- Sections: one `Card` each; requirements uses `Table` (caption "Application sections").
- Clause and quality badges: `Badge` with icon.
- Documents and source: `Card` in a sticky right column on desktop.
- Pursue confirmation: `Modal`. Result: M0's `Toast`.
- Copy button: a local `ghost` `Button` using `navigator.clipboard` (no new shared primitive in the MVP).
- List page: `PageHeader`, `TextField` (search), a checkbox, `Table`, and a "Load more" `Button`.

## 6. Interactions

1. **Load.** `GET /v1/opportunities/{id}` and `GET /v1/opportunities/{id}/documents` run in parallel. The header
   and sections render when the first returns; the documents panel has its own skeleton.
2. **Pursue.** Opens the modal: "Start a pursuit for *{title}*? Hope creates a workflow and asks a development
   director or executive director for a go/no-go decision (HITL-1)." Confirm -> `POST /v1/opportunities/{id}/pursue`
   through M4's `pursue()` client. The confirm button reads "Starting…" and is disabled.
   - 201 `{workflow_id}`: close, toast "Pursuit started" with "Open workflow" (`/workflows/{workflow_id}`), and refetch the
     detail so the header shows the workflow.
   - 409 `already_pursuing` (Problem field `workflow_id`): toast "A pursuit already exists" with "Open workflow".
   - 422 `ineligible`: error in the modal: "This opportunity looks ineligible for your agency. Check the eligibility clauses first."
   - 403 `forbidden`: error in the modal: "Your current role can't start a pursuit. Switch to Development director in the user menu."
   - Network error or 5xx: "Couldn't start the pursuit. Try again."
3. **Open document.** An `<a href={downloadUrl(sha256, "inline")} target="_blank" rel="noopener noreferrer">`. No
   extra API call. "Download" links use `disposition=attachment`.
4. **Evidence link.** Opens the document at the page: `downloadUrl(sha256, "inline") + "#page=" + page` in a new tab
   (the `sha256` is looked up by `artifact_id` in the documents list).
5. **Deep link from SC03** (`?doc={artifact_id}&page={n}`): scrolls to the documents panel, outlines that document,
   and shows a `Button` "Open page {n}" next to it. It doesn't open a tab automatically (browsers block that).
6. **Copy hash.** Copies the full `content_hash`; a polite live region says "Copied".
7. **Back.** `router.back()` when the referrer is this app, otherwise a link to `/matrix`.
8. **Keyboard.** `p` opens the Pursue modal when the button is visible; Esc closes it.
9. **List page.** Typing debounces 300 ms, then `GET /v1/opportunities?q=` and updates `?q=` in the URL. "Include closed"
   sets `?closed=1` (`include_closed=true`). "Load more" sends `cursor=next_cursor`. Rows link to the detail page.
   422 `query_too_short` -> hint "Type at least 2 characters." under the field (no request is sent for 1 character).

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading | Header skeleton (title bar + 2 text bars), 5 key-fact skeleton cells, 3 section skeletons; the documents panel shows 2 skeleton rows |
| Not found (404) | `EmptyState`: "We couldn't find this opportunity." + "Back to opportunities" |
| Error (network / 5xx) | `ErrorNotice`: "We couldn't load this opportunity. Try again." + Retry |
| Documents error | In the panel: "Documents couldn't be loaded." + Retry; the rest of the page still works |
| No documents | In the panel: "Hope only has the Grants.gov listing for this opportunity." + "View on Grants.gov ↗" |
| Missing critical fields | `warn` banner: "Hope couldn't find {the application deadline / the award ceiling} in this RFP. Check the source before deciding." |
| Low confidence (< 80%) | `warn` banner: "Hope is less sure about this RFP than usual ({pct}%). Check the key facts against the documents." |
| Injection suspected (`injection_suspected`) | `bad` banner: "Parts of this RFP looked like instructions to an AI and were ignored. Read the source document before relying on the summary." |
| Closed | `neutral` banner: "Applications closed on {date}." Pursue hidden |
| No pursue role | No Pursue button; muted text "Switch to Development director to start a pursuit." |
| List: empty search | "No opportunities match "{q}"." + "Clear search" |
| List: nothing ingested | "No opportunities yet. Run `make demo` or `hope-ingest grants-gov` to load some." |
| Offline | Banner "You're offline. Showing what was already loaded." Pursue disabled |
| Stale artifact | Not applicable (no approvals on this screen) |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount | `GET /v1/opportunities/{id}` | `title`, `normalized.*` (section 4), `provenance.*`, `tenant`, `documents_count` | Per id for the session; refetch after Pursue |
| Mount | `GET /v1/opportunities/{id}/documents` | `documents[].{artifact_id, sha256, filename, media_type, size_bytes, available}` | Per id for the session |
| Open document | `GET /v1/artifacts/{sha256}/download?disposition=` (a plain link) | file | Browser cache, `max-age=300` |
| Pursue | `POST /v1/opportunities/{id}/pursue` (M4) | `workflow_id`, error `code` | Invalidates the detail |
| List mount, search, toggle | `GET /v1/opportunities?q=&include_closed=&limit=20` | `items[]`, `total`, `next_cursor` | Keep previous results while loading |
| Load more | `GET /v1/opportunities?…&cursor=` | same | Appends |
| Shell | `GET /v1/me` (M0) | `roles` | Session (the role switcher changes it) |

## 9. Responsive behaviour

- >= 1280 px: two columns (sections 2/3, documents 1/3, sticky).
- 1024-1279 px: the same, with filenames truncated (full name in a tooltip).
- 641-1023 px: one column; documents move under the key facts; key facts wrap 3 + 2.
- <= 640 px: the mobile wireframe: 2-column facts grid, stacked sections, a sticky Pursue bar; the modal is full screen.
- List page <= 640 px: rows become cards (title, funder, award, due).

## 10. Accessibility

- One `h1`; each section is a `section` with an `h2`. The documents column is an `aside` labelled "Documents".
- Badges and urgency use icon + text, never colour alone ("8 days !" also has visually hidden text "due soon").
- Evidence links have names like "Open page 5 of ojjdp-2026-172743.pdf, evidence for: Applicants must…".
- External links include visually hidden "(opens in a new tab)".
- The Pursue modal traps focus and returns it to the Pursue button; toasts use `role="status"`.
- Every card has a 1 px border with at least 3:1 contrast in addition to the liquid-glass shadow.
- `prefers-reduced-motion`: the deep-link outline appears without animation and scrolling is instant.

## 11. Fixture data

`apps/web/src/api/opportunities/fixture.ts` builds on `api/fixtures/opportunities.ts`:
- **hero:** the OJJDP mentoring opportunity (due in 8 days, ceiling $2M, two clauses `needs_review` and `draft`, three
  requirement sections, two documents), `tenant` with `recommendation: "pursue"`, score 87, no workflow.
- **in-workflow:** a tracked opportunity with `workflow_id: "wf-demo-1"` and state `AwaitingGoNoGo`.
- **terminal:** state `Declined`.
- **sparse:** no award, no cost share, no requirements, no clauses, no documents, and
  `missing_critical_fields: ["funding.award_ceiling"]`.
- **low-confidence:** `overall_confidence: 0.72`. **suspicious:** `injection_suspected: true`.
- **closed:** due yesterday. **rolling:** `rolling: true`.
- **unavailable document:** one document with `available: false`.
- **errors:** id `00000000-0000-0000-0000-000000000404` returns 404; `new FixtureOpportunitiesApi({ failDocuments: true })`.
- `searchOpportunities` supports `q`, `include_closed`, `ids` and cursor paging (page size 20) over these.
- M4's fixture `pursue()` returns `{workflow_id: "wf-demo-2"}`, and throws `already_pursuing` for **in-workflow** and
  `ineligible` for **sparse**.

## 12. Analytics and success measures

Log to the console in the MVP (no analytics backend): `opportunity_viewed {opportunity_id, from}`,
`opportunity_document_opened {opportunity_id, kind: "document"|"evidence"}`, `opportunity_pursue_started {opportunity_id}`,
`opportunity_search {q_length, result_count}`.
Demo success: the presenter goes from the matrix to this page, opens the real NOFO at a cited page, and starts a
pursuit in under 30 seconds without hitting an error state.

## 13. Acceptance criteria

- [ ] AC1 The header, key facts and sections render every field in section 4 from the **hero** fixture.
- [ ] AC2 The **sparse** fixture shows every "Not stated" / "Nationwide" / hidden-section fallback and the missing-fields banner.
- [ ] AC3 Deadline urgency follows the thresholds (red "!" <= 7 days, amber <= 14, "Rolling", "Closed"), shown in the funder's timezone.
- [ ] AC4 Clauses are ordered needs-review, draft, approved, with icon + text badges and working evidence links (`#page=`).
- [ ] AC5 Documents open inline (PDF) or download (others); unavailable documents have no link; the documents error state keeps the rest of the page.
- [ ] AC6 `?doc=&page=` outlines that document and offers "Open page n".
- [ ] AC7 Pursue is hidden without a pursue role and in terminal states; it handles 201, `already_pursuing`, `ineligible`, `forbidden` and a network error with the exact copy.
- [ ] AC8 Low-confidence, suspicious, closed, not-found and error states render with the exact copy.
- [ ] AC9 The list page searches (debounced, 2+ characters), toggles closed, loads more, and links to detail.
- [ ] AC10 The mobile layout shows the 2-column facts grid and the sticky Pursue bar.
- [ ] AC11 axe finds no violations on the hero, sparse, modal-open and list states.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `apps/web/src/features/opportunities/OpportunityDetail.test.tsx::renders hero facts and sections` |
| AC2 | `OpportunityDetail.test.tsx::sparse fallbacks and missing fields` |
| AC3 | `KeyFacts.test.tsx::deadline urgency and timezone` |
| AC4 | `OpportunityDetail.test.tsx::orders clauses with evidence links` |
| AC5 | `DocumentsPanel.test.tsx::open download unavailable and error` |
| AC6 | `OpportunityDetail.test.tsx::deep link outlines document` |
| AC7 | `OpportunityDetail.test.tsx::pursue permissions and outcomes` |
| AC8 | `OpportunityDetail.test.tsx::state copy` (one case per state) |
| AC9 | `OpportunityList.test.tsx::search toggle and load more` |
| AC10 | `OpportunityDetail.test.tsx::mobile layout` (matchMedia mock) |
| AC11 | `OpportunityDetail.a11y.test.tsx` (vitest-axe) |

## 15. Open questions

- Should the page show amendments ("what changed")? Recommended default: no for the MVP; the demo data has no amendments.
- Should the page offer an in-app PDF viewer with highlighted evidence? Recommended default: no; open the PDF at the page in a new tab.
- Should the list page be in the main nav? Recommended default: yes, as "Opportunities" (Request to M0 #1), because it's the
  quickest way to show the live Grants.gov pull in the demo.
- Should a 1-character search be allowed? Recommended default: no (2+ characters, enforced in the UI and the API).
