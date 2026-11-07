# SC00: App shell (layout, nav, session guard)

| | |
|---|---|
| Route | wraps every `/hope/*` route (`app/hope/layout.tsx`); `/` and `/hope` redirect to `/hope/discover` |
| Feature folder | `apps/web/app/hope/layout.tsx`, `components/hope/ui.tsx` (`HopeNav`, `HopeFooter`), `api/session/RequireSession.tsx` |
| Built by | PR #34 (layout, nav, footer, EN/ES). H0 adds the session guard and Sign out |
| Primary users | everyone, on every `/hope/*` screen |
| Can act | anyone in offline mode; any signed-in user online |
| Status | Built, except the session guard and Sign out (H0) |

## 1. Purpose and user goals

The frame around every Hope screen. It answers: where am I, where can I go next, and (online) am I signed in.
Online, it also makes sure nobody sees a `/hope/*` screen without a session, and nobody skips onboarding:
Hope can't find grants without a profile. Offline (no API URL) it is exactly the PR #34 demo shell.

## 2. Information hierarchy

1. The page content (the shell stays quiet).
2. Primary nav: **Discover** (home), **Saved** (with the saved count), **Deadlines**, **Our profile**.
3. The EN/ES toggle, and online only the signed-in name with **Sign out**.
4. The deadline reminder strip (applications due within 14 days), when there is one.
5. The footer: "Demo data" and the browser-storage note.

There is no tenant picker, no roles, no notification bell and no new-grants badge in the hackathon.

## 3. Wireframe

```text
Any width (glass-chrome bar, max-w-6xl, wraps)
┌───────────────────────────────────────────────────────────────────────────────┐
│ hope✳     Discover  [Saved (2)]  Deadlines  Our profile      [EN|ES]           │
│                                                    online: Dana Okafor · Sign out │
│ ● Due soon: Bayfront Youth Fund (6d) · …                    (only when due ≤14 d) │
└───────────────────────────────────────────────────────────────────────────────┘
  page content
──────────────────────────────────────────────────────────────────────────────────
  Demo data · Saved in this browser only — …                          <footer right>

< 640 px: logo and toggle on the first row; the nav drops to its own full-width row and scrolls sideways.
```

## 4. Content inventory

| Element | Source | Format | Rules |
|---|---|---|---|
| Logo | static | "hope✳" | Links to `/hope/discover` |
| Nav items | `NAV` in `components/hope/ui.tsx`, labels `h.nav.*` (`lib/hope/i18n.ts`) | text pill | Active item: `bg-navy text-white` + `aria-current="page"`; Saved is also active on `/hope/applications/*` |
| Saved count | `useHope().state.decisions` (`decision === "saved"`) | "(2)" | Hidden at 0 |
| Language toggle | `LanguageToggle` (locale cookie) | EN / ES | Unchanged |
| Name | `useSession().me.display_name` (`GET /v1/me`) | "Dana Okafor" | Online and `ready` only; truncated at 24 characters |
| Sign out | `h.session.signOut` | text button | Online and `ready` only |
| Deadline reminder | `state.applications` (stage ≠ `ready`) × `useOpportunities()` | "Name (6d)" | Only deadlines within 14 days; links to `/hope/deadlines` |
| Footer | `h.demo`, `h.storageNote`, `h.look.footerR` | small text | Unchanged |

## 5. Components

Existing only: the `glass-chrome` bar and pills in `HopeNav`, `LanguageToggle`, and `Loading` / `ErrorNotice` from
`components/ui` for the guard states. Sign out uses the existing `btnSecondary` style. No new primitives, and no change
to `app/globals.css` or `components/ui/**`.

## 6. Interactions

1. **Load any `/hope/*` route, offline** (`NEXT_PUBLIC_HOPE_API_URL` unset): render the page. No request, no Sign out.
2. **Load any `/hope/*` route, online:** `RequireSession` reads `useSession()` (one cached `GET /v1/me`).
   - loading: the checking state (section 7), never a flash of page content;
   - 401 `not_signed_in`: `router.replace("/login?next=" + encodeURIComponent(path + search))`;
   - 200 with `onboarding_complete: false`: `router.replace("/onboarding")`;
   - 200 with `onboarding_complete: true`: render the page;
   - network error or 5xx: the unreachable state, with Retry.
3. **`/` and `/hope`** redirect to `/hope/discover` (built).
4. **Sign out (online):** `POST /v1/auth/logout` returns 204, then `invalidateSession()` and `router.replace("/login")`.
   On an error, stay and show "Couldn't sign out. Try again." `hope:state:v1` is never cleared.
