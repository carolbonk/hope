# SC11: Onboarding wizard

| | |
|---|---|
| Route | `/onboarding` (query: `step=basics|mission|cause|budget|programs|review`) |
| Files | `apps/web/app/onboarding/page.tsx` → `apps/web/features/onboarding/` (`OnboardingWizard.tsx`, `model.ts`, `useOnboardingDraft.ts`, `NteePicker.tsx`, `TagInput.tsx`, `steps/*`) |
| Built by | [H1](../features/H1-sign-in-and-profile.md) (PR #24). **Built and kept as is**: no restyle and no new copy. H1 makes only the two fixes in section 6 |
| Primary users | The first staff member after sign-up (once, about 5 minutes); anyone who opens `/onboarding` again |
| Can act | Any signed-in user (when online); anyone in this browser (when offline) |
| Status | Built. Remaining: the two fixes (401 → `/login?next=`, `invalidateSession()` after finishing) and their tests |

## 1. Purpose and user goals

Collect the minimum Hope needs to find and explain grants, without feeling like a grant application.

How users arrive:
- from SC01 after sign-up (`onboarding_complete: false`)
- from H0's `RequireSession`, which sends a user who hasn't onboarded from any `/hope/*` route to `/onboarding`
- by opening the URL directly

Within 5 seconds each step must answer:
1. What is this step asking, and why does Hope need it? (the "why" line under the title)
2. How far along am I? ("Step 2 of 6" and a progress bar)
3. What's required? (`*` on required labels; "(optional)" on the rest)

**Primary action:** Continue → (on Review: "Finish and find grants").
**Secondary actions:** ← Back, Edit a section from Review, Suggest codes.

## 2. Information hierarchy

1. Step label "Step n of 6", the step title (`h1`) and the "why" line.
2. The step's fields, required ones first.
3. ← Back / Continue →.
4. Progress and the step list: a left rail on desktop, a top bar on mobile.

Hidden: the browser-only parts of the Hope profile (contacts, capacity, the document dossier). Those live on SC09 `/hope/profile`.

## 3. Wireframe

`app/onboarding` sits outside `app/hope/layout.tsx`, so there is no `HopeNav`, no language toggle and no guard. The
root layout's `<main>` holds the wizard.

Desktop (≥ 1024 px): a 260 px rail plus the step card (max 720 px), centred.

```text
┌───────────────────────┬──────────────────────────────────────────────────────────────────┐
│ Set up your profile   │ STEP 2 OF 6                                                       │  <- Card (glass-panel)
│ ▓▓▓▓▓▓░░░░░░░░ 20%    │ Mission and values                                     (h1)       │
│                       │ Hope matches grants to what you do and why. Use your own words.   │
│ ✓ 1 Basics            │                                                                   │
│ ● 2 Mission & values  │ Mission statement *                                               │
│ ○ 3 Cause (NTEE)      │ ┌─────────────────────────────────────────────────────────────┐   │
│ ○ 4 Budget            │ │ Riverbend Community Health Alliance brings preventive care…│   │
│ ○ 5 Programs          │ └─────────────────────────────────────────────────────────────┘   │
│ ○ 6 Review            │ Vision (optional)                                                 │
│                       │ [ Every rural family can reach the care they need…          ]   │
│  <- rail: glass-inset  │ Values (TagInput, up to 10)                                       │
│     active: glass-active│ (Care regardless of ability to pay ×) (Community-led ×) [      ] │
│                       │                                          [ ← Back ] [ Continue → ]│
└───────────────────────┴──────────────────────────────────────────────────────────────────┘
```

Progress is `round(index / 5 * 100)`: 0, 20, 40, 60, 80, 100.

Step 3 (Cause) body (`CauseStep` → `NteePicker`):

```text
│ [ Search codes or words, e.g. "clinic" or E32            ]   <- ARIA combobox
│ ┌──────────────────────────────────────────────────────────┐
│ │ E32  Community Clinics                     Health Care    │  <- listbox (glass-chrome)
│ │ E30  Ambulatory Health Center              Health Care    │
│ └──────────────────────────────────────────────────────────┘
│ Selected                                                       
│ 1. E32 Community Clinics  Primary        [↑] [↓] [Remove]      
│ 2. F30 Mental Health Treatment           [↑] [↓] [Remove]      
│ Suggested from your mission                     [ Suggest codes ]
│ F30 Mental Health Treatment — Provides mental health support. "mental health" [c2]   [Add]
│ O50 Youth Development Programs — … [Unverified]                                    [Added]
```

Mobile (≤ 640 px):
- A `glass-chrome` top bar ("Step 2 of 6 · Mission and values" + progress) replaces the rail.
- The Back/Continue bar is fixed to the bottom (`glass-chrome`).
- Program cards and the NTEE listbox are full width.

## 4. Content inventory

The step model is `STEPS` in `features/onboarding/model.ts`, and the client rules are `validateStep`. All fields are `ProfileForm` paths (H1 section 2).

| Element | Field | Format and example | Rules (client = server) |
|---|---|---|---|
| **Basics** Legal name * | `basics.legal_name` | "Riverbend Community Health Alliance" | 2-200 chars |
| EIN * | `basics.ein` | "84-3917265" | `formatEin`: digits only, dash after the 2nd digit; must match `12-3456789`; the server also checks the prefix |
| Tax status | `basics.tax_status` | select, default "501(c)(3) public charity" | `TAX_STATUSES` |
| City * / State * | `basics.hq_city`, `basics.hq_state` | "Wenatchee", "WA – Washington" | city 2-80; state from `US_STATES` (50 + DC + PR) |
| Service area * | `basics.service_area` | tags "Chelan County, WA" | 1-20 entries, each 2-80 chars; quick picks = the HQ state name and "Nationwide" |
| Website (optional) | `basics.website` | "https://riverbendhealth.example.org" | `https://` is added on blur if missing |
| **Mission** statement * | `mission.mission_statement` | textarea | 20-2000 chars |
| Vision (optional) | `mission.vision_statement` | textarea | ≤ 2000 |
| Values | `mission.values` | tags | ≤ 10, 2-60 chars each |
| **Cause** NTEE * | `ntee_codes` | "E32 Community Clinics · Health Care" | 1-3, order = priority (↑/↓), the first is "Primary"; labels come from the search response |
| Suggestions | `POST /v1/profile/ntee-suggestions` | "F30 Mental Health Treatment — reason "quote" [c2]" | Shows the `reason` and the quote chip from `citation`; `verified: false` → "Unverified" badge; never auto-added |
| **Budget** band * | `budget.budget_band` | radio group: "Under $250K", "$250K–$1M", "$1M–$5M", "$5M–$25M", "Over $25M" | required |
| Exact budget (optional) | `budget.annual_operating_budget_usd` | "$3,120,000" | whole dollars; an amount outside the chosen band switches the band and shows "This amount is in the {band} band." |
| Fiscal year ends | `budget.fiscal_year_end` | month + day selects, default Dec 31 | stored as `MM-DD` |
| **Programs** Program name * | `programs[i].name` | "Mobile Dental Clinic" | 2-120 |
| Description * | `programs[i].description` | textarea | 20-1000 |
| People served * | `programs[i].people_served` | "Children and adults on Medicaid" | 2-200 |
| Served per year (optional) | `programs[i].annual_served` | "3,200" | integer |
| Age range (optional) | `programs[i].age_range` | "11-18" | ≤ 40 |
| **Review** | the whole form | one section per step, each with "Edit" | an error summary lists the steps that have errors |

## 5. Components

- From `components/ui`: `Card`, `Button`, `TextField`, `TextArea`, `SelectField`, `Badge`, `ErrorNotice`, `SuccessNotice`.
- Glass utilities: `glass-panel`, `glass-inset`, `glass-chrome`, `glass-active` and `glass-focus`, all from `app/globals.css`, which doesn't change.
- Feature files: `OnboardingWizard.tsx`, `steps/{Basics,Mission,Cause,Budget,Programs,Review}Step.tsx`, `TagInput.tsx`,
  `NteePicker.tsx`, `model.ts`, `useOnboardingDraft.ts`.
- Clients:
  - `profileApi()` (`getProfile`, `saveProfile`)
  - `onboardingApi()` (`searchNtee`, `suggestNtee`)
  - In both, `NEXT_PUBLIC_HOPE_API_URL` picks HTTP, and the offline fixture is used otherwise.
  - Tests inject both through props.
- After a save: `seedHopeProfile(form)` (`lib/hope/fromOnboarding.ts`) writes the Hope profile into `hope:state:v1`,
  keeping saved grants and applications.

## 6. Interactions

1. **Mount.** `getProfile()`:
   - A profile → prefill from `form`, keep `etag` and `ntee_labels`, and start at `firstIncomplete(form)`.
   - `null` (404) → the localStorage draft `hope.onboarding.v1` (with the notice "We restored your progress.") or `emptyForm()`.
   - **401 (fix 1)** → `router.replace("/login?next=%2Fonboarding")`.
   - Any other error → `ErrorNotice` "We couldn't load your profile." with Retry.
2. **Step from the URL.** `?step=` is used only when it is a valid id at or before `firstIncomplete(form)`. Otherwise
   the start step is used.
3. **Continue.** It validates the current step.
   - Invalid → errors under the fields, focus moves to the first `aria-invalid` field, and there is no navigation.
   - Valid → `saveDraft(form)`, then `router.push("?step=<next>")`, so browser Back works.
4. **Back.** Goes to the previous step and never loses data.
5. **Step rail.** Steps up to `max(firstIncomplete, current)` are clickable; later ones are disabled.
6. **NTEE search** (code, no model):
   - Typing is debounced 200 ms → `searchNtee(q, 20)` (`GET /v1/profile/ntee-codes`). Empty input shows the 26 groups.
   - ↑/↓ move, Enter selects, Esc closes.
   - A 4th selection shows "You can pick up to 3 codes."
7. **Suggest codes** (the LLM step; see H1 section 7). It is enabled once the mission is ≥ 20 chars.
   - It sends `suggestNtee({mission_statement, programs: [{name, description}]})` from the current draft.
     Nothing is saved, and the button reads "Suggesting…".
   - Each result shows "Add" (or "Added" when the code is already selected). Only a click adds a code.
   - `error: "suggestions_unavailable"` or a network error → "Suggestions aren't available right now. Search instead."
   - 429 `rate_limited` → "Too many requests. Try again in a minute."
   - Empty `suggestions` → "No suggestions for this mission. Search instead."
8. **Programs.** "+ Add another program" (max 10) appends a card. "Remove" asks inline "Remove {name}? [Remove] [Keep]".
9. **Finish** (Review): `saveProfile(form, etag)` (`PUT /v1/profile`, with `If-Match` when a profile exists). The button
   shows "Saving…", and Edit links are disabled.
   - 200/201 → `seedHopeProfile(form)`, `clearDraft()`, **`invalidateSession()` (fix 2)**, then
     `router.replace("/hope/discover?onboarded=1")`.
   - 422 `validation_error` → `errors[]` mapped by `stepOfField`; jump to the first step with an error.
     Review shows "Fix {n} items before finishing."
   - 428 `if_match_required` → refetch the `ETag` and retry once.
   - 409 `version_conflict` → "Someone else saved the profile while you were editing." + "Load their version" (refetch and prefill).
   - **401** → `router.replace("/login?next=%2Fonboarding")`. The draft stays in localStorage.
   - Anything else → "We couldn't save your profile. Your answers are kept on this device. Try again." + Retry.
10. **Leave mid-way.** The draft is in localStorage, and there is no blocking prompt.
11. **Keyboard.** Enter in a single-line field submits the step. Ctrl/⌘+Enter in a textarea submits the step.

LLMs suggest, code decides: the only model output on this screen is a list of suggested codes. Code checks each code
and quote on the server. The user picks the codes, and only `PUT` writes them.

## 7. States and exact copy

Step titles and "why" lines (`STEPS`):

| Step | Title | Why line |
|---|---|---|
| 1 | Basics | "Funders check who you are and where you work. Hope searches by your service area." |
| 2 | Mission and values | "Hope matches grants to what you do and why. Use your own words." |
| 3 | Cause | "NTEE codes are how funders categorize nonprofits. Pick up to 3; the first is your primary." |
| 4 | Budget | "Many grants are limited to organizations of a certain size." |
| 5 | Programs | "Grants fund programs. Tell Hope what you run and who it serves." |
| 6 | Review | "Check everything once. You can change it later on your profile." |

| State | What shows |
|---|---|
| Loading (mount) | rail skeleton + card with 3 field skeletons, `role="status"` "Loading your profile" |
| Load error | "We couldn't load your profile." / "Check your connection and try again." + Retry |
| Restored draft | `SuccessNotice` "We restored your progress." |
| Required empty | "{Label} is required." (e.g. "Mission statement is required.") |
| EIN format | "Enter your EIN as 12-3456789." |
| EIN prefix (server) | "This EIN prefix isn't assigned by the IRS. Check the number." |
| Too short / too long | "Write at least {n} characters." / "Keep it under {n} characters." |
| No NTEE code | "Pick at least one NTEE code." |
| Too many NTEE | "You can pick up to 3 codes." |
| Suggestions unavailable | "Suggestions aren't available right now. Search instead." |
| Unverified suggestion | `Badge` "Unverified", title "Hope couldn't find this phrase in your text." |
| Budget outside band | "This amount is in the {band} band." |
| Review with errors | "Fix {n} item(s) before finishing." |
| Saving | button "Saving…" |
| Conflict | "Someone else saved the profile while you were editing." + "Load their version" |
| Save failed | "We couldn't save your profile. Your answers are kept on this device. Try again." + Retry |
| Offline | "You're offline. Your answers are saved on this device." Finish is disabled |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount, "Load their version", 428 retry | `GET /v1/profile` | 404, or `form`, `ntee_labels`, `ETag` | none |
| NTEE search | `GET /v1/profile/ntee-codes?q=&limit=20` | `items[].code,label,group_label` | none |
| Suggest | `POST /v1/profile/ntee-suggestions` | `suggestions[]`, `error` | none |
| Finish | `PUT /v1/profile` (full `ProfileForm`, `If-Match` when a profile exists) | 200/201, `ETag` | then `invalidateSession()` (H0) |

Offline (no `NEXT_PUBLIC_HOPE_API_URL`): `FixtureProfileApi("empty", 400)` and `FixtureOnboardingApi("normal", 250)`, in memory.

## 9. Responsive behaviour

- ≥ 1024 px: rail + card.
- < 1024 px: the rail is hidden; the top bar shows the step and progress.
- ≤ 640 px: a fixed bottom action bar and full-width cards.

## 10. Accessibility

- Each step has one `h1` (the title). Focus moves to it on every step change, and a polite live region announces "Step 3 of 6, Cause".
- The rail is an `ol` with `aria-current="step"`. Completed steps carry the sr-only text ", completed".
- Required fields have `aria-required`. Errors are linked with `aria-describedby`. Review's error summary links to each step.
- `NteePicker` follows the ARIA 1.2 combobox pattern. The selected list has labelled Move up/down/Remove buttons, and
  suggestion buttons are labelled "Add {code} {label}".
- The budget bands are a `radiogroup` with arrow-key movement.
- Liquid glass:
  - Text sits only on `glass-panel` / `glass-chrome` / `glass-inset`.
  - Under `prefers-reduced-transparency: reduce` the panels render solid.
  - `prefers-reduced-motion` stops the progress transition.

## 11. Fixture data

`apps/web/lib/api/profile/fixture.ts` (`FixtureProfileApi`):
- Modes: `empty` (404), `existing` (`DEMO_FORM`, version 3), `invalid` (422 `basics.ein` / `invalid_ein_prefix` and
  `programs.0.description` / `too_short`), `conflict` (409) and `network`.
- `network` throws `ProblemError(0, "network_error")` once H0's `api/http.ts` lands.
- With no `etag` on an existing profile, it gives 428.

`apps/web/lib/api/onboarding/fixture.ts` (`FixtureOnboardingApi`):
- `searchNtee` uses `searchNteeCodes` (26 groups + about 40 codes in `api/onboarding/ntee.ts`).
- `suggestNtee` uses keyword rules with exact-substring quotes (E32, F30, O50, K31, L41). Modes: `unverified` and `down` (`suggestions_unavailable`).
- These are the same rules as the backend's `hope_profile/ntee_mock.py`.

## 12. Analytics and success measures

No analytics in the hackathon. Success: the median time to finish is under 5 minutes.

## 13. Acceptance criteria

- [ ] AC1 With no profile, the wizard starts at Basics; Continue is blocked with the exact messages until the required fields are valid.
- [ ] AC2 The draft persists to localStorage and is restored with the notice; future steps stay disabled in the rail.
- [ ] AC3 Suggestions show the reason and the quote chip; "Add" adds the code; no more than 3 codes can be picked; unverified items show the badge; unavailable shows the copy.
- [ ] AC4 Finish sends the full form, seeds `hope:state:v1` and lands on `/hope/discover?onboarded=1`.
- [ ] AC5 A 422 maps the server field errors to their steps.
- [ ] AC6 A 409 shows the conflict copy and "Load their version".
- [ ] AC7 An exact budget outside the chosen band switches the band and shows the warning.
- [ ] AC8 Programs can be added and removed with the inline confirm.
- [ ] AC9 EIN input formats digits into `12-3456789`.
- [ ] AC10 `?step=` works and browser Back returns to the previous step with its values intact.
- [ ] AC11 Review "Edit" links jump to the right step.
- [ ] AC12 An existing profile prefills the form, and Finish sends its `ETag` as `If-Match`.
- [ ] AC13 (fix 1) A 401 on mount or on Finish goes to `/login?next=%2Fonboarding`.
- [ ] AC14 (fix 2) A successful Finish calls `invalidateSession()` before redirecting.
- [ ] AC15 The H1 PR leaves `app/globals.css`, the step components' markup and all copy in this spec unchanged.

## 14. Test plan

Existing tests are in `apps/web/features/onboarding/OnboardingWizard.test.tsx`. New tests go in the same file.

| AC | Test (file::name) |
|---|---|
| AC1 | `OnboardingWizard.test.tsx::blocks continue until valid` (exists) |
| AC2 | `::restores draft from local storage and keeps future steps disabled` (exists) |
| AC3 | `::suggests NTEE codes with citations and limits to 3` (exists) |
| AC4 | `::finish saves and redirects` (exists) |
| AC5 | `::server errors map to steps` (exists) |
| AC6 | `::shows the conflict copy on 409` (exists) |
| AC7 | `::exact amount switches band` (exists) |
| AC8 | `::adds and removes programs` (exists) |
| AC9 | `::formats ein` (new) |
| AC10 | `::step url and back navigation` (new) |
| AC11 | `::review edit links` (new) |
| AC12 | `::existing profile prefills and sends if match` (new) |
| AC13 | `::redirects to login on 401` (new) |
| AC14 | `::finish invalidates the session` (new; mock `@/lib/api/session`) |
| AC15 | reviewer check: `git diff main -- apps/web/app/globals.css apps/web/features/onboarding/steps` shows no markup or copy change |

`apps/web/lib/hope/fromOnboarding.test.ts` covers `seedHopeProfile` and `profileFromOnboarding` (exists, plus H1's new cases).

## 15. Open questions

- "Prefill from our website" (fetch + LLM extraction)? Recommended default: no for the hackathon, because it adds a second agent and new failure modes.
- Should Programs be optional? No: H0's `onboarding_complete` and the drafting step need at least one program.
- Spanish copy? The wizard is English-only today (no toggle outside `/hope`). Adding ES would be new UI copy; ask first.
