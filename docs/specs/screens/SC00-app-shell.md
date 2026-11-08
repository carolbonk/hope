# SC00: App shell (layout, nav, session guard)

| | |
|---|---|
| Route | wraps every `/hope/*` route (`app/hope/layout.tsx`); `/` and `/hope` redirect to `/hope/discover` |
| Feature folder | `apps/web/app/hope/layout.tsx`, `components/hope/ui.tsx` (`HopeNav`, `HopeFooter`), `api/session/RequireSession.tsx` |
| Built by | PR #34 (layout, footer, EN/ES), #38 H0 (session guard, Sign out), #40 (5 s notices, glass nav), #42 (journey order, account menu) |
| Primary users | everyone, on every `/hope/*` screen |
| Can act | anyone in offline mode; any signed-in user online |
| Status | Built |

## 1. Purpose and user goals

The frame around every Hope screen. It answers: where am I, where can I go next, and (online) am I signed in.
Online, it also makes sure nobody sees a `/hope/*` screen without a session, and nobody skips onboarding:
Hope can't find grants without a profile. Offline (no API URL) it is exactly the PR #34 demo shell.

## 2. Information hierarchy

1. The page content (the shell stays quiet).
2. Primary nav in journey order (find → shortlist → meet deadlines): **Discover** (home), **Saved** (with the saved
   count), **Deadlines**.
3. On the right: the EN/ES toggle and the **account menu** (Our profile; online also the signed-in name and **Sign out**).
   The profile is set up once in onboarding, so it lives in the menu, not among the daily links.
4. The deadline reminder strip (applications due within 14 days), with a × close button. It auto-dismisses after 5 s.
5. The footer: "Demo data" and the browser-storage note.

There is no tenant picker, no roles, no notification bell and no new-grants badge in the hackathon.

## 3. Wireframe

```text
Any width (glass-nav bar: 35% white + blur, max-w-6xl, wraps)
┌───────────────────────────────────────────────────────────────────────────────┐
│ hope✳        Discover  [Saved (2)]  Deadlines          [EN|ES] [👤 Dana Okafor ▾] │
│                                                         ┌ account menu ──────┐ │
│                                                         │ Our profile        │ │
│                                                         │ Sign out (online)  │ │
│                                                         └────────────────────┘ │
│ ● Due soon: Youth Mentoring Grants (6d) · …          [×]   (only when due ≤14 d) │
└───────────────────────────────────────────────────────────────────────────────┘
  page content
──────────────────────────────────────────────────────────────────────────────────
  Demo data · Saved in this browser only — …                          <footer right>

< 640 px: logo, toggle and the account menu (icon only) on the first row; the nav drops to its own full-width row and scrolls sideways.
```

## 4. Content inventory

| Element | Source | Format | Rules |
|---|---|---|---|
| Logo | static | "hope✳" | Links to `/hope/discover` |
| Nav items | `NAV` in `components/hope/ui.tsx` (discover, saved, deadlines), labels `h.nav.*` (`lib/hope/i18n.ts`) | text pill | Active item: `aria-current="page"`, white text on one navy pill that slides between items (`NavLinks`); Saved is also active on `/hope/applications/*` |
| Saved count | `useHope().state.decisions` (`decision === "saved"`) | "(2)" | Hidden at 0 |
| Language toggle | `LanguageToggle` (locale cookie) | EN / ES | Unchanged |
| Account menu button | `AccountMenu`; label `useSession().me.display_name` (`GET /v1/me`) online, else `h.session.account` | "Dana Okafor" / "Account" | Name truncated at 24 characters; screen-reader only below `sm`; navy while on `/hope/profile` |
| Menu: Our profile | `h.nav.profile` | link | Always; goes to `/hope/profile` |
| Menu: Sign out | `h.session.signOut` | button | Online and `ready` only (`OnlineAccount`) |
| Deadline reminder | `state.applications` (stage ≠ `ready`) × `useOpportunities()` | "Name (6d)" + × | Only deadlines within 14 days; the text links to `/hope/deadlines`; × (`h.dismiss`) hides it until reload; `AutoDismiss` removes it after 5 s |
| Footer | `h.demo`, `h.storageNote`, `h.look.footerR` | small text | Unchanged |

## 5. Components

The `glass-nav` bar (`app/globals.css`: `--glass-fill-nav` 35% white + `--glass-blur`), `NavLinks` (sliding pill),
`AccountMenu` / `OnlineAccount` (popover with `animate-pop-in`), `LanguageToggle`, `AutoDismiss` for the reminder and
the sign-out error, and `Loading` / `ErrorNotice` from `components/ui` for the guard states. All in `components/hope/ui.tsx`.

## 6. Interactions

