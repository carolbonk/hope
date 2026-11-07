# SC01: Sign in and sign up

| | |
|---|---|
| Route | `/login` (query: `tab=signin|signup`, `returnTo`, `signedOut=1`) |
| Feature folder | `apps/web/features/session/` |
| Built by | [H1](../features/H1-sign-in-and-profile.md) (uses H0's `api/session`) |
| Primary users | Nonprofit staff, once per 14 days (cookie lifetime); the presenter at the start of the demo |
| Can act | Anyone can open it (public route). Sign-up needs the team's invite code (H0), and joins the single organization |
| Status | Draft |

> **Aligned after PR #34/#35. This box is authoritative: where anything below disagrees (routes, `apps/web/src/...` paths, building a screen from scratch), this box wins.**
> - The UI already exists: the Hope frontend under `/hope/*` (zip port, liquid glass) plus SC11 `/onboarding`. Don't rebuild or restyle screens; keep `app/globals.css` and `features/onboarding/**` as they are.
> - `apps/web` has no `src/`: `app/`, `components/`, `lib/`, `features/`, `api/` sit at the package root, and `@/*` maps to `./*`.
> - Pages only call `useHope()` (`lib/hope/store.ts`) and `useOpportunities()` (`lib/hope/opportunities.ts`). A backend plugs in through its own adapter in `lib/hope/sync/<name>.ts`. Keep the hook signatures and don't edit pages for wiring.
> - The `/v1` contract in `contracts/` still holds for the backend. On the wire, money is `amount_minor` (integer) + ISO currency; the adapters convert to the UI's whole units.
> - **To build (H1):** `app/login/page.tsx`, liquid glass with `components/ui`. After sign-in, go to `/onboarding` if the profile isn't set up yet, otherwise to `returnTo` or `/hope/discover`.

## 1. Purpose and user goals

The front door. Users arrive by opening Hope, from `RequireSession` redirecting a 401
(`/login?returnTo=/grants/...`), or after signing out (`?signedOut=1`).

Within 5 seconds the screen must answer:
1. What is Hope? (one line: "Find grants that fit, and get a plain-English plan to apply.")
2. Do I sign in or create an account? (two tabs, sign-in first)
3. What went wrong? (one clear error, next to the field it concerns)

**Primary action:** Sign in. **Secondary:** Create account; fill the demo login (demo mode only).

## 2. Information hierarchy

1. Logo and the one-line promise.
2. The active tab's form (email, password, and display name on sign-up).
3. The submit button, full width.
4. Small print: "Free for nonprofits." and, in demo mode, the demo-account hint.

Hidden: password rules appear only on the sign-up tab, under the field; no "forgot password" (out of scope; see Open questions).

## 3. Wireframe

Desktop (>= 1024 px): centred card, 440 px wide, on the base colour; no app nav.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│                     ┌──────────────────────────────────┐               │
│                     │            (H)  Hope              │  <- logo mark (glass-inset) + wordmark
│                     │ Find grants that fit, and get a   │
│                     │ plain-English plan to apply.      │
│                     │ ┌──────────────┬───────────────┐  │  <- Tabs (glass-active = active)
│                     │ │ ● Sign in    │  Create account│  │
│                     │ └──────────────┴───────────────┘  │
│                     │ Email                             │
│                     │ [ dana@riverbendhealth.org      ] │  <- Input glass-inset
│                     │ Password                    [Show]│
│                     │ [ ••••••••••                    ] │
│                     │ [            Sign in            ] │  <- Button primary
│                     │ ─────────────────────────────────  │
│                     │ Demo: demo@hope.org / hope-demo   │  <- only when NEXT_PUBLIC_HOPE_DEMO=1
│                     │ [ Use the demo account ]          │
│                     │ Free for nonprofits.              │
│                     └──────────────────────────────────┘               │
└────────────────────────────────────────────────────────────────────────┘
```

Create-account tab adds "Your name" above Email, a password hint
"At least 8 characters." under Password, and a required "Invite code" field under Password with the
hint "Ask your team for the invite code."; the button reads "Create account".

Mobile (<= 640 px): the card is full width with 16 px margins, no outer shadow frame; same order.

## 4. Content inventory

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Promise | static | "Find grants that fit, and get a plain-English plan to apply." | - |
| Tab | URL `tab` | "Sign in" / "Create account" | Default `signin`; invalid value -> `signin` |
| Your name | input -> `display_name` | "Dana Okafor" | Sign-up only; required, 2-80 chars, trimmed |
| Email | input -> `email` | "dana@riverbendhealth.org" | Required; `type="email"`; trimmed and lower-cased before sending |
| Password | input -> `password` | masked; "Show"/"Hide" toggle | Required; sign-up needs >= 8 chars (client check mirrors H0's `weak_password`) |
| Invite code | input -> `invite_code` | "Xq7m-3Kp9-Lw2v-8Tz4" | Sign-up only; required; trimmed; `autocomplete="off"` |
| Field errors | client checks or problem `code` | "Enter your email address." | Under the field, `role="alert"` on submit |
| Form error | problem `code` | "That email or password isn't right." | Above the button |
| Signed-out notice | URL `signedOut=1` | "You're signed out." | `SuccessNotice`; removed from the URL after render |
| Demo hint | `NEXT_PUBLIC_HOPE_DEMO === "1"` | "Demo: demo@hope.org / hope-demo" | Button fills both fields and focuses Sign in |

## 5. Components

`Card` (`glass-panel`), H0 `Tabs` (active tab `glass-active`), `TextField` (`glass-inset`), `Button`
(primary, full width; ghost for Show/Hide and the demo button), `ErrorNotice`, `SuccessNotice`.
Feature files: `features/session/LoginScreen.tsx`, `SignInForm.tsx`, `SignUpForm.tsx`, `returnTo.ts`.
`app/login/page.tsx` renders `LoginScreen` outside the app chrome; the page sits on `glass-backdrop` and the card is `glass-panel`, so no text touches the backdrop.

## 6. Interactions

1. **Switch tab.** Click or ←/→ on the tab list; sets `?tab=` with `router.replace`; keeps the email value; clears errors.
2. **Sign in.** Client checks (empty email/password). Then `login({email, password})`
   (H0: `POST /v1/auth/login`). Button shows "Signing in…" and is disabled; fields read-only.
   - 200 -> `me()` (H0 `GET /v1/me`): `onboarding_complete` false -> `router.replace("/onboarding")`;
     else `router.replace(returnTo ?? "/grants")`.
   - 401 `invalid_credentials` -> form error; password cleared and focused.
   - 422 `validation_error` -> field errors from `errors[]`.
   - 429 (if H0 rate-limits) -> "Too many attempts. Wait a minute and try again."
   - Network / 5xx -> form error "We couldn't reach Hope. Check your connection and try again."
3. **Create account.** Client checks (name, email, password >= 8, invite code). `signup({email, password, display_name})`
   (H0: `POST /v1/auth/signup`). Button "Creating account…".
   - 201 -> `me()` -> `/onboarding` when not onboarded (normal for the first user), else `returnTo ?? "/grants"`.
   - 409 `email_taken` -> field error on Email with a link "Sign in instead" (switches tab, keeps email).
   - 422 `weak_password` -> field error on Password.
   - 403 `signup_closed` -> form error; focus moves to Invite code.
   - Network / 5xx -> same as sign-in.
4. **Show/Hide password.** Toggles `type`; button `aria-pressed`; focus stays on the toggle.
5. **Use the demo account.** Fills `demo@hope.org` / `hope-demo` on the Sign-in tab and focuses "Sign in" (does not submit, so the presenter controls the moment).
6. **Already signed in.** On mount, `me()`; 200 -> redirect as in interaction 2 (no form flash: show the loading state until `me()` settles).
7. **returnTo safety.** Only same-origin paths starting with `/` and not `//` are used; anything else becomes `/grants`.
8. **Keyboard.** Enter submits; the first field is auto-focused on load and on tab switch.

## 7. States and exact copy

| State | What shows |
|---|---|
| Checking session (mount) | Card with logo and a `Progress` bar (indeterminate), sr text "Checking your session…" |
| Idle | Form as in the wireframe |
| Submitting | "Signing in…" / "Creating account…" on the button |
| Empty email | "Enter your email address." |
| Bad email format | "Enter an email like name@example.org." |
| Empty password | "Enter your password." |
| Short password (sign-up) | "Use at least 8 characters." |
| Empty name (sign-up) | "Enter your name." |
| Empty invite code (sign-up) | "Enter your team's invite code." |
| `invalid_credentials` | "That email or password isn't right." |
| `email_taken` | "There's already an account with this email. Sign in instead?" |
| `weak_password` | "Use at least 8 characters." |
| `signup_closed` | "That invite code isn't right. Ask your team for the current code." |
| Rate limited | "Too many attempts. Wait a minute and try again." |
| Network / 5xx | "We couldn't reach Hope. Check your connection and try again." |
| Signed out | "You're signed out." |
| Offline (`navigator.onLine` false) | "You're offline. Connect to sign in." Button disabled |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount | H0 `me()` -> `GET /v1/me` | 200: `onboarding_complete`; 401 -> show form | none |
| Sign in | H0 `login()` -> `POST /v1/auth/login` `{"email":"demo@hope.org","password":"hope-demo"}` | 200 `{user}`; problem `code` | sets cookie |
| Create account | H0 `signup()` -> `POST /v1/auth/signup` `{"email":"dana@riverbendhealth.org","password":"…","display_name":"Dana Okafor","invite_code":"Xq7m-3Kp9-Lw2v-8Tz4"}` | 201 `{user}`; problem `code`, `errors[]` | sets cookie |
| After either | `GET /v1/me` | `onboarding_complete` | session cache in H0's provider is invalidated |

## 9. Responsive behaviour

- >= 641 px: 440 px card centred vertically.
- <= 640 px: full-width card, top-aligned with 24 px top margin; buttons 48 px tall.

## 10. Accessibility

- `h1` "Sign in to Hope" / "Create your Hope account" (visually the wordmark; heading text updates with the tab).
- Tabs follow the ARIA tabs pattern (`role="tablist"`, arrow keys, `aria-selected`).
- Inputs have visible labels, `autocomplete` (`email`, `current-password` / `new-password`, `name`).
- Errors: field errors linked via `aria-describedby`; on submit failure focus moves to the first invalid field or the form error (`role="alert"`).
- Contrast AA; 1 px borders on inputs; glass focus ring (2 px accent glow + outline); no motion except `motion-safe:` shadow transitions.
- Liquid glass: text sits only on `glass-panel` / `glass-chrome` / `glass-overlay`, never on `glass-backdrop`; contrast is checked against the worst-case background. Under `prefers-reduced-transparency: reduce` (and without `backdrop-filter` support) panels, inputs and overlays render solid with the same layout; `prefers-reduced-motion` stops the backdrop motion and highlight shimmer.

## 11. Fixture data

`features/session` tests mock H0's `api/session` module:
- `login`: `demo@hope.org` / `hope-demo` -> user Demo Admin; anything else -> `ApiError(401, …, "invalid_credentials")`.
- `signup`: `taken@hope.org` -> 409 `email_taken`; password `short` -> 422 `weak_password`; any invite code other than `hope-demo-invite-code` -> 403 `signup_closed`; otherwise 201.
- `me`: switchable: 401, `{onboarding_complete: false}`, `{onboarding_complete: true}`.
- A `network` switch throws `TypeError("Failed to fetch")`.

## 12. Analytics and success measures

Events: `auth_viewed {tab}`, `auth_submitted {tab}`, `auth_failed {tab, code}`, `auth_succeeded {tab, onboarding_complete}`.
Success: sign-up to finished onboarding in under 5 minutes; fewer than 10% of sign-ins fail with `invalid_credentials`.

## 13. Acceptance criteria

- [ ] AC1 Sign in with valid credentials goes to `returnTo` (or `/grants`); a not-onboarded user goes to `/onboarding`.
- [ ] AC2 `invalid_credentials` shows the exact copy, clears and focuses the password.
- [ ] AC3 Create account sends `display_name`, `email`, `password`, then goes to `/onboarding`.
- [ ] AC4 `email_taken` shows the field error with "Sign in instead" switching tabs and keeping the email.
- [ ] AC5 Client validation messages match section 7 and block the request.
- [ ] AC6 `?tab=signup` opens the create-account tab; switching tabs updates the URL.
- [ ] AC7 An already signed-in visitor is redirected without seeing the form.
- [ ] AC8 An unsafe `returnTo` (`https://evil.example`, `//x`) falls back to `/grants`.
- [ ] AC9 Demo mode shows the hint and fills the fields; non-demo mode hides it.
- [ ] AC10 `?signedOut=1` shows "You're signed out."
- [ ] AC11 Network failure shows the network copy.
- [ ] AC12 axe: no violations on both tabs and the error state.
- [ ] AC13 `signup_closed` shows the exact copy and focuses Invite code; the invite code is required and sent as `invite_code`.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `apps/web/features/session/LoginScreen.test.tsx::sign in redirects by onboarding state` |
| AC2 | `LoginScreen.test.tsx::invalid credentials` |
| AC3 | `LoginScreen.test.tsx::create account goes to onboarding` |
| AC4 | `LoginScreen.test.tsx::email taken offers sign in` |
| AC5 | `LoginScreen.test.tsx::client validation copy` |
| AC6 | `LoginScreen.test.tsx::tabs sync with url` |
| AC7 | `LoginScreen.test.tsx::redirects when already signed in` |
| AC8 | `apps/web/features/session/returnTo.test.ts::rejects unsafe targets` |
| AC9 | `LoginScreen.test.tsx::demo hint fills credentials` |
| AC10 | `LoginScreen.test.tsx::signed out notice` |
| AC11 | `LoginScreen.test.tsx::network error copy` |
| AC12 | `apps/web/features/session/LoginScreen.a11y.test.tsx` (vitest-axe) |
| AC13 | `LoginScreen.test.tsx::signup closed asks for invite code` |

## 15. Open questions

- Forgot password? Recommended default: no link in the hackathon (no email sending); add reset after the demo.
- Sign-up is invite-only (decided; H0 section 1, H1 D1).