5. **Session expires mid-use:** any `/v1` 401 dispatches `hope:unauthorized`; the guard redirects as in 2, keeping `next`.
6. **Window focus:** `me()` is refetched, so a sign-out in another tab is picked up.
7. `/login` and `/onboarding` are outside `app/hope/layout.tsx`, so the guard never redirects either to itself.

## 7. States and exact copy

Copy lives in `lib/hope/i18n.ts` (`en` and `es`, new keys under `session`).

| State | What shows (EN / ES) |
|---|---|
| Checking session (online) | `Loading` with `h.loading`: "Loading your workspace…" / "Cargando tu espacio…" |
| API unreachable | `ErrorNotice` title "Hope can't reach the server." / "Hope no puede conectarse al servidor."; body "Check that `make demo` is running, then try again." / "Revisa que `make demo` esté en marcha y vuelve a intentarlo."; Retry calls `retry()` |
| Signed out | Redirect only (SC01 shows its own message) |
| Not onboarded | Redirect only (SC11) |
| Sign-out failed | Inline under the button: "Couldn't sign out. Try again." / "No se pudo cerrar la sesión. Inténtalo de nuevo." |
| Offline | The PR #34 shell, unchanged |

## 8. Data and endpoints

| Trigger | Call | Fields | Cache |
|---|---|---|---|
| Mount (online), window focus | `GET /v1/me` | `display_name`, `onboarding_complete` | Module cache in `api/session`; `invalidateSession()` clears it |
| Sign out | `POST /v1/auth/logout` | - | Clears the session cache |

Mocks: `contracts/mocks/w1/me.get/{onboarded,not_onboarded,signed_out}.json`, `contracts/mocks/w1/auth.logout/ok.json`.
The shell calls no other endpoint. Model calls: none (all code).

## 9. Responsive behaviour

- ≥ 640 px (`sm`): logo, nav, toggle (and Sign out) on one wrapping row.
- < 640 px: the nav takes its own full-width row (`order-3 w-full overflow-x-auto`), pills scroll sideways, and every
  target stays at least 44 px tall.

## 10. Accessibility

- `<nav aria-label="Hope">` (`h.brand`); the active link has `aria-current="page"`; all links use the gold `focusRing`.
- The checking state is `role="status"`; the unreachable state is `role="alert"`.
- Sign out is a `<button>`, reachable by keyboard right after the language toggle.
- The page stays in the root layout's `<main>`.

## 11. Fixture data

`me.get` scenarios `onboarded`, `not_onboarded`, `signed_out`; a fetch that rejects (unreachable); offline
(`NEXT_PUBLIC_HOPE_API_URL` unset). Browser state: an empty `hope:state:v1` and one with 2 saved decisions.

## 12. Analytics and success measures

None in the hackathon. Success: online, no `/hope/*` route renders page content without a session; offline, nothing changes.

## 13. Acceptance criteria

- [ ] AC1 Offline, every `/hope/*` route renders with no `/v1` request and no Sign out.
- [ ] AC2 Online without a session, every `/hope/*` route redirects to `/login?next=<path>`, and no page content renders first.
- [ ] AC3 Online, a signed-in user who hasn't onboarded is redirected to `/onboarding`.
- [ ] AC4 A `/v1` 401 after load redirects to `/login` with `next`; an unreachable API shows the exact copy and Retry refetches.
- [ ] AC5 Sign out calls logout, clears the session cache, keeps `hope:state:v1` and lands on `/login`; a failure shows the exact copy.
- [ ] AC6 The nav is unchanged: four items, the active item has `aria-current`, the Saved count is hidden at 0, and `/` lands on `/hope/discover`.

## 14. Test plan (Vitest, offline)

| AC | Test |
|---|---|
| AC1-AC4 | `api/session/RequireSession.test.tsx` (mocks `fetch` with the `contracts/mocks/w1` bodies; offline case stubs `NEXT_PUBLIC_HOPE_API_URL` empty) |
| AC4 | `api/http.test.ts` (problem parsing, `network_error`, the `hope:unauthorized` event) |
| AC5, AC6 | `components/hope/ui.test.tsx` (`HopeNav` offline/online, sign out ok and failed, active item, saved count) |

## 15. Open questions

- The footer note says "no real sign-in" even online. Recommended default: keep it for the hackathon, since all
  application data is still browser-only.
