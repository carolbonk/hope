# SC01: Sign in and sign up

| | |
|---|---|
| Route | `/login` (query: `tab=signin|signup`, `next`, `signedOut=1`) |
| Files | `apps/web/app/login/` (`page.tsx`, `LoginScreen.tsx`, `copy.ts`): to build |
| Built by | [H1](../features/H1-sign-in-and-profile.md), using H0's `api/session` (`me`, `login`, `signup`, `invalidateSession`, `safeNext`) and `api/http.ts` (`ProblemError`) |
| Primary users | Nonprofit staff, once per 14 days (the cookie lifetime); the presenter at the start of the demo |
| Can act | Anyone can open it (it is outside the `/hope/*` guard). Sign-up needs the team's invite code (H0) and joins the single organization |
| Status | Draft (the only new H1 page) |

## 1. Purpose and user goals

This is the front door. Users arrive in three ways:
- by opening Hope while signed out: H0's `RequireSession` in `app/hope/layout.tsx` sends them to `/login?next=/hope/...`
- from SC11 on a 401: `/login?next=%2Fonboarding`
- from SC00's Sign out: `/login`
- after signing out: `?signedOut=1`

Within 5 seconds the screen must answer:
1. What is Hope? In one line: "Find grants that fit, and get a plain-English plan to apply."
2. Do I sign in or create an account? Two tabs, with sign-in first.
3. What went wrong? One clear error, next to the field it concerns.

**Primary action:** Sign in. **Secondary:** Create account; fill in the demo login (demo mode only).

## 2. Information hierarchy

1. The `Logo` (the `hope✳` wordmark from `components/hope/ui.tsx`), the one-line promise and `LanguageToggle`.
2. The active tab's form (email and password; name and invite code on sign-up).
3. The full-width submit button.
4. Small print: "Free for nonprofits." and, in demo mode, the demo-account hint.

Hidden: the password rule shows only on the sign-up tab. There is no "forgot password" link (out of scope).

## 3. Wireframe

Desktop (≥ 1024 px): a centred `Card` (`glass-panel`), 440 px wide, inside the root layout's `<main>`. There is no
`HopeNav` (the page is outside `/hope`).

```text
┌────────────────────────────────────────────────────────────────────────┐
│                     ┌──────────────────────────────────┐               │
│                     │ hope✳                      EN|ES │  <- Logo + LanguageToggle (light)
│                     │ Find grants that fit, and get a   │
│                     │ plain-English plan to apply.      │
│                     │ ┌──────────────┬───────────────┐  │  <- tabs (active = glass-active)
│                     │ │ ● Sign in    │ Create account│  │
│                     │ └──────────────┴───────────────┘  │
│                     │ Email                             │
│                     │ [ dana@riverbendhealth.org      ] │  <- TextField (glass-inset)
│                     │ Password                    [Show]│
│                     │ [ ••••••••••                    ] │
│                     │ [            Sign in            ] │  <- Button primary
│                     │ ─────────────────────────────────  │
│                     │ Demo: demo@hope.org / hope-demo   │  <- only when NEXT_PUBLIC_HOPE_DEMO=1
│                     │ [ Use the demo account ]          │  <- Button ghost
│                     │ Free for nonprofits.              │
│                     └──────────────────────────────────┘               │
└────────────────────────────────────────────────────────────────────────┘
```

The Create-account tab adds:
- "Your name" above Email
- the hint "At least 8 characters." under Password
- a required "Invite code" field under Password, with the hint "Ask your team for the invite code."

Its button reads "Create account".

Mobile (≤ 640 px): the card is full width with 16 px margins; same order.

## 4. Content inventory

