# SC09: Organization profile and document dossier

| | |
|---|---|
| Route | `/hope/profile` |
| Files | `apps/web/app/hope/profile/page.tsx` (built; owned by H1 so nobody else edits it; **no change in the hackathon**) |
| Built by | PR #34 (the Hope frontend). H1 adds only the backend sync behind `useHope()` (`lib/hope/sync/profile.ts`) |
| Primary users | Development director / grant writer; the presenter, to show what Hope knows |
| Can act | Anyone in this browser (offline); any signed-in user (online, behind H0's `RequireSession`) |
| Status | Built. Remaining H1 work is the sync adapter; this page's code doesn't change |

## 1. Purpose and user goals

One place for everything the nonprofit tells Hope: identity, mission and programs, capacity, the **document
dossier**, and a review. Discover's match reasons and the H4 workspace (`requirementStatus`, `oppDocs`) read the same
`OrgProfile`. Users arrive from the "Profile" item in `HopeNav`, and from "Update in your dossier →" in the H4 workspace.

Within 5 seconds the screen must answer:
1. How far along is our profile? (the 5-step rail and the "Profile n/5 steps complete" notice)
2. What is still pending? (the Review step's pending list and its three states)
3. Is this a certification? No: the gold notice says so on every step.

**Primary action:** "Save & continue". **Secondary:** fill in the demo organization; go to a step; on Review, Resolve
a pending item, record a simulated review, or request team review.

## 2. Information hierarchy

1. `PageIntro`: kicker "The heart of your matches", title "Start with your purpose.", and the intro line.
2. The not-certification notice with the storage note.
3. The resume notice (only when 0 < `completedSteps` < 5).
4. The 5-step rail: Identity · Mission & programs · Capacity · Documents & requirements · Review.
5. The step `Panel`: "Step n of 5 · {step}", "Fill with demo organization", the fields, then Back / status / Save & continue.

## 3. Wireframe

Inside `app/hope/layout.tsx` (`HopeNav` with the EN/ES toggle, `HopeFooter`).

```text
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ hope✳     Discover   Saved (2)   Deadlines   [Profile]                         EN | ES   │  <- HopeNav (glass-chrome)
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ THE HEART OF YOUR MATCHES                                                                 │  <- PageIntro
│ Start with your purpose.                                                                  │
│ Build the profile and document dossier our team can review. Leave anything you don't…    │
│ ┌ Completing this profile is not legal certification… Saved in this browser only… ┐      │  <- gold notice
│ [1 Identity] [2 Mission & programs] [3 Capacity] [4 Documents & requirements] [5 Review]  │  <- rail (navy = current, sage = done)
│ ┌ Panel (glass-panel) ───────────────────────────────────────────────────────────────┐   │
│ │ Step 2 of 5 · Mission & programs               Fill with demo organization (demo)   │   │
│ │ Mission [                                                               ]           │   │
│ │ Vision  [                                                               ]           │   │
│ │ Population served [        ]   Territory / service area [ Miami-Dade ▾ ]            │   │
│ │ Does the organization serve minors?  (Yes) (No) (Unknown)                           │   │
│ │ Impact areas  [mentoring] [youth] [family] …                                        │   │
│ │ Programs: name · what it does · measurable result · people served per year  [+ Add] │   │
│ │ [ Back ]                        ● Unsaved changes                [ Save & continue ]│   │
│ └────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

Mobile: the rail shows step numbers only, and the fields stack in one column.

## 4. Content inventory

Everything is `OrgProfile` in `hope:state:v1` (`lib/hope/types.ts`). The **Sync** column shows what H1's adapter sends
to `/v1/profile`. The full mapping is in H1 section 12, `formFromProfile`.

| Step | Fields | Sync to `/v1/profile` |
|---|---|---|
| 1 Identity | `legalName`, `publicName`, `country`, `jurisdiction`, `website`, contacts, responsible person, `legalStatus`, `has501c3` (US) / `usTaxStatus` (non-US) | `legalName` → `basics.legal_name`; `website`; `jurisdiction` → `basics.hq_state` when it is a US state; `legalStatus` → `basics.tax_status`. The rest stays in the browser |
| 2 Mission & programs | `mission`, `vision`, `targetPopulation`, `servesMinors`, `serviceArea`, `focusAreas`, `programs[] {id, name, description, outcomes, served}` | `mission`, `vision`, `serviceArea` (split on `;`), programs' `name` / `description` / `served` by id. `outcomes`, `focusAreas` and `servesMinors` stay in the browser |
| 3 Capacity | `annualBudget`, `currency`, `fiscalYear`, staff, volunteers, `foundedYear`, `experience`, `fundingNeed`, `intendedUse` | `annualBudget` (only when `currency` is USD; rounded to whole dollars, band derived) → `budget.*`; `fiscalYear`'s trailing `MM-DD`. The rest stays in the browser |
| 4 Documents & requirements | `dossier[ReqId]` (`status`, `naReason`, `evidenceRef` = a file **name** only, `period`, `expires`, comments) | never. Nothing is uploaded |
| 5 Review | `summary(profile)`: profile complete / documentation reviewed / eligibility per call; pending items; simulated reviews; `reviewRequest` (`delivery: "local_only"`) | never |

NTEE codes, EIN, HQ city, people served and age range have no field on this page. The sync keeps the server's values
for them (they come from SC11).

## 5. Components

`PageIntro`, `Panel`, `btnPrimary`, `btnSecondary`, `input` and `focusRing` from `components/hope/ui.tsx`; local `Field`,
`Text`, `Tri`, `Checks`, `Programs`, `Dossier`, `ReqRow`, `Review` and `StateCard` in `page.tsx`. Rules come from `lib/hope/dossier.ts`
(`applicability`, `pendingItems`, `summary`, `PROFILE_STEPS = 5`). Copy is `h.profile.*` in `lib/hope/i18n.ts` (EN + ES).

## 6. Interactions

1. **Load.** `useHope().state.profile` (`normalizeProfile` migrates old records). Online, H0's `HopeSync` has already
   called `loadRemoteProfile()`. When the server copy is newer, it was hydrated into the browser state. The page doesn't know or care.
2. **Edit.** Any change marks it "Unsaved changes", and leaving the page triggers the browser's `beforeunload` prompt.
3. **Save & continue** (code only):
   - Step checks:
     - Step 1 needs a legal name and a well-formed contact email (when given).
     - Step 2 needs a mission.
     - Step 3 parses the numbers (positive budget, whole counts, a year from 1800 to now).
     - Empty programs are dropped.
   - Then `useHope().saveProfile(next)` writes `hope:state:v1` and shows "Saved".
   - **Online:** H0's `saveProfile` then calls `saveRemoteProfile(next)`, which is fire-and-forget and never throws.
     The page never waits for it and shows no sync state.
4. **Fill with demo organization.** Loads `DEMO_PROFILE` (Tidepath, fictional) into the draft without saving.
5. **Rail and Back.** You can go to any completed step. Back goes to the previous step.
6. **Review → Resolve.** Opens the step and focuses the field or requirement row for the pending item.
7. **Simulated review / Request team review.** These are browser-only records (`simulated: true`, `delivery: "local_only"`). They are never sent.

No model call happens on this page.

## 7. States and exact copy

These are the existing strings from `h.profile.*`. H1 changes none of them.

| State | What shows |
|---|---|
| Not certification | "Completing this profile is not legal certification and does not guarantee eligibility for any funding opportunity." |
| Storage note | "Saved in this browser only (localStorage). No server, no sign-in, no file uploads." (stays as is in the hackathon; see Open questions) |
| Resume | "Profile {n}/5 steps complete — pick up where you left off." |
| Unsaved / saved | "● Unsaved changes" / "✓ Saved" |
| Errors | "Add the organization's legal name." · "Enter a valid email, or leave blank for now." · "Add a mission so we can explain matches." · "Enter a positive number, or leave blank if unknown." · "Enter a positive whole number, or leave blank if unknown." · "Enter a year between 1800 and this year, or leave blank." |
| No programs | "No programs yet — add at least one so funders understand your work." |
| Sync failure (online) | nothing on the page; `console.warn("[hope-sync] profile", code)` |

## 8. Data and endpoints

The page itself calls no endpoint. H1's adapter makes these calls behind `useHope()`:

| Trigger | Call (from `lib/hope/sync/profile.ts`) | Fields used | Notes |
|---|---|---|---|
| `HopeSync` once the session is ready | `GET /v1/profile` | `form`, `updated_at`, `ETag` | A newer server copy → `hydrateProfile` (no echo) |
| `saveProfile` (Save & continue) | `PATCH /v1/profile` with only the changed, valid sections, `If-Match` | the response `form`, `ETag` | 409/428 → refetch and retry once; 422 → drop those sections; network → retry later |

Offline (no `NEXT_PUBLIC_HOPE_API_URL`): no calls at all.

## 9. Responsive behaviour

- ≥ 640 px: two-column field grids; the rail shows labels from `md` up.
- < 640 px: one column; the rail shows numbers only.

## 10. Accessibility

- The page has an `h1` from `PageIntro` and an sr-only `h2` "Your organization profile".
- The rail is an `ol` with `aria-current="step"` and `aria-label` "{n}. {label}".
- Tri-state questions are radio groups. "Unknown" is never shown as "No".
- The save status is `role="status"`, and errors are `role="alert"`.
- Liquid glass: text sits on `glass-panel` / `glass-chrome` only. Reduced transparency and reduced motion are respected by `app/globals.css`.

## 11. Fixture data

- Browser: `DEMO_PROFILE` (Tidepath, Miami-Dade, fictional) in `lib/hope/store.ts`.
- Sync tests (`lib/hope/sync/profile.test.ts`):
  - a stubbed `profileApi()` / `fetch`
  - server responses from `contracts/mocks/w2/profile.get/ok.json` and `profile.patch/{ok,version_conflict}.json`
  - a seeded `hope:state:v1`

## 12. Analytics and success measures

No analytics in the hackathon. Success: online, an edit saved here shows up in `GET /v1/profile` within one save.

## 13. Acceptance criteria

- [ ] AC1 The page renders and saves exactly as on main, with no diff under `app/hope/profile/**`.
- [ ] AC2 Offline, saving makes no network request.
- [ ] AC3 Online, Save & continue PATCHes only the sections the edit changed, with `If-Match`, and the page never waits on it.
- [ ] AC4 Browser-only fields (dossier, contacts, capacity extras, program outcomes, reviews) are never sent, and they survive a server hydrate.
- [ ] AC5 A newer server profile replaces only the synced fields on load; an older one is ignored.
- [ ] AC6 A non-USD budget is not sent, and the server's budget is kept.
- [ ] AC7 A sync failure (409 twice, 422, network) changes nothing on screen and never loses the browser edit.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | reviewer check: `git diff --stat main -- apps/web/app/hope/profile` is empty |
| AC2 | `apps/web/lib/hope/sync/profile.test.ts::off without api url` |
| AC3 | `profile.test.ts::save patches changed valid sections` |
| AC4 | `apps/web/lib/hope/fromOnboarding.test.ts::round trip keeps browser-only fields` |
| AC5 | `profile.test.ts::load returns newer server profile only` |
| AC6 | `fromOnboarding.test.ts::formFromProfile mapping` (non-USD case) |
| AC7 | `profile.test.ts::conflict retries once`, `::validation drops sections`, `::network sets pending and retries` |

## 15. Open questions

- **The storage note is wrong online.** "Saved in this browser only … No server" is untrue once sync is on. Recommended:
  in a later PR, add `h.profile.storageSynced` (EN + ES) and show it when `syncEnabled`. That is a page and i18n change,
  so it needs the owner's go-ahead.
- **Sync status UI** (pending / failed)? Recommended default: none in the hackathon, because pages don't change.
- **NTEE, EIN, HQ city and people served** are editable only in SC11 today. Re-running `/onboarding` prefills from the server and updates them.
