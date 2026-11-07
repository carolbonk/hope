# SC01: Sign-in

| | |
|---|---|
| Route | `/login` (also handles the IdP redirect: `/login?code=...&state=...`) |
| Feature folder | `apps/web/src/features/session/` |
| Built by | [S01](../features/S01-sign-in-users-and-roles.md) |
| Roles | Public (no session needed). Everyone who is invited can sign in. |
| Status | Draft |

## Purpose

Staff of the organization sign in with their identity provider and land on the screen they were
trying to reach. The screen also explains why sign-in failed (not invited, deactivated, IdP down).

## Layout

The app shell header is hidden on this route (`nav.ts` marks `/login` as `public`, A8).

1. Centred `Card` (`neu-raised`, max width 28rem) containing:
   - Hope logo mark (the `neu-inset` "H" from `AppShell`) and heading "Sign in to Hope".
   - The organization name if known (`NEXT_PUBLIC_HOPE_ORG_NAME`, optional), else no subtitle.
   - Primary `Button` "Continue with {NEXT_PUBLIC_HOPE_OIDC_PROVIDER_NAME}" (default label "Continue with your organization account").
   - A notice region (`ErrorNotice`, or `SuccessNotice` after sign-out) below the button.
   - Small print: "Hope is free for nonprofits. Trouble signing in? Ask your Hope administrator."
2. In dev mode (`NEXT_PUBLIC_HOPE_AUTH_MODE=dev`) the button is replaced by a `Well` (`neu-inset`)
   that reads "Development mode: you are signed in as {NEXT_PUBLIC_HOPE_USER_ID}", with a
   "Continue" button.

Mobile (<= 640 px): the card fills the width with 16 px margins, and the button is full width.

## Data and endpoints

| Trigger | Call | Uses |
|---|---|---|
| Click "Continue" (oidc) | Browser redirect to `{issuer}/authorize` with `response_type=code`, `client_id`, `redirect_uri={origin}/login`, `scope=openid email profile`, `state`, `code_challenge` (S256), and `nonce` | - |
| Page load with `code` and `state` | `POST {token_endpoint}` (code + verifier), then `GET /v1/me` with the new access token | `user_id`, `display_name`, `roles`, `agency` |
| Page load without `code` | none (no `GET /v1/me` until the user clicks) | - |

The issuer metadata comes from `{NEXT_PUBLIC_HOPE_OIDC_ISSUER}/.well-known/openid-configuration`
and is fetched once per page load. `GET /v1/me` returns the shape in S01 (`MeResponse` in
`apps/web/src/api/session/types.ts`).

## Interactions

1. **Continue:** generate the `state`, `nonce` and PKCE verifier, store them in `sessionStorage`
   under `hope.oidc.pending` together with `returnTo` (the `?returnTo=` query value, which must be
   a same-origin path starting with `/`; anything else becomes `/`). The button shows a pending
   state ("Redirecting…") and is disabled.
2. **Callback:** if `state` doesn't match `hope.oidc.pending.state` -> error "Sign-in expired or
   was started in another tab. Try again." and clear the pending entry. Otherwise exchange the code,
   keep the tokens in memory (`lib/auth.ts`, A7), clear the pending entry, remove `code` and `state`
   from the URL (`history.replaceState`), then call `GET /v1/me`:
   - 200 with `agency: null` -> `router.replace("/onboarding")`.
   - 200 -> `router.replace(returnTo)`.
   - 403 `not_invited` -> "Your account ({email from the ID token}) hasn't been invited to Hope.
     Ask your Hope administrator to invite this email address."
   - 403 `user_deactivated` -> "Your Hope access has been turned off. Contact your administrator."
   - 401 `invalid_token` -> "We couldn't verify your sign-in. Try again."
   - 503 `idp_unavailable` or a network error -> "The sign-in service is unavailable right now." with a Retry button.
3. **Token exchange error** (`error` query param from the IdP, e.g. `access_denied`) -> show the IdP's
   `error_description` if present, else "Sign-in was cancelled."
4. **Step-up:** other screens call `requestStepUp(returnTo)` from `features/session/oidc.ts`, which redirects with
   `prompt=login`, `max_age=0` and `acr_values` (if `NEXT_PUBLIC_HOPE_OIDC_MFA_ACR` is set). The
   callback is handled the same way, and the user returns to `returnTo` with a fresh `mfa: true` token.
