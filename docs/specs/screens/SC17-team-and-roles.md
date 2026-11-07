# SC17: Team, roles and settings

| | |
|---|---|
| Route | `/settings/team` |
| Feature folder | `apps/web/src/features/session/` |
| Built by | [S01](../features/S01-sign-in-users-and-roles.md) |
| Roles | `org_admin` can see and act. Other users get the permission-denied state (and the nav entry is hidden, A8). |
| Status | Draft |

## Purpose

The org admin invites teammates, assigns the roles that HITL gates route to, and deactivates
people who leave. Gates can't be approved unless someone holds the role, so this screen also
shows which gate roles nobody holds.

## Layout

1. `PageHeader` "Team and roles", description "Invite people and choose what they can approve.",
   actions: primary `Button` "Invite person".
2. **Coverage strip:** `Card` (`neu-raised`) listing each gate role with the gates it unlocks:
   `development_director` (HITL-1, eligibility review), `finance_director` (HITL-2, HITL-0),
   `compliance_officer` (HITL-3), `executive_director` (HITL-4), `aor` (HITL-5), `org_admin` (HITL-0).
   Each role shows a `Badge`: `good`/`check` "{n} people", or `warn`/`alert` "Nobody". Gate names come
   from `GATES[gate].title` (`apps/web/src/lib/gates.ts`), and role names from `roleLabel`
   (`apps/web/src/features/status.tsx`).
3. **Filter:** `Segmented` "Active / Invited / Deactivated / All" (default "Active").
4. **Team table:** `Table` with caption "Team members", columns Name (and email below it), Roles
   (one `Badge` `neutral` per role), Status (`Badge`: active `good`/`check`, invited `info`/`clock`,
   deactivated `neutral`/`minus`), Last seen (relative time, "Never" if null), and Actions ("Edit roles"
   and "Deactivate" or "Reactivate" `Button`s, `ghost`).
5. **Invite dialog** (`Modal`): `TextField` Email, `TextField` Name, a role checkbox group (one
   checkbox per `Role`, each with a one-line description), and Cancel / "Send invite" buttons.
6. **Edit roles dialog** (`Modal`): the same checkbox group, pre-filled, with Cancel / "Save roles".
7. **Deactivate confirm** (`Modal`): "Deactivate {name}? They lose access on their next request.
   Their past approvals stay in the audit trail." Cancel / danger "Deactivate".

Mobile (<= 640 px): the coverage strip becomes a vertical list; the table becomes stacked cards
(one per user, actions in a row at the bottom), and dialogs become full-screen `drawer` variants.

## Data and endpoints

| Trigger | Call | Uses |
|---|---|---|
| Mount, and after each successful write | `GET /v1/users` (no filter; the filter is applied client-side) | all user fields |
| Send invite | `POST /v1/users` `{email, display_name, roles}` | returned user |
| Save roles | `PATCH /v1/users/{user_id}` `{roles}` with `If-Match: "{version}"` | returned user, `ETag` |
| Deactivate / Reactivate | `PATCH /v1/users/{user_id}` `{status}` with `If-Match` | returned user |
| Shell (already loaded) | `GET /v1/me` | `user_id` (to disable "Deactivate" on yourself), `roles` |

Shapes are exactly those in S01. The users list isn't cached across navigations; it reloads on mount.

## Interactions

1. **Invite person** opens the invite dialog with focus on Email. "Send invite" is disabled until
   the email is valid and at least one role is checked. While pending the button reads "Sending…".
   - 201: close, show `SuccessNotice` "Invite sent to {email}. They can sign in once they use that
     email with your identity provider.", then reload the list.
   - 409 `user_exists`: inline error on Email, "{email} is already on the team. Reactivate them instead."
   - 422 `unknown_role` / `validation_error`: inline error with the Problem `detail`.
2. **Edit roles** opens the dialog. Saving with no change closes it without a request.
   - 200: close and update the row in place.
   - 409 `last_admin`: dialog error "At least one active person must keep the Org admin role."
   - 412 `version_conflict`: dialog error "Someone else changed this person. We reloaded their
     latest roles; check them and save again." The dialog reloads the user from a fresh `GET /v1/users`.
3. **Deactivate** opens the confirm dialog. It's disabled for your own row (tooltip "You can't
   deactivate yourself").
   - 200: the row moves to Deactivated; `SuccessNotice` "{name} was deactivated."
   - 409 `last_admin` / `cannot_deactivate_self`: error in the dialog with that message.