1. **Load any `/hope/*` route, offline** (`NEXT_PUBLIC_HOPE_API_URL` unset): render the page. No request, no Sign out.
2. **Load any `/hope/*` route, online:** `RequireSession` reads `useSession()` (one cached `GET /v1/me`).
   - loading: the checking state (section 7), never a flash of page content;
   - 401 `not_signed_in`: `router.replace("/login?next=" + encodeURIComponent(path + search))`;
   - 200 with `onboarding_complete: false`: `router.replace("/onboarding")`;
   - 200 with `onboarding_complete: true`: render the page;
   - network error or 5xx: the unreachable state, with Retry.
3. **`/` and `/hope`** redirect to `/hope/discover` (built).
4. **Account menu:** the button toggles the popover (`aria-expanded`). Opening focuses the first item; Esc closes and
   returns focus to the button; an outside click or choosing an item closes it.
5. **Sign out (online, in the menu):** `POST /v1/auth/logout` returns 204, then `invalidateSession()` and
   `router.replace("/login")`. On an error, stay and show "Couldn't sign out. Try again." `hope:state:v1` is never cleared.
6. **Deadline reminder:** clicking the text opens `/hope/deadlines`; × closes it without navigating.
7. **Session expires mid-use:** any `/v1` 401 dispatches `hope:unauthorized`; the guard redirects as in 2, keeping `next`.
8. **Window focus:** `me()` is refetched, so a sign-out in another tab is picked up.
9. `/login` and `/onboarding` are outside `app/hope/layout.tsx`, so the guard never redirects either to itself.

## 7. States and exact copy

Copy lives in `lib/hope/i18n.ts` (`en` and `es`, new keys under `session`).

| State | What shows (EN / ES) |
|---|---|
| Checking session (online) | `Loading` with `h.loading`: "Loading your workspace…" / "Cargando tu espacio…" |
| API unreachable | `ErrorNotice` title "Hope can't reach the server." / "Hope no puede conectarse al servidor."; body "Check that `make demo` is running, then try again." / "Revisa que `make demo` esté en marcha y vuelve a intentarlo."; Retry calls `retry()` |
| Signed out | Redirect only (SC01 shows its own message) |
| Not onboarded | Redirect only (SC11) |
| Sign-out failed | Under the account menu for at most 5 s (`AutoDismiss`): "Couldn't sign out. Try again." / "No se pudo cerrar la sesión. Inténtalo de nuevo." |
| Offline | The PR #34 shell, unchanged |

## 8. Data and endpoints

| Trigger | Call | Fields | Cache |
|---|---|---|---|
| Mount (online), window focus | `GET /v1/me` | `display_name`, `onboarding_complete` | Module cache in `api/session`; `invalidateSession()` clears it |
| Sign out | `POST /v1/auth/logout` | - | Clears the session cache |

Mocks: `contracts/mocks/w1/me.get/{onboarded,not_onboarded,signed_out}.json`, `contracts/mocks/w1/auth.logout/ok.json`.
The shell calls no other endpoint. Model calls: none (all code).

## 9. Responsive behaviour

- ≥ 640 px (`sm`): logo, nav, toggle and account menu on one wrapping row.
- < 640 px: the nav takes its own full-width row (`order-3 w-full overflow-x-auto`), pills scroll sideways, and every
  target stays at least 44 px tall.

## 10. Accessibility

- `<nav aria-label="Hope">` (`h.brand`); the active link has `aria-current="page"`; all links use the gold `focusRing`.
- The checking state is `role="status"`; the unreachable state is `role="alert"`.
- The account menu is a disclosure `<button>` (`aria-haspopup`, `aria-expanded`, `aria-controls`) right after the
  language toggle; Sign out is a `<button>` inside it. The reminder's × has `aria-label` "Dismiss notification".
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
- [ ] AC6 The nav has three items in journey order (Discover, Saved, Deadlines), the active item has `aria-current`, the Saved count is hidden at 0, Our profile is only in the account menu, and `/` lands on `/hope/discover`.
- [ ] AC7 The account menu opens with focus on its first item and Esc closes it and returns focus; the reminder and every notice are gone after 5 s.

## 14. Test plan (Vitest, offline)

| AC | Test |
|---|---|
| AC1-AC4 | `api/session/RequireSession.test.tsx` (mocks `fetch` with the `contracts/mocks/w1` bodies; offline case stubs `NEXT_PUBLIC_HOPE_API_URL` empty) |
| AC4 | `api/http.test.ts` (problem parsing, `network_error`, the `hope:unauthorized` event) |
| AC5-AC7 | `components/hope/ui.test.tsx` (`HopeNav` offline/online, link order, account menu focus/Esc, sign out ok and failed) and `components/ui/AutoDismiss.test.tsx` (5 s removal) |

## 15. Open questions

- The footer note says "no real sign-in" even online. Recommended default: keep it for the hackathon, since all
  application data is still browser-only.
