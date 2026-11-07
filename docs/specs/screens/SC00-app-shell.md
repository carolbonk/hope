# SC00: App shell (layout, nav, session guard)

| | |
|---|---|
| Route | wraps every route; `/` redirects |
| Feature folder | `apps/web/components/AppShell.tsx`, `components/RequireSession.tsx`, `nav.ts` |
| Built by | H0 |
| Primary users | everyone, on every screen |
| Can act | any signed-in user |
| Status | Ready |

> **Aligned after PR #34/#35. This box is authoritative: where anything below disagrees (routes, `apps/web/src/...` paths, building a screen from scratch), this box wins.**
> - The UI already exists: the Hope frontend under `/hope/*` (zip port, liquid glass) plus SC11 `/onboarding`. Don't rebuild or restyle screens; keep `app/globals.css` and `features/onboarding/**` as they are.
> - `apps/web` has no `src/`: `app/`, `components/`, `lib/`, `features/`, `api/` sit at the package root, and `@/*` maps to `./*`.
> - Pages only call `useHope()` (`lib/hope/store.ts`) and `useOpportunities()` (`lib/hope/opportunities.ts`). A backend plugs in through its own adapter in `lib/hope/sync/<name>.ts`. Keep the hook signatures and don't edit pages for wiring.
> - The `/v1` contract in `contracts/` still holds for the backend. On the wire, money is `amount_minor` (integer) + ISO currency; the adapters convert to the UI's whole units.
> - **Built:** `app/hope/layout.tsx` + `HopeNav` (Discover, Saved, Deadlines, Our profile, EN/ES) and `HopeFooter`. The one thing left for H0 is the session guard; the nav stays as is.

## 1. Purpose and user goals

The frame around every screen. It answers three questions: where am I, where can I go next, and
am I signed in as the right person. It also guarantees that nobody sees an inner screen without a
session, and that nobody skips onboarding: Hope can't find grants without a profile.

## 2. Information hierarchy

1. The page content (the shell stays quiet).
2. Primary nav: **Grants** (the shortlist workflow is home), **Discover**, **Profile**.
3. The user menu (name, organization name, Sign out).

There's no tenant picker, no roles and no notification bell in the hackathon.

## 3. Wireframe

```text
Desktop (>= 1024 px)
┌──────────────┬───────────────────────────────────────────────────────────┐
│  ◉ Hope      │  <page title>                         (DS) Dana Smith ▾   │
│              │                                       Bright Futures Org  │
│  ▣ Grants  3 │───────────────────────────────────────────────────────────│
│  ⌕ Discover  │                                                           │
│  ☺ Profile   │                    page content                           │
│              │                                                           │
│              │                                                           │
│  (raised     │                                                           │
│   sidebar)   │                                                           │
└──────────────┴───────────────────────────────────────────────────────────┘
Mobile (<= 640 px): top bar with the logo and avatar; nav as a bottom tab bar (Grants, Discover, Profile).
```

## 4. Content inventory

| Element | Source | Format | Rules |
|---|---|---|---|
| Logo | static | "Hope" wordmark | Links to `/grants` |
| Nav items | `nav.ts` | icon + label | Active item uses `glass-active` and `aria-current="page"` |
| Grants count badge | `GET /v1/grants?status=new&limit=1` -> `counts.new` | "3" | Hidden at 0; caps at "99+" |
| User name + initials | `GET /v1/me` -> `display_name` | "Dana Smith", avatar "DS" | Truncated at 24 characters |
| Organization name | `GET /v1/profile` -> `form.basics.legal_name` | secondary text | Hidden until onboarding is done |

## 5. Components

The sidebar is a `Card` (`glass-panel`); nav items are `Button` variant `nav`; the user menu is a
`Drawer` on mobile and a popover menu on desktop; signing out shows a `Toast`.

## 6. Interactions

1. **Load any route.** Calls `GET /v1/me`.
   - 401 `not_signed_in` goes to `/login?next=<current path>`.
   - 200 with `onboarding_complete: false` goes to `/onboarding`. It never redirects away from `/login` or `/onboarding` themselves.
   - 200 renders the page.
2. **`/`** redirects to `/grants`.
3. **Sign out.** `POST /v1/auth/logout` returns 204, then it goes to `/login` with the toast "Signed out".
4. **Session expires mid-use.** Any API 401 triggers the same redirect, keeping `next`.
5. **Keyboard:** "Skip to content" is the first tab stop; `g` then `g`/`d`/`p` jumps to Grants, Discover or Profile.

## 7. States and exact copy

| State | What shows |
|---|---|
| Checking session | Full-page soft skeleton (sidebar + header blocks), no flash of content |
| API unreachable | Full-page "Hope can't reach the server. Check that `make demo` is running." + Retry |
| Signed out | Redirect (no message); `/login` shows "Please sign in to continue" when `next` is set |

## 8. Data and endpoints

| Trigger | Call | Fields | Cache |
|---|---|---|---|
| App load, window focus | `GET /v1/me` | `display_name`, `agency_id`, `onboarding_complete` | Session; refetch on focus |
| After `me` | `GET /v1/profile` | `form.basics.legal_name` | Session |
| After `me`, every 60 s | `GET /v1/grants?status=new&limit=1` | `counts.new` | 60 s |
| Sign out | `POST /v1/auth/logout` | - | Clears all caches |

## 9. Responsive behaviour

- >= 1024 px: fixed 240 px sidebar.
- 641-1023 px: an icon-only 72 px rail, with tooltips.
- <= 640 px: a top bar and a bottom tab bar.

## 10. Accessibility

- Landmarks: `<nav aria-label="Primary">`, `<main id="content">`.
- The badge reads "3 new grants".
- Focus returns to the main heading after route changes.
- `prefers-reduced-motion` disables transitions.

## 11. Fixture data

Session fixtures: signed out; signed in but not onboarded; signed in and onboarded with 0 new grants; signed in and onboarded with 120 new grants (shows "99+").

## 12. Analytics and success measures

Events: `session_started`, `signed_out`, `nav_clicked {to}`. Success: no route renders protected content without a session.

## 13. Acceptance criteria

- [ ] AC1 Without a session, every route except `/login` redirects to `/login?next=…`.
- [ ] AC2 A signed-in user who hasn't onboarded is redirected to `/onboarding` from every other route.
- [ ] AC3 `/` redirects to `/grants`; the active nav item has `aria-current`.
- [ ] AC4 The badge shows the new-grant count, is hidden at 0, and shows "99+" above 99.
- [ ] AC5 Sign out calls logout, clears caches, and lands on `/login` with the toast.
- [ ] AC6 The mobile layout shows the bottom tab bar.

## 14. Test plan

| AC | Test |
|---|---|
| AC1, AC2 | `components/RequireSession.test.tsx` |
| AC3, AC4, AC6 | `components/AppShell.test.tsx` |
| AC5 | `components/AppShell.test.tsx::sign out` |

## 15. Open questions

- None.
