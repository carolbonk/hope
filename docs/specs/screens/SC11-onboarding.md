# SC11: Onboarding wizard

| | |
|---|---|
| Route | `/onboarding` (query: `step=basics|mission|cause|budget|programs|review`) |
| Feature folder | `apps/web/src/features/onboarding/` |
| Built by | [H1](../features/H1-sign-in-and-profile.md) |
| Primary users | The first staff member after sign-up (once, about 5 minutes); anyone redoing it from SC09 "Run setup again" |
| Can act | Any signed-in user |
| Status | Draft |

## 1. Purpose and user goals

Collect the minimum Hope needs to find and explain grants, without feeling like a grant
application. Users arrive from SC01 after sign-up (`onboarding_complete: false`), from
`RequireSession` redirecting a non-onboarded user, or from SC09.

Within 5 seconds each step must answer:
1. What is this step asking, and why does Hope need it? (one-line "why" under the title)
2. How far along am I? ("Step 2 of 6" and a progress bar)
3. What's required? (required fields marked; "Optional" on the rest)

**Primary action:** Continue (then "Finish and find grants" on Review).
**Secondary actions:** Back, edit a section from Review, ask for NTEE suggestions.

## 2. Information hierarchy

1. Step title + "why" line ("Funders filter by where you work. Hope uses this to search.").
2. The step's fields, required ones first.
3. Continue / Back.
4. Progress and step list (left rail on desktop, top bar on mobile).

Hidden: the enterprise profile (legal details beyond EIN, financial rates, approvals); not part of the hackathon.

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ (H) Hope                                                   Dana Okafor ▾                 │  <- minimal header (no nav)
├───────────────────────┬──────────────────────────────────────────────────────────────────┤
│ Set up your profile   │ Step 2 of 6                                                       │
│ ▓▓▓▓▓▓░░░░░░░░ 33%    │ Mission and values                                                │  <- Card raised
│                       │ Hope matches grants to what you do and why. Use your own words.   │
│ ✓ 1 Basics            │                                                                   │
│ ● 2 Mission & values  │ Mission statement *                                               │
│ ○ 3 Cause (NTEE)      │ ┌─────────────────────────────────────────────────────────────┐   │
│ ○ 4 Budget            │ │ Riverbend Community Health Alliance brings preventive care…│   │
│ ○ 5 Programs          │ └─────────────────────────────────────────────────────────────┘   │
│ ○ 6 Review            │ 182 / 2000                                                        │
│                       │ Vision (optional)                                                 │
│  <- step rail          │ [ Every rural family can reach the care they need…          ]   │
│     (Well, glass-inset) │ Values (optional, up to 10)                                       │
│                       │ (Care regardless of ability to pay ×) (Community-led ×) [+ Add]   │
│                       │                                                                   │
│                       │                                   [ ← Back ]   [ Continue → ]     │
└───────────────────────┴──────────────────────────────────────────────────────────────────┘
```

Step 3 (Cause) body:

```text
│ What kind of nonprofit are you? *  Pick up to 3 NTEE codes. The first is your primary.  │
│ [🔍 Search codes or words, e.g. "clinic" or E32          ]                               │
│ ┌──────────────────────────────────────────────────────────┐                            │
│ │ E32  Community Clinics                     Health Care    │  <- listbox (combobox popup)
│ │ E30  Ambulatory Health Center              Health Care    │
│ └──────────────────────────────────────────────────────────┘                            │
│ Selected: (1 · E32 Community Clinics ×) (2 · F30 Mental Health Treatment ×)              │
│ ✨ Suggested from your mission       [Suggest codes]                                      │
│  + F30 Mental Health Treatment — "mental health support" [c1]        [Add]               │
```

Step 5 (Programs): repeatable program cards (name, description, people served, number served
per year, age range) with "+ Add another program" (max 10) and "Remove" on each (not on the last one).

Step 6 (Review): one read-only `Card` per section with "Edit" links, and "Finish and find grants".

Mobile (<= 640 px): the rail becomes a top bar "Step 2 of 6 · Mission and values" with the
progress bar; Back/Continue become a sticky bottom bar; the NTEE results list is full width.

## 4. Content inventory

| Element | Source / target | Format and example | Rules |
|---|---|---|---|
| Progress | step index | "Step 2 of 6", bar 33% | `round(100 * (index) / 6)`; Review = 100% |
| **Basics** legal name * | `form.basics.legal_name` | "Riverbend Community Health Alliance" | 2-200 chars |
| EIN * | `basics.ein` | "84-3917265" | Auto-inserts the dash after 2 digits; 9 digits; server checks IRS prefix |
| Tax status | `basics.tax_status` | Select, default "501(c)(3) public charity" | Options = `TaxStatus` labels |
| City * / State * | `basics.hq_city`, `basics.hq_state` | "Wenatchee", select "WA – Washington" | 50 states + DC + PR |
| Service area * | `basics.service_area` | Tags "Chelan County, WA" "Washington" | 1-20 entries, each 2-80 chars; first suggestion = the HQ state; quick chip "Nationwide" |
| Website | `basics.website` | "https://riverbendhealth.example.org" | Optional; `https://` added if missing |
| **Mission** statement * | `mission.mission_statement` | textarea, counter "182 / 2000" | 20-2000 chars |
| Vision | `mission.vision_statement` | textarea | <= 2000 |
| Values | `mission.values` | tags | <= 10, 2-60 chars each, no duplicates |
| **Cause** NTEE * | `ntee_codes` via `GET /v1/profile/ntee-codes` | "E32 Community Clinics · Health Care" | 1-3; order = priority (drag handle or ↑/↓ buttons); labels from the search response |
| Suggestions | `POST /v1/profile/ntee-suggestions` | "F30 Mental Health Treatment — 'mental health support' [c1]" | Shows `reason`, quote as a `CitationChip` (profile citation); `verified: false` shows "Unverified" badge |
| **Budget** band * | `budget.budget_band` | Segmented: "Under $250K", "$250K–$1M", "$1M–$5M", "$5M–$25M", "Over $25M" | Required |
| Exact budget | `budget.annual_operating_budget_usd` | "$3,120,000" | Optional whole dollars; if it falls outside the chosen band, inline warning "This amount is in the $X band" and the band auto-switches on blur |
| Fiscal year end | `budget.fiscal_year_end` | Select month + day, default Dec 31 | Stored "MM-DD" |
| **Programs** name * | `programs[i].name` | "Mobile Dental Clinic" | 2-120 |
| Description * | `programs[i].description` | textarea | 20-1000 |
| People served * | `programs[i].people_served` | "Children and adults on Medicaid" | 2-200 |
| Served per year | `programs[i].annual_served` | "3,200" | Optional integer |
| Age range | `programs[i].age_range` | "11-18" | Optional, <= 40 |
| **Review** | the whole form | Section cards | "Edit" jumps to the step with `?step=` |