5. **Sign out** (user menu in the shell): clear the in-memory tokens and redirect to the IdP
   `end_session_endpoint` if it has one, with `post_logout_redirect_uri={origin}/login?signed_out=1`.
   The login page then shows `SuccessNotice` "You're signed out."
6. Any API 401 anywhere in the app calls the `onUnauthenticated` handler (A7), which redirects to
   `/login?returnTo=<current path>`.

## States

- **Idle:** the card with the button.
- **Redirecting:** button disabled with "Redirecting…" (`aria-busy="true"`).
- **Completing sign-in:** `Loading` "Signing you in…" (the same label as `SessionProvider`).
- **Error:** `ErrorNotice` with the message for the code, plus a "Try again" button that restarts at step 1.
- **Signed out:** `SuccessNotice`.
- **Misconfigured** (oidc mode with no issuer or client id): `ErrorNotice` "Sign-in isn't configured
  for this deployment." with no button.
- There is no empty, permission-denied or stale-artifact state on this screen.

## Accessibility

- The page `<h1>` is "Sign in to Hope". On load, focus is on the primary button; after an error,
  focus moves to the notice (`role="alert"`).
- The pending state uses `aria-busy` and keeps the button label readable (not only a spinner).
- Error notices use the `alert` icon plus text, not colour alone.
- Contrast is WCAG AA, and focus rings use `neu-focus`.
- No animation except the `Loading` indicator, which respects `prefers-reduced-motion`.

## Fixture data

`apps/web/src/api/session/fixture.ts`: `getMe()` returns
`{user_id: "u-dana", email: "dana@example.org", display_name: "Dana Okafor", roles: ["executive_director", "development_director", "finance_director", "compliance_officer", "aor", "org_admin"], mfa: false, auth_mode: "dev", agency: {agency_id: FIXTURE_AGENCY_ID, legal_name: "Riverside Family Services"}}`.
With no API URL configured the login page shows the dev-mode card. Tests inject a fake OIDC
client (`features/session/oidc.ts` exports `createOidcClient(deps)` with `fetch`, `crypto` and
`location` injected).

## Acceptance criteria

- [ ] SC01-AC1 Clicking Continue stores state, nonce and verifier and redirects to the authorize URL with an S256 `code_challenge` and the configured `redirect_uri`.
- [ ] SC01-AC2 A callback with a mismatched `state` shows the expired-sign-in error and never calls the token endpoint.
- [ ] SC01-AC3 A successful callback calls `GET /v1/me`, removes `code` and `state` from the URL and navigates to `returnTo`; an off-site `returnTo` becomes `/`.
- [ ] SC01-AC4 `agency: null` navigates to `/onboarding`.
- [ ] SC01-AC5 `not_invited`, `user_deactivated`, `invalid_token` and `idp_unavailable` each show their message in a focused `role="alert"` region.
- [ ] SC01-AC6 Dev mode shows the dev card and no IdP button.
- [ ] SC01-AC7 `?signed_out=1` shows "You're signed out."
- [ ] SC01-AC8 An API 401 on another screen redirects to `/login?returnTo=<path>`.

## Test plan

| AC | Test (file::name) |
|---|---|
| SC01-AC1 | `apps/web/src/features/session/LoginScreen.test.tsx::redirects with PKCE` |
| SC01-AC2 | `apps/web/src/features/session/LoginScreen.test.tsx::rejects mismatched state` |
| SC01-AC3 | `apps/web/src/features/session/LoginScreen.test.tsx::completes sign-in and returns` |
| SC01-AC4 | `apps/web/src/features/session/LoginScreen.test.tsx::sends users without an agency to onboarding` |
| SC01-AC5 | `apps/web/src/features/session/LoginScreen.test.tsx::shows each sign-in error` |
| SC01-AC6 | `apps/web/src/features/session/LoginScreen.test.tsx::dev mode card` |
| SC01-AC7 | `apps/web/src/features/session/LoginScreen.test.tsx::signed out notice` |
| SC01-AC8 | `apps/web/src/features/session/oidc.test.ts::401 redirects to login` |