| Element | Source | Format and example | Rules |
|---|---|---|---|
| Promise | `copy.ts` | "Find grants that fit, and get a plain-English plan to apply." | - |
| Tab | URL `tab` | "Sign in" / "Create account" | Default `signin`; an invalid value → `signin` |
| Your name | input → `display_name` | "Dana Okafor" | Sign-up only; required, 2-80 chars, trimmed |
| Email | input → `email` | "dana@riverbendhealth.org" | Required; `type="email"`; trimmed and lower-cased before sending |
| Password | input → `password` | masked, with a "Show"/"Hide" toggle | Required; sign-up needs ≥ 8 chars (mirrors H0's `weak_password`) |
| Invite code | input → `invite_code` | "Xq7m-3Kp9-Lw2v-8Tz4" | Sign-up only; required; trimmed; `autocomplete="off"` |
| Field errors | client checks or problem `code` | "Enter your email address." | Under the field, `role="alert"` on submit |
| Form error | problem `code` | "That email or password isn't right." | Above the button |
| Signed-out notice | URL `signedOut=1` | "You're signed out." | `SuccessNotice`; removed from the URL after render |
| Demo hint | `NEXT_PUBLIC_HOPE_DEMO === "1"` | "Demo: demo@hope.org / hope-demo" | The button fills both fields and focuses Sign in |

All copy lives in `app/login/copy.ts` as `{ en, es }` and is picked by `useI18n().locale`. It is kept local, so the
shared `lib/hope/i18n.ts` doesn't change.

## 5. Components

- From `components/ui` (no new styles):
  - `Card` (`glass-panel`)
  - `TextField` (`glass-inset`)
  - `Button`: `primary` for submit, full width; `ghost` for Show/Hide and the demo button
  - `ErrorNotice`, `SuccessNotice`, `Loading`
- `Logo` from `components/hope/ui.tsx` and `LanguageToggle` (`tone="light"`).
- The tabs are a small local `role="tablist"` built from two `Button`s; the active one gets `glass-active`.
- Files:
  - `app/login/page.tsx`: wraps `LoginScreen` in `Suspense`, `metadata.title` "Sign in · Hope"
  - `LoginScreen.tsx`
  - `copy.ts`
- The redirect target comes from H0's `safeNext(next)`. Don't write a second one.

## 6. Interactions

1. **Switch tab.** Click a tab, or use ←/→ on the tab list. This sets `?tab=` with `router.replace`, keeps the email, and clears errors.
2. **Sign in.** Client checks first (empty email or password). Then `login({email, password})` (H0: `POST /v1/auth/login`).
   While it runs, the button shows "Signing in…" and is disabled, and the fields are read-only.
   - 200 → `invalidateSession()`, then `me()` (H0: `GET /v1/me`). If `onboarding_complete` is false,
     `router.replace("/onboarding")`. Otherwise `router.replace(safeNext(next))`.
   - 401 `invalid_credentials` → form error; the password is cleared and focused.
   - 422 `validation_error` → field errors from `errors[]`.
   - 429 → "Too many attempts. Wait a minute and try again."
   - `ProblemError(0, "network_error")` or 5xx → "We couldn't reach Hope. Check your connection and try again."
3. **Create account.** Client checks first (name, email, password ≥ 8, invite code). Then
   `signup({email, password, display_name, invite_code})` (H0: `POST /v1/auth/signup`). The button shows "Creating account…".
   - 201 → `invalidateSession()`, `me()` → `/onboarding` when not onboarded (normal for the first user), else `safeNext(next)`.
   - 409 `email_taken` → a field error on Email with a "Sign in instead" link (switches tab, keeps the email).
   - 422 `weak_password` → a field error on Password.
   - 403 `signup_closed` → form error; focus moves to Invite code.
   - Network error or 5xx → same as sign-in.
4. **Show/Hide password.** Toggles `type`. The button has `aria-pressed`, and focus stays on the toggle.
5. **Use the demo account.** Fills `demo@hope.org` / `hope-demo` on the Sign-in tab and focuses "Sign in". It does
   not submit, so the presenter controls the moment.
6. **Already signed in.** On mount, call `me()`. A 200 redirects as in interaction 2. Show the loading state until
   `me()` settles, so the form doesn't flash.
7. **`safeNext(next)`** (H0) accepts only paths that start with `/` and not `//`. Anything else becomes `/hope/discover`.
8. **Keyboard.** Enter submits. The first field is focused on load and on each tab switch.

Code decides everything here; there is no model call.

## 7. States and exact copy

| State | EN | ES |
|---|---|---|
| Checking session (mount) | `Loading` "Checking your session…" | "Comprobando tu sesión…" |
| Submitting | "Signing in…" / "Creating account…" | "Iniciando sesión…" / "Creando cuenta…" |
| Empty email | "Enter your email address." | "Escribe tu correo electrónico." |
| Bad email format | "Enter an email like name@example.org." | "Escribe un correo como nombre@ejemplo.org." |
| Empty password | "Enter your password." | "Escribe tu contraseña." |
| Short password (sign-up) | "Use at least 8 characters." | "Usa al menos 8 caracteres." |
| Empty name (sign-up) | "Enter your name." | "Escribe tu nombre." |
| Empty invite code (sign-up) | "Enter your team's invite code." | "Escribe el código de invitación de tu equipo." |
| `invalid_credentials` | "That email or password isn't right." | "El correo o la contraseña no son correctos." |
| `email_taken` | "There's already an account with this email. Sign in instead?" | "Ya existe una cuenta con este correo. ¿Quieres iniciar sesión?" |
| `weak_password` | "Use at least 8 characters." | "Usa al menos 8 caracteres." |
| `signup_closed` | "That invite code isn't right. Ask your team for the current code." | "Ese código de invitación no es correcto. Pide a tu equipo el código actual." |
| Rate limited | "Too many attempts. Wait a minute and try again." | "Demasiados intentos. Espera un minuto e inténtalo de nuevo." |
| Network / 5xx | "We couldn't reach Hope. Check your connection and try again." | "No pudimos conectar con Hope. Revisa tu conexión e inténtalo de nuevo." |
| Signed out | "You're signed out." | "Cerraste sesión." |
| Offline (`navigator.onLine` false) | "You're offline. Connect to sign in." (button disabled) | "Estás sin conexión. Conéctate para iniciar sesión." |

## 8. Data and endpoints

| Trigger | Call | Fields used | Cache / refetch |
|---|---|---|---|
| Mount | H0 `me()` → `GET /v1/me` | 200: `onboarding_complete`; 401 → show the form | none |
| Sign in | H0 `login()` → `POST /v1/auth/login` (`contracts/mocks/w1/auth.login/request.json`) | 200 `{user}`; problem `code` | sets the cookie |
| Create account | H0 `signup()` → `POST /v1/auth/signup` (`.../auth.signup/request.json`) | 201 `{user}`; problem `code`, `errors[]` | sets the cookie |
| After either | `GET /v1/me` | `onboarding_complete` | - |

Without `NEXT_PUBLIC_HOPE_API_URL`, sync and the guard are off (H0), and nothing links to `/login`. If someone opens it
anyway, it shows the form, and a submit shows the network copy. Tests always mock `api/session`.

## 9. Responsive behaviour

- ≥ 641 px: the 440 px card, centred.
- ≤ 640 px: a full-width card, top-aligned with a 24 px top margin; buttons are 48 px tall.

## 10. Accessibility

- The `h1` is "Sign in to Hope" / "Create your Hope account" (visually hidden next to the wordmark). It updates with the tab.
- The tabs follow the ARIA tabs pattern (`role="tablist"`, arrow keys, `aria-selected`).
- Inputs have visible labels and `autocomplete` (`email`, `current-password` / `new-password`, `name`).
- Field errors are linked with `aria-describedby`. When a submit fails, focus moves to the first invalid field or to the form error (`role="alert"`).
- Liquid glass:
  - Text sits only on `glass-panel` / `glass-chrome`, never on `glass-backdrop`.
  - Contrast is AA against the worst-case background.
  - Under `prefers-reduced-transparency: reduce` the panels render solid.
  - `prefers-reduced-motion` stops the shimmer.

## 11. Fixture data

`app/login` tests mock H0's `api/session` module with Vitest:
- `login`: `demo@hope.org` / `hope-demo` → user Dana Okafor; anything else → `ProblemError(401, "invalid_credentials", …)`.
- `invalidateSession`: a spy; `safeNext`: the real H0 function.
- `signup`:
  - `taken@hope.org` → 409 `email_taken`
  - password `short` → 422 `weak_password`
  - any invite code other than `Xq7m-3Kp9-Lw2v-8Tz4` → 403 `signup_closed`
  - otherwise 201
- `me`: switchable between 401, `{onboarding_complete: false}` and `{onboarding_complete: true}`, shaped like `contracts/mocks/w1/me.get/*`.
- A `network` switch throws `ProblemError(0, "network_error", …)`, as H0's `apiFetch` does.

## 12. Analytics and success measures

No analytics in the hackathon. Success: from sign-up to a finished onboarding in under 5 minutes.

## 13. Acceptance criteria

- [ ] AC1 Signing in with valid credentials calls `invalidateSession()` and goes to `safeNext(next)` (or `/hope/discover`); a user who hasn't onboarded goes to `/onboarding`.
- [ ] AC2 `invalid_credentials` shows the exact copy, and clears and focuses the password.
- [ ] AC3 Create account sends `display_name`, `email`, `password` and `invite_code`, then goes to `/onboarding`.
- [ ] AC4 `email_taken` shows the field error; "Sign in instead" switches tabs and keeps the email.
- [ ] AC5 Client validation messages match section 7 and block the request.
- [ ] AC6 `?tab=signup` opens the create-account tab; switching tabs updates the URL.
- [ ] AC7 A visitor who is already signed in is redirected without seeing the form.
- [ ] AC8 An unsafe `next` (`https://evil.example`, `//x`) falls back to `/hope/discover` (through `safeNext`).
- [ ] AC9 Demo mode shows the hint and fills the fields; without demo mode the hint is hidden.
- [ ] AC10 `?signedOut=1` shows "You're signed out."
- [ ] AC11 A network failure shows the network copy.
- [ ] AC12 `signup_closed` shows the exact copy and focuses Invite code.
- [ ] AC13 With the ES locale cookie, every string in section 7 renders in Spanish.
- [ ] AC14 The page uses only `components/ui`, `Logo` and `LanguageToggle`; `app/globals.css` is unchanged.

## 14. Test plan

| AC | Test (file::name) |
|---|---|
| AC1 | `apps/web/app/login/LoginScreen.test.tsx::sign in redirects by onboarding state` |
| AC2 | `LoginScreen.test.tsx::invalid credentials` |
| AC3 | `LoginScreen.test.tsx::create account goes to onboarding` |
| AC4 | `LoginScreen.test.tsx::email taken offers sign in` |
| AC5 | `LoginScreen.test.tsx::client validation copy` |
| AC6 | `LoginScreen.test.tsx::tabs sync with url` |
| AC7 | `LoginScreen.test.tsx::redirects when already signed in` |
| AC8 | `LoginScreen.test.tsx::unsafe next falls back to discover` |
| AC9 | `LoginScreen.test.tsx::demo hint fills credentials` |
| AC10 | `LoginScreen.test.tsx::signed out notice` |
| AC11 | `LoginScreen.test.tsx::network error copy` |
| AC12 | `LoginScreen.test.tsx::signup closed asks for invite code` |
| AC13 | `LoginScreen.test.tsx::renders spanish copy` |
| AC14 | reviewer check: `git diff main -- apps/web/app/globals.css apps/web/components/ui` is empty |

## 15. Open questions

- Forgot password? Recommended default: no link in the hackathon (Hope sends no email).
- Sign-up is invite-only (decided; H0 section 1, H1 D1).
