# SC09: Profile

| | |
|---|---|
| Route | `/profile` (hash anchors `#basics`, `#mission`, `#cause`, `#budget`, `#programs`, `#program-{program_id}`) |
| Feature folder | `apps/web/src/features/profile/` (replaces today's `ProfileEditor.tsx`, `SectionShell.tsx`, `sections.tsx`) |
| Built by | [H1](../features/H1-sign-in-and-profile.md) |
| Primary users | Development director / grant writer (after onboarding, then whenever programs or numbers change); the presenter, to show what the agents read |
| Can act | Any signed-in user (no roles in the hackathon) |
| Status | Draft |

The enterprise version of this screen (health strip, SAM.gov, HITL-0, documents, history) is
the S09 draft on `specs/profile`; this hackathon version keeps its layout ideas and drops those features.

## 1. Purpose and user goals

One page with everything Hope knows about the nonprofit, in the same five sections as
onboarding, each editable in place. Users arrive from the nav, from the user menu, from a
brief or proposal citation whose `profile_path` links here (`/profile#program-prg-chw`), or
from SC11's Review.

Within 5 seconds the screen must answer:
1. Is our profile complete enough for good matches? (completeness meter + top suggestion)
2. What does Hope think we do? (mission, NTEE, programs at a glance)
3. How do I fix something? (an Edit button on every section)

**Primary action:** edit a section and save. **Secondary:** follow a completeness suggestion; run discovery again after changes.

## 2. Information hierarchy

1. Header: organization name, "Last saved {time} by {name}", completeness meter.
2. Completeness suggestions (only when < 100%).
3. Sections in onboarding order, read mode by default (scannable), each with Edit.
4. A post-save nudge: "Run discovery again to use your changes."

Hidden: the enterprise fields (rates, audits, approvals) are not shown at all in the hackathon.

## 3. Wireframe

Desktop (>= 1024 px):

```text
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ (H) Hope    Grants   Discover   [Profile]                              Dana Okafor ▾      │  <- H0 app shell
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ Riverbend Community Health Alliance                                                       │  <- PageHeader
│ What Hope knows about you. Discovery, briefs and drafts all use this. Last saved Nov 7,   │
│ 4:40 PM by Dana Okafor.                                                                   │
│ ┌ Profile strength ───────────────────────────────┐                                       │  <- Card raised
│ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░  92%                         │
│ │ Next: Add the age range for Community Health Worker Network  [Fix →]                    │
│ └─────────────────────────────────────────────────┘                                       │
├───────────────┬──────────────────────────────────────────────────────────────────────────┤
│ On this page  │ Basics                                                          [Edit]   │  <- section Card (read mode)
│ · Basics      │ EIN 84-3917265 · 501(c)(3) public charity                                │
│ · Mission     │ Wenatchee, WA · Serves Chelan County, WA; Douglas County, WA; Washington │
│ · Cause       │ riverbendhealth.example.org ↗                                            │
│ · Budget      ├──────────────────────────────────────────────────────────────────────────┤
│ · Programs (3)│ Mission and values                                              [Edit]   │
│  <- anchor nav │ "Riverbend Community Health Alliance brings preventive care, dental…"   │
│    (sticky)   │ Vision: Every rural family can reach the care they need…                 │
│               │ Values: (Care regardless of ability to pay) (Community-led) (Bilingual…) │
│               ├──────────────────────────────────────────────────────────────────────────┤
│               │ Cause                                                           [Edit]   │
│               │ ① E32 Community Clinics · ② F30 Mental Health Treatment                  │
│               ├──────────────────────────────────────────────────────────────────────────┤
│               │ Budget                                                          [Edit]   │
│               │ $3,120,000 a year ($1M–$5M) · Fiscal year ends Jun 30                    │
│               ├──────────────────────────────────────────────────────────────────────────┤
│               │ Programs (3)                                          [+ Add program]    │
│               │ ┌ Mobile Dental Clinic ───────────────────────────────── [Edit] ┐        │
│               │ │ Two mobile units provide cleanings, sealants…                   │        │
│               │ │ Serves: Children and adults on Medicaid · 3,200 a year          │        │
│               │ └──────────────────────────────────────────────────────────────────┘     │
└───────────────┴──────────────────────────────────────────────────────────────────────────┘
```

Edit mode (one section at a time) replaces that card's body with the same fields as the
matching SC11 step and a footer `[Cancel] [Save changes]`; the card gets a `glass-active` accent edge to show it's being edited.

Mobile (<= 640 px): no anchor nav (a "Jump to" select at the top instead); cards full width;
the Save/Cancel footer is sticky while a section is in edit mode.

## 4. Content inventory

All from `GET /v1/profile` (H1).

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Org name | `form.basics.legal_name` | H1 | Wraps |
| Last saved | `updated_at`, `updated_by` | "Last saved Nov 7, 4:40 PM by Dana Okafor" | Relative within 24 h ("12 min ago"); `updated_by` email shows the part before "@" if no display name |
| Strength | `completeness.score` | `Progress` 92% + "92%" text | < 60 amber text "Needs work", 60-89 neutral "Good", >= 90 green "Strong"; always text + bar |
| Next suggestion | `completeness.suggestions[0]`, `missing[0]` | "Add the age range for Community Health Worker Network" + "Fix →" | "Fix" opens the section in edit mode and focuses the field for `missing[0]`; hidden at 100% |
| Basics | `form.basics.*` | "EIN 84-3917265 · 501(c)(3) public charity"; "Wenatchee, WA"; service area joined with "; "; website link (host only) | Website opens in a new tab with `rel="noopener"` |
| Mission | `form.mission.*` | Quote-styled mission; "Vision: …"; values as chips | Mission truncated to 3 lines with "Show more"; empty vision/values show "Not added" muted + Add link |
| Cause | `form.ntee_codes`, `ntee_labels` | "① E32 Community Clinics" | Order = priority; numbered text, not colour |
| Budget | `form.budget.*` | "$3,120,000 a year ($1M–$5M)" or "$1M–$5M a year (estimated)"; "Fiscal year ends Jun 30" | Exact via `Intl.NumberFormat`; band label map as SC11 |
| Programs | `form.programs[]` | Card per program: name, description (3 lines + Show more), "Serves: {people_served} · {annual_served} a year · ages {age_range}" | `id="program-{program_id}"` for deep links |
| Post-save nudge | after any successful save | "Saved. Run discovery again to use your changes." + "Run discovery" (`/discover`) | `Toast`, 8 s |

## 5. Components

- H0 app shell (`glass-chrome` top bar); `PageHeader`; `Card` (`glass-panel`; edit mode adds a `glass-active` accent edge); H0 `Progress`; `Badge` for strength label (icon + text); `Button`.
- Edit forms reuse SC11's step components and `TagInput`/`NteePicker` from `features/onboarding` (same spec, so importing is allowed) via a `mode="section"` prop.
- Feature files: `features/profile/ProfileScreen.tsx`, `SectionCard.tsx`, `ProgramCard.tsx`, `useProfile.ts`.
- H0 `Toast`; `ErrorNotice`, `Loading`, `EmptyState`.

## 6. Interactions

1. **Load.** `GET /v1/profile`; 404 `profile_not_found` -> `router.replace("/onboarding")`. Keep the `ETag`.
2. **Edit a section.** Opens edit mode for that section only; other Edit buttons are disabled
   (tooltip "Finish editing {section} first"). Focus moves to the first field.
3. **Cancel.** Discards changes (no prompt if unchanged; inline confirm "Discard your changes? [Discard] [Keep editing]" otherwise).
4. **Save changes.** Client-validates with SC11's rules. `PATCH /v1/profile` with only that
   section, e.g. `{"mission": {...}}` or `{"programs": [...]}`, header `If-Match: "{version}"`.
   Button "Saving…".
   - 200 -> read mode with the new data, new `ETag`, nudge toast; live region "Mission saved."
   - 422 `validation_error` -> field errors from `errors[]` (paths are form paths, e.g. `programs.1.description`).
   - 409 `version_conflict` -> stay in edit mode; `ErrorNotice` "Someone else saved the profile since you opened it." + "Reload their version" (refetches; your unsaved text is shown below the form as "Your text" for copying).
   - 428 `if_match_required` -> refetch the `ETag` and retry once.
   - 401 -> `/login?returnTo=/profile`.
   - Network / 5xx -> "We couldn't save {section}. Your changes are still here. Try again." + Retry.
5. **Programs.** "+ Add program" opens a new program card in edit mode at the end; saving
   sends the whole `programs` list. Each program's Edit edits only that card but still saves the
   whole list. "Remove program" (in edit mode) is disabled when only one program remains
   ("You need at least one program.").
6. **Fix (strength).** Opens the matching section and focuses the missing field.
7. **Deep links.** `#program-prg-chw` scrolls to and briefly outlines that card (outline only, no animation under reduced motion).
8. **Run setup again.** Link in the page footer "Prefer the guided setup? Run setup again" -> `/onboarding`.
9. **Keyboard.** `e` on a focused section opens Edit; Esc cancels (with the discard confirm); Ctrl+Enter saves.

## 7. States and exact copy

| State | What shows |
|---|---|
| Loading | Header skeleton + strength bar skeleton + 5 card skeletons |
| No profile (404) | Redirect to `/onboarding` (no flash) |
| Error (load) | `ErrorNotice` "We couldn't load your profile." + "Check your connection and try again." + Reload |
| Empty optional field | "Not added" (muted) + "Add" link opening edit mode |
| Validation | SC11 messages (e.g. "Mission statement is required.") |
| Saving | "Saving…" |
| Saved | Toast "Saved. Run discovery again to use your changes." |
| Conflict | "Someone else saved the profile since you opened it." + "Reload their version" |
| Save failed | "We couldn't save {section}. Your changes are still here. Try again." |
| Last program | "You need at least one program." |
| 100% strength | "Strong · 100%" and no suggestion row |
| Offline | Banner "You're offline. You can read your profile, but saving needs a connection." Save disabled |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount, after conflict reload | `GET /v1/profile` | `form`, `ntee_labels`, `completeness`, `version`, `updated_at`, `updated_by`, `ETag` | Refetch on window focus when no section is in edit mode |
| Save section | `PATCH /v1/profile` (one section, `If-Match`) | same as GET in the response | Replaces local state; invalidates H0 `me` (`onboarding_complete`) |
| NTEE edit | `GET /v1/profile/ntee-codes`, `POST /v1/profile/ntee-suggestions` | as SC11 | as SC11 |

## 9. Responsive behaviour

- >= 1024 px: 200 px sticky anchor nav + content (max 820 px).
- 641-1023 px: anchor nav hidden; "Jump to" select under the header.
- <= 640 px: full-width cards; sticky Save/Cancel in edit mode; program cards stack.

## 10. Accessibility

- `h1` org name; each section is a `section` with an `h2` and `aria-labelledby`.
- Edit mode: focus to the first field; on save/cancel focus returns to the section's Edit button; outcome announced in a polite live region.
- Strength is text + bar (`role="progressbar"` with `aria-valuenow`, label "Profile strength").
- Anchor nav is a `nav` with `aria-label="On this page"` and `aria-current` on the section in view.
- Contrast AA; 1 px borders; glass focus ring (2 px accent glow + outline); `prefers-reduced-motion` disables scroll smoothing and the deep-link outline fade.
- Liquid glass: text sits only on `glass-panel` / `glass-chrome` / `glass-overlay`, never on `glass-backdrop`; contrast is checked against the worst-case background. Under `prefers-reduced-transparency: reduce` (and without `backdrop-filter` support) panels, inputs and overlays render solid with the same layout; `prefers-reduced-motion` stops the backdrop motion and highlight shimmer.

## 11. Fixture data

`apps/web/src/api/profile/fixture.ts`:
- `getProfile` default: the H1 demo form (Riverbend), version 3, completeness 92 with `missing: ["programs.1.age_range"]` and the matching suggestion.
- Switches: `"incomplete"` (score 58; vision, values, website, exact budget missing), `"complete"` (100), `"none"` (404), `"error"` (503).
- `patchProfile`: merges the section, bumps the version; switches `"invalid"` (422 `programs.0.description` too_short), `"conflict"` (409 with `current_version: 4`), `"network"`.

## 12. Analytics and success measures

Events: `profile_viewed {score}`, `profile_section_edit_started {section}`, `profile_section_saved {section, seconds}`,
`profile_save_failed {section, code}`, `profile_fix_clicked {path}`, `profile_rerun_discovery_clicked`.
Success: profile strength >= 90% for the demo org; after edits, discovery is re-run within the session over 50% of the time.

## 13. Acceptance criteria

- [ ] AC1 Read mode shows every section's content as in the content inventory, with the strength meter and next suggestion.
- [ ] AC2 Edit opens one section at a time; others are disabled with the tooltip.
- [ ] AC3 Save sends only that section with `If-Match`, updates the view and shows the nudge toast.
- [ ] AC4 422 shows field errors from form paths; 409 shows the conflict copy and "Reload their version".
- [ ] AC5 Programs: add, edit one, remove (blocked on the last) all save the whole list.
- [ ] AC6 "Fix" opens the right section and focuses the missing field.
- [ ] AC7 `#program-{id}` scrolls to that program.
- [ ] AC8 A 404 redirects to `/onboarding`.
- [ ] AC9 Cancel with changes asks to discard; without changes it closes immediately.
- [ ] AC10 Every state in section 7 renders with the exact copy.
- [ ] AC11 Mobile shows the "Jump to" select and sticky Save/Cancel.
- [ ] AC12 axe: no violations in read, edit and error states.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `apps/web/src/features/profile/ProfileScreen.test.tsx::read mode content and strength` |
| AC2 | `ProfileScreen.test.tsx::one section edits at a time` |
| AC3 | `ProfileScreen.test.tsx::saves one section with if match` |
| AC4 | `ProfileScreen.test.tsx::validation and conflict` |
| AC5 | `apps/web/src/features/profile/ProgramCard.test.tsx::add edit remove programs` |
| AC6 | `ProfileScreen.test.tsx::fix focuses missing field` |
| AC7 | `ProfileScreen.test.tsx::program deep link` |
| AC8 | `ProfileScreen.test.tsx::redirects to onboarding without profile` |
| AC9 | `ProfileScreen.test.tsx::cancel discards with confirm` |
| AC10 | `ProfileScreen.test.tsx::state copy` |
| AC11 | `ProfileScreen.test.tsx::mobile layout` (matchMedia mock) |
| AC12 | `apps/web/src/features/profile/ProfileScreen.a11y.test.tsx` (vitest-axe) |

## 15. Open questions

- Show what the agents "see" (e.g. the exact search queries built from the profile)? Recommended default: no on this screen; H2's discovery screen shows its queries.
- Version history? Recommended default: out of scope; the backend keeps versions, so it can be added later.
- Allow editing while discovery is running? Recommended default: yes; the running job uses the profile as it was when it started (H2's job reads the profile at start).