## 5. Components

- `Card` (`glass-panel`) for the step body; `Well` (`glass-inset`) for the step rail; H0 `Progress`.
- `TextField`, `TextArea`, `SelectField`, `Segmented` (budget bands, active `glass-active`), `Button`.
- Feature components: `OnboardingWizard.tsx`, `steps/BasicsStep.tsx`, `MissionStep.tsx`,
  `CauseStep.tsx`, `BudgetStep.tsx`, `ProgramsStep.tsx`, `ReviewStep.tsx`, `TagInput.tsx`,
  `NteePicker.tsx` (ARIA combobox + listbox), `useOnboardingDraft.ts` (localStorage).
- H0 `CitationChip` / `CitationPopover` for suggestion quotes; H0 `Toast` for the finish message.
- `TagInput` is feature-local; if SC09 also needs it, SC09 imports from `features/onboarding` (same spec).

## 6. Interactions

1. **Mount.** `GET /v1/profile`: 404 -> empty form (or the `localStorage` draft `hope.onboarding.v1`
   if present: notice "We restored your progress."); 200 -> prefill from `form` and keep the `ETag`
   (re-running setup). Step comes from `?step=` if valid and all earlier steps are valid; else the first incomplete step.
2. **Continue.** Validates the current step on the client (rules in section 4; same messages as
   the server's codes). Invalid -> errors under fields, focus to the first invalid field, no
   navigation. Valid -> saves the draft to `localStorage`, `?step=next` (`router.push`, so browser Back works).
3. **Back.** Previous step; never loses data.
4. **Step rail.** Completed steps and the current one are clickable; future ones are disabled until the steps before them are valid.
5. **EIN typing.** Digits only; the dash is inserted after the 2nd digit; paste "843917265" becomes "84-3917265".
6. **NTEE search.** Typing (debounced 200 ms) -> `GET /v1/profile/ntee-codes?q={text}&limit=20`.
   Empty input shows the 26 groups; picking a group fills the input with its letter to drill down.
   ↑/↓ move, Enter selects, Esc closes. A 4th selection is blocked with "You can pick up to 3 codes."
7. **Suggest codes.** Enabled once the mission is >= 20 chars. `POST /v1/profile/ntee-suggestions`
   `{mission_statement, programs: [...]}` (programs from the draft if already filled). Button
   "Suggesting…"; results list with "Add"; already-selected codes show "Added".
   `error: "suggestions_unavailable"` or a network error -> "Suggestions aren't available right now. Search instead."
   429 `rate_limited` -> "Too many requests. Try again in a minute."
8. **Programs.** "+ Add another program" appends an empty card and focuses its name; "Remove" asks
   inline "Remove {name}? [Remove] [Keep]".
9. **Finish (Review).** `PUT /v1/profile` with the whole form (+ `If-Match` when re-running).
   Button "Saving…"; all Edit links disabled.
   - 200/201 -> clear the draft, invalidate H0's `me` cache, `router.replace("/discover")`, `Toast` "Profile saved. Let's find grants that fit."
   - 422 `validation_error` -> map each `errors[].field` to its step; jump to the first step with an error and show messages; Review lists "Fix 2 items before finishing." with links.
   - 409 `version_conflict` -> "Someone else saved the profile while you were editing." + "Load their version" (refetch, prefill, keep the draft in memory for comparison is out of scope).
   - 428 `if_match_required` -> refetch to get the `ETag`, then retry once automatically.
   - 401 `not_signed_in` -> `/login?returnTo=/onboarding` (draft stays in `localStorage`).
   - Network / 5xx -> "We couldn't save your profile. Your answers are kept on this device. Try again." + Retry.
10. **Leave mid-way.** Draft is in `localStorage`; no blocking prompt.
11. **Keyboard.** Enter in a single-line field = Continue; Ctrl+Enter in a textarea = Continue.

## 7. States and exact copy

Step titles and "why" lines:

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
| Loading (mount) | Rail skeleton + card with 3 field skeletons |
| Restored draft | `SuccessNotice` "We restored your progress." |
| Required empty | "{Label} is required." (e.g. "Mission statement is required.") |
| EIN format | "Enter your EIN as 12-3456789." |
| EIN prefix (server) | "This EIN prefix isn't assigned by the IRS. Check the number." |
| Too short | "Write at least {n} characters." |
| Too many NTEE | "You can pick up to 3 codes." |
| Unknown NTEE (server) | "{code} isn't an NTEE code. Pick one from the list." |
| No NTEE results | "No codes match "{q}". Try a broader word like "health" or "youth"." |
| Suggestions unavailable | "Suggestions aren't available right now. Search instead." |
| Unverified suggestion | Badge "Unverified" + tooltip "Hope couldn't find this phrase in your text." |
| Budget outside band | "This amount is in the {band} band." |
| Review with errors | "Fix {n} items before finishing." |
| Saving | Button "Saving…" |
| Conflict | "Someone else saved the profile while you were editing." + "Load their version" |
| Save failed | "We couldn't save your profile. Your answers are kept on this device. Try again." |
| Offline | Banner "You're offline. Your answers are saved on this device." Finish disabled |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount | `GET /v1/profile` | 404 or `form`, `ETag` | none |
| NTEE search | `GET /v1/profile/ntee-codes?q=&limit=20` | `items[].code,label,group_label` | Cache per `q` for the session |
| Suggest | `POST /v1/profile/ntee-suggestions` | `suggestions[]`, `error` | none |
| Finish | `PUT /v1/profile` (full `ProfileForm`, `If-Match` when re-running) | response `ETag`, `onboarding_complete` | Invalidates H0 `me` |
| After finish | H0 `me()` | `onboarding_complete` | - |

## 9. Responsive behaviour

- >= 1024 px: 260 px rail + content (max 720 px).
- 641-1023 px: rail collapses into a horizontal stepper above the card.
- <= 640 px: top bar with step name and progress; sticky Back/Continue bar; program cards full width; NTEE listbox full width.

## 10. Accessibility

- Each step has an `h1` with the step title; on step change focus moves to it and the live region announces "Step 3 of 6, Cause".
- The rail is an ordered list with `aria-current="step"`; completed steps carry the text "completed" (not only ✓).
- Required fields: visible "*" plus `aria-required`; errors via `aria-describedby`, summary on Review links to fields.
- `NteePicker` follows the ARIA 1.2 combobox pattern; selected codes are a list with remove buttons labelled "Remove E32 Community Clinics"; reorder buttons labelled "Move up/down".
- Budget `Segmented` is a radio group.
- Contrast AA, 1 px borders on inputs and cards, glass focus ring (2 px accent glow + outline), `prefers-reduced-motion` disables the progress-bar transition.
- Liquid glass: text sits only on `glass-panel` / `glass-chrome` / `glass-overlay`, never on `glass-backdrop`; contrast is checked against the worst-case background. Under `prefers-reduced-transparency: reduce` (and without `backdrop-filter` support) panels, inputs and overlays render solid with the same layout; `prefers-reduced-motion` stops the backdrop motion and highlight shimmer.

## 11. Fixture data

`apps/web/src/api/profile/fixture.ts` and `apps/web/src/api/onboarding/fixture.ts`:
- `getProfile`: 404 by default for onboarding tests; `"existing"` switch returns the H1 demo form (Riverbend) with `ETag "3"`.
- `saveProfile`: echoes the form as version 1; switches: `"invalid"` (422 with `basics.ein`/`invalid_ein_prefix` and `programs.0.description`/`too_short`), `"conflict"` (409), `"network"`.
- `searchNtee`: 40 real codes (all of group E, F30, F32, B, O50, P, W) with the search ranking of H1 step 12; empty `q` returns 26 groups.
- `suggestNtee`: returns E32 (verified) and F30 (verified) for any mission containing "dental" or "health"; `"unverified"` switch returns one item with `verified: false`; `"down"` switch returns `error: "suggestions_unavailable"`.

## 12. Analytics and success measures

Events: `onboarding_step_viewed {step}`, `onboarding_step_completed {step, seconds}`, `onboarding_ntee_suggested {count}`,
`onboarding_ntee_suggestion_added {code}`, `onboarding_finished {seconds_total, programs, ntee_count}`, `onboarding_save_failed {code}`.
Success: median time to finish under 5 minutes; over 80% of started onboardings finish.

## 13. Acceptance criteria

- [ ] AC1 With no profile, the wizard starts at Basics; Continue is blocked with the exact messages until required fields are valid.
- [ ] AC2 Steps are reflected in `?step=`; browser Back returns to the previous step with values intact; future steps are disabled in the rail.
- [ ] AC3 The draft persists to `localStorage` and is restored with the notice after reload.
- [ ] AC4 EIN input formats digits into `12-3456789`.
- [ ] AC5 NTEE search shows results from the endpoint, supports keyboard selection, limits to 3 and allows reordering.
- [ ] AC6 Suggestions show reason and a citation chip; "Add" adds the code; unverified items show the badge; unavailable shows the copy.
- [ ] AC7 An exact budget outside the chosen band shows the warning and switches the band.
- [ ] AC8 Programs can be added (max 10) and removed (not the last).
- [ ] AC9 Review shows every section with Edit links that jump to the right step.
- [ ] AC10 Finish sends the full form; success clears the draft and lands on `/discover` with the toast.
- [ ] AC11 A 422 maps server field errors to their steps and shows "Fix {n} items before finishing."
- [ ] AC12 Re-running with an existing profile prefills it and sends `If-Match`; 409 shows the conflict copy.
- [ ] AC13 Mobile layout uses the top bar and sticky actions.
- [ ] AC14 axe: no violations on each step and the Review error state.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `apps/web/src/features/onboarding/OnboardingWizard.test.tsx::blocks continue until valid` |
| AC2 | `OnboardingWizard.test.tsx::step url and back navigation` |
| AC3 | `OnboardingWizard.test.tsx::restores draft from local storage` |
| AC4 | `apps/web/src/features/onboarding/steps/BasicsStep.test.tsx::formats ein` |
| AC5 | `apps/web/src/features/onboarding/NteePicker.test.tsx::search select limit reorder` |
| AC6 | `NteePicker.test.tsx::suggestions with citations and fallbacks` |
| AC7 | `apps/web/src/features/onboarding/steps/BudgetStep.test.tsx::exact amount switches band` |
| AC8 | `apps/web/src/features/onboarding/steps/ProgramsStep.test.tsx::add and remove programs` |
| AC9 | `OnboardingWizard.test.tsx::review edit links` |
| AC10 | `OnboardingWizard.test.tsx::finish saves and redirects` |
| AC11 | `OnboardingWizard.test.tsx::server errors map to steps` |
| AC12 | `OnboardingWizard.test.tsx::rerun prefills and handles conflict` |
| AC13 | `OnboardingWizard.test.tsx::mobile layout` (matchMedia mock) |
| AC14 | `apps/web/src/features/onboarding/OnboardingWizard.a11y.test.tsx` (vitest-axe) |

## 15. Open questions

- Should the wizard offer "Prefill from our website" (fetch + LLM extraction)? Recommended default: no for the hackathon; it adds a second agent and new failure modes. Revisit after the demo.
- Should Programs be optional? Recommended default: no; at least one program is required because H0's `onboarding_complete` and the drafting agent depend on it.
- Save each step to the server? Recommended default: no; `localStorage` draft + one `PUT` (H1 D2).