4. **Reactivate** (deactivated rows): no confirm. PATCH `{status: "active"}`. An `invited` row has
   no Reactivate button (it never had an IdP binding).
5. Any 403 `forbidden` on a write (for example your own admin role was removed in another tab)
   switches the whole screen to the permission-denied state.

## States

- **Loading:** `Loading` "Loading your team…".
- **Empty** (the filter matches nobody): `EmptyState` "No {filter} people." The team itself is
  never empty because the viewer is an admin.
- **Error** on load: `ErrorNotice` "Couldn't load the team" with Retry.
- **Permission denied** (viewer lacks `org_admin`, or 403): `EmptyState` with the `lock` icon:
  "Only an Org admin can manage the team. Ask {names of active org_admins if known, else "your administrator"}."
  No `GET /v1/users` call is made when `me.roles` lacks `org_admin`.
- **Stale:** the 412 handling above; there is no artifact hash on this screen.

## Accessibility

- Tab order: Invite button, coverage strip (read-only, not focusable), filter, table rows and actions.
- Dialogs trap focus (`Modal`), return focus to the button that opened them, and close on Escape.
- The role checkbox group is a `fieldset` with `legend` "Roles". Each checkbox has its description
  linked with `aria-describedby`.
- Status and coverage use icon plus text. A role with nobody reads "Nobody" (not only an amber colour).
- Action buttons have accessible names that include the person, e.g. "Edit roles for Sam Lee".
- `SuccessNotice` is `role="status"`; errors are `role="alert"`.

## Fixture data

`apps/web/src/api/session/fixture.ts` `listUsers()` returns five users:
Dana Okafor (`executive_director`, `aor`, `org_admin`, active, `version: 3`, the fixture session),
Sam Lee (`finance_director`, active), Priya Raman (`development_director`, `grant_writer`, active),
Jordan Ellis (`compliance_officer`, invited, `last_seen_at: null`), and Lee Park (`viewer`,
deactivated). In this data nobody holds `cfo`, so the strip shows "Nobody" for CFO. The fixture
implements `inviteUser`, `updateUser` (bumps `version`, enforces `last_admin` and
`cannot_deactivate_self`, and throws 412 if `If-Match` is not the current version) and `getMe()`
from SC01.

## Acceptance criteria

- [ ] SC17-AC1 An org admin sees the team table and coverage strip; a role nobody holds shows "Nobody" with the alert icon.
- [ ] SC17-AC2 A non-admin sees the permission-denied state, and `listUsers` is never called.
- [ ] SC17-AC3 An invite sends `{email, display_name, roles}`, shows the success notice and reloads; `user_exists` shows the inline email error.
- [ ] SC17-AC4 Edit roles sends PATCH with `If-Match` set to the row's `version`; `last_admin` and `version_conflict` show their messages; the 412 path reloads the user.
- [ ] SC17-AC5 Deactivate needs confirmation, is disabled on your own row, and moves the row to Deactivated on success.
- [ ] SC17-AC6 The filter shows the right rows and the empty state.
- [ ] SC17-AC7 Dialogs trap focus and return it to the opener; every action button's accessible name includes the person's name.

## Test plan

| AC | Test (file::name) |
|---|---|
| SC17-AC1 | `apps/web/src/features/session/TeamScreen.test.tsx::shows team and role coverage` |
| SC17-AC2 | `apps/web/src/features/session/TeamScreen.test.tsx::non-admin sees permission denied` |
| SC17-AC3 | `apps/web/src/features/session/TeamScreen.test.tsx::invites a person`, `::duplicate invite error` |
| SC17-AC4 | `apps/web/src/features/session/TeamScreen.test.tsx::edits roles with If-Match`, `::last admin and version conflict` |
| SC17-AC5 | `apps/web/src/features/session/TeamScreen.test.tsx::deactivates with confirmation` |
| SC17-AC6 | `apps/web/src/features/session/TeamScreen.test.tsx::filters by status` |
| SC17-AC7 | `apps/web/src/features/session/TeamScreen.test.tsx::dialog focus management` |

## Note on discovery schedules

`SCREENS.md` lists `GET/PUT /v1/sources/schedules` (S10) on this screen. S01 does not build that
section because S10 owns those endpoints and runs in the same wave. See "Catalog changes" in the
S01 report: the recommendation is a separate `/settings/sources` screen built by S10.
