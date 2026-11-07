# S01: Sign-in, users, roles and `/v1/me` (single tenant)

> **Out of scope for the hackathon. Don't build this.** This spec belongs to the earlier design (the Phase 1 pipeline and the M0-M7 / S-spec roadmap). Hackathon agents build only H0-H5 (see [`README.md`](../README.md)). Keep this file for after the hackathon.

| | |
|---|---|
| Wave | 1 |
| Depends on | S00 |
| Screens | [SC01](../screens/SC01-sign-in.md), [SC17](../screens/SC17-team-and-roles.md) |
| Migrations | `db/migrations/0110_users.sql` |
| Blueprint | 4.4 (approver roles, separation of duties), 6.2 (Identity: OIDC SSO), 8.4 (access control, step-up MFA, audit) |
| Status | Draft |

## Goal

People sign in to Hope with the organization's identity provider (OIDC), and every request
carries a verified user with platform roles. An org admin invites teammates and assigns the
roles that the HITL gates route to (finance director, compliance officer, AOR, and so on).
Without this, approvals are attributed to whatever `X-Hope-User` header the browser sends.

## Current state

On `main` after S00:

- `hope_core.auth.Principal` (`tenant_id: UUID`, `user_id: str`, `roles: frozenset[str]`,
  `mfa: bool`), `get_principal` and `require_roles(*roles)` (S00 step 5). `get_principal` sets
  `tenant_id` from `HopeSettings.tenant_id` (`HOPE_TENANT_ID`) and reads `X-Hope-User`,
  `X-Hope-Roles` and `X-Hope-MFA` headers. Nothing checks them, so any caller can claim any role.
- The pillar app factory `hope_pillar.api.create_app` mounts the empty routers `api/me.py` and
  `api/users.py` (S00 step 9).
- Gates check roles against `pillar_gate_requests.approver_roles` in `_lock_gate` (now in
  `services/pillar/src/hope_pillar/api/workflows.py` after the S00 split). Role strings in use
  today: `org_admin`, `development_director`, `finance_director`, `cfo`, `compliance_officer`,
  `executive_director`, `aor` (`hope_workflow.policy.GATES`, `hope_profile.validators.DEFAULT_HITL0_ROLES`),
  plus free-form roles from `AgencyProfile.approval_hierarchy[].approver_roles`
  (e.g. `board_treasurer` in `services/workflow/tests/test_lifecycle.py`).
- There is no `users` table. The web app has no sign-in; `HttpApi.getSession()`
  (`apps/web/src/api/http.ts`, moved to `apps/web/src/api/session/` by S00) fabricates a
  session from `NEXT_PUBLIC_HOPE_USER_ID` / `NEXT_PUBLIC_HOPE_ROLES`.
- `StepUpDialog` (`apps/web/src/features/approvals/StepUpDialog.tsx`) is a placeholder that
  accepts any 6 digits and sends `mfa-placeholder:<code>`.

## Behaviour

### Authentication modes

1. New settings class `hope_pillar.auth.settings.AuthSettings` (`HOPE_` prefix):
   - `auth_mode: Literal["oidc", "dev"] = "dev"`.
   - `oidc_issuer: str | None` (e.g. `https://login.example.org/`), `oidc_audience: str | None`
     (the API's client id / audience), `oidc_jwks_ttl_seconds: int = 3600`.
   - `oidc_mfa_amr: list[str] = ["mfa", "otp", "hwk", "swk"]` and
     `oidc_mfa_max_age_seconds: int = 600` (how fresh a step-up must be).
   - `oidc_roles_claim: str | None = None` (optional IdP groups claim, see Decision 3).
   - `bootstrap_admin_email: str | None` (see step 9).
   - `env: Literal["local", "test", "staging", "prod"] = "local"`. Startup fails with
     `RuntimeError("HOPE_AUTH_MODE=dev is not allowed in prod")` if `env == "prod"` and
     `auth_mode == "dev"`, or if `auth_mode == "oidc"` and issuer or audience is missing.
2. `hope_pillar.auth.install_auth(app)` is called by `create_app` (shared addition A1). In
   `oidc` mode it sets `app.dependency_overrides[hope_core.auth.get_principal] = oidc_principal`.
   In `dev` mode it leaves S00's header principal in place. Every router (pillar and the mounted
   profile router) therefore gets the verified principal without any route change.

### `oidc_principal` (every request)

3. Read `Authorization: Bearer <jwt>`. Missing or not `Bearer` -> 401 `unauthenticated`
   with header `WWW-Authenticate: Bearer`.
4. Verify the JWT with PyJWT against the issuer's JWKS (`{issuer}/.well-known/openid-configuration`
   -> `jwks_uri`, cached for `oidc_jwks_ttl_seconds`; an unknown `kid` forces one refetch).
   Required: `alg` in `RS256`/`ES256` (never `none` or `HS*`), `iss == oidc_issuer`,
   `aud` contains `oidc_audience`, `exp` in the future, `nbf`/`iat` not in the future (60 s
   leeway), `sub` present. Any failure -> 401 `invalid_token` (detail names the failed check,
   never echoes the token). JWKS fetch failure with no cached key -> 503 `idp_unavailable`.
5. Look up the user by `(idp_issuer, idp_subject)`. If there is none, look up an `invited` user whose
   `email` equals the token's `email` claim (case-insensitive) **and** `email_verified` is
   `true`; bind it (set `idp_issuer`, `idp_subject`, `status = 'active'`, `activated_at = now()`)
   and write audit `user.activated`. No match -> 403 `not_invited`.
6. `status = 'deactivated'` -> 403 `user_deactivated`.
7. Build `Principal(tenant_id=HOPE_TENANT_ID, user_id=str(users.user_id), roles=frozenset(users.roles),
   mfa=<step 8>)`. Roles always come from the `users` row, never from the token (unless
   Decision 3 changes this).
8. `mfa = True` only when the token's `amr` intersects `oidc_mfa_amr` **and**
   `now - auth_time <= oidc_mfa_max_age_seconds`. The existing gate checks
   (`STEP_UP_MFA_GATES` in `_lock_gate`) use this flag unchanged.
9. Bootstrap: on the first request in `oidc` mode, if the `users` table is empty and
   `bootstrap_admin_email` is set, insert that email as an `invited` user with roles
   `["org_admin"]` (`invited_by = "system:bootstrap"`). With an empty table and no bootstrap
   email, every sign-in returns 403 `not_invited`.
10. `last_seen_at` is updated at most once per 5 minutes per user (one `UPDATE ... WHERE
    last_seen_at < now() - interval '5 minutes'`), so reads stay cheap.

### Dev mode

11. `dev` mode keeps S00's header principal. `GET /v1/me` still works: if a `users` row with
    `user_id::text = X-Hope-User` exists it is used, otherwise a synthetic user is returned
    (`email: null`, `display_name` = the header value, `status: "active"`). Dev mode never writes
    `users` rows from headers.

### Users API

12. `GET /v1/me` (any signed-in user) returns the user, roles, the MFA flag, and the agency.
    The agency is the tenant's one agency: `SELECT agency_id, legal_name FROM agencies ORDER BY
    created_at LIMIT 1`. If there is none, `agency` is `null` (the web shell sends the user to
    `/onboarding`, SC11).
13. `GET /v1/users`, `POST /v1/users` and `PATCH /v1/users/{user_id}` require `org_admin`
    (`require_roles("org_admin")`, otherwise 403 `forbidden`).
14. Invite (`POST /v1/users`): email is normalized (trim, lowercase). Every role must be a
    `Role` value (shared addition A2), otherwise 422 `unknown_role`. An existing user with
    that email -> 409 `user_exists` (including deactivated users: reactivate them with PATCH).
    The user is inserted as `invited`, audit `user.invited` is written, and a
    `notification.requested` event (S00's `NotificationRequest`, `kind: "user_invited"`,
    `channels: ["email"]`, recipient = the invitee's email; see shared addition A5) goes
    through the outbox in the same transaction. Delivery is S12's job.
15. PATCH accepts `roles` and/or `status` (`active` | `deactivated`) and requires
    `If-Match: "<version>"` (the user's integer `version`). Missing -> 428 `precondition_required`;
    stale -> 412 `version_conflict`. Rules, checked in this order:
    - `status: "active"` on an `invited` user -> 422 `invalid_transition` (only sign-in activates).
    - Removing `org_admin` from, or deactivating, the last active `org_admin` -> 409 `last_admin`.
    - A user cannot deactivate themselves -> 409 `cannot_deactivate_self`.
    - Unknown role -> 422 `unknown_role`.
    Each change writes one audit row: `user.roles_changed` (`detail: {"before": [...], "after": [...]}`),
    `user.deactivated` or `user.reactivated`. A no-op PATCH returns 200 without an audit row.
16. Role changes take effect on the user's next request (roles are read per request). Open gate
    requests are not re-routed. Decisions already recorded keep the role they were made in
    (`HitlDecision.role`, S00).
17. Deactivating a user does not revoke IdP tokens; the next request returns 403 `user_deactivated`.

### Audit

18. Every write in this spec inserts into `audit_log` with the `write_audit` helper
    (shared addition A3), in the same transaction as the change: `actor` = acting user id
    (or `system:bootstrap`), `subject = "user:<user_id>"`.

## Contracts

- **Shared models used:** `hope_core.auth.Principal`, `get_principal`, `require_roles`;
  `hope_core.errors.Problem`, `Forbidden`, `NotFound`, `ConcurrencyError`;
  `hope_core.schemas.NotificationRequest` (moved from `hope_workflow.contracts` by S00).
- **Shared contract additions** (for the S00 batch; S01 cannot start without A1-A3):
  - **A1** `services/pillar/src/hope_pillar/auth/__init__.py` with
    `def install_auth(app: FastAPI) -> None: return None`, called by `create_app` after the
    routers are mounted. S01 owns the body of `hope_pillar/auth/**` from then on.
  - **A2** `hope_core.auth.Role(StrEnum)`: `org_admin`, `grant_writer`, `development_director`,
    `program_lead`, `finance_director`, `cfo`, `compliance_officer`, `executive_director`,
    `board_chair`, `aor`, `viewer`. Exported to `@hope/schemas` as a TS union. (`board_treasurer`
    in a workflow test becomes `board_chair`, or see Decision 2.)
  - **A3** `hope_core.audit.write_audit(cur, *, actor: str, action: str, subject: str, detail: dict[str, Any] | None = None) -> None`
    (one `INSERT INTO audit_log`; the trigger chains the hash). S13 and S03 use it too.
  - **A4** `hope_core.errors.Unauthorized(code="unauthenticated")` -> 401 with
    `WWW-Authenticate: Bearer`, and `PreconditionFailed` -> 412 `version_conflict`,
    `PreconditionRequired` -> 428 `precondition_required`.
  - **A5** `NotificationRequest.recipient_emails: list[str] = []` (invites go to someone who has no roles yet) and
    `NotificationKind` gains `"user_invited"`.
  - **A6** Dependency `pyjwt[crypto]>=2.9,<3` in `services/pillar/pyproject.toml` (+ `uv lock`).
  - **A7** Web: `apps/web/src/lib/auth.ts` with `getAccessToken(): string | null` and
    `onUnauthenticated(cb)`, which every per-feature `http.ts` uses to send `Authorization: Bearer`.
    It replaces the `X-Hope-User` / `X-Hope-Roles` headers when `NEXT_PUBLIC_HOPE_AUTH_MODE=oidc`.
    S01 fills in the implementation behind this interface in `features/session/oidc.ts`.
  - **A8** Web: `nav.ts` entries for `/login` (hidden from the nav, `public: true`) and
    `/settings/team` (`roles: ["org_admin"]`).
- **Events:** produces `notification.requested` (topic `gop.notifications`, payload
  `NotificationRequest`, producer `pillar`, consumer S12) on invite. No new event types.
- **Endpoints** (router `services/pillar/src/hope_pillar/api/me.py` and `api/users.py`):

  `GET /v1/me`: any signed-in user. 200:
  ```json
  {
    "user_id": "6f1c2a9e-3d4b-4c55-9a1e-0b7f2d8c4e11",
    "email": "dana@example.org",
    "display_name": "Dana Okafor",
    "roles": ["executive_director", "aor"],
    "mfa": false,
    "auth_mode": "oidc",
    "agency": {"agency_id": "1b6f0c1e-8a43-4f0e-9d2a-5c3e7b9a1f20", "legal_name": "Riverside Family Services"}
  }
  ```
  401 `unauthenticated` | `invalid_token`; 403 `not_invited` | `user_deactivated`; 503 `idp_unavailable`.

  `GET /v1/users?status=active|invited|deactivated&role=<Role>`: `org_admin`. 200:
  ```json
  {"items": [{
    "user_id": "6f1c2a9e-3d4b-4c55-9a1e-0b7f2d8c4e11",
    "email": "dana@example.org",
    "display_name": "Dana Okafor",
    "roles": ["executive_director", "aor"],
    "status": "active",
    "version": 3,
    "invited_by": "system:bootstrap",
    "created_at": "2026-11-01T14:02:11Z",
    "activated_at": "2026-11-01T14:10:40Z",
    "last_seen_at": "2026-11-07T15:01:00Z"
  }]}
  ```
  Ordered by `status` (`active`, `invited`, `deactivated`), then `display_name`. No pagination
  (one organization; Decision 5). 403 `forbidden`.

  `POST /v1/users`: `org_admin`. Body:
  `{"email": "sam@example.org", "display_name": "Sam Lee", "roles": ["finance_director"]}`
  (`display_name` 1-120 chars; `roles` 1-11 unique items). 201 with the user object
  (`status: "invited"`, `version: 1`) and a `Location: /v1/users/{user_id}` header.
  403 `forbidden`; 409 `user_exists`; 422 `unknown_role` | `validation_error`.

  `PATCH /v1/users/{user_id}`: `org_admin`, header `If-Match: "3"`. Body (at least one field):
  `{"roles": ["finance_director", "cfo"], "status": "active"}`. 200 with the updated user and
  `ETag: "4"`. 403 `forbidden`; 404 `not_found`; 409 `last_admin` | `cannot_deactivate_self`;
  412 `version_conflict`; 422 `unknown_role` | `invalid_transition`; 428 `precondition_required`.

- **Database** (`db/migrations/0110_users.sql`):
  ```sql
  CREATE TABLE users (
    user_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL REFERENCES tenants DEFAULT current_tenant(),
    email         text NOT NULL CHECK (email = lower(email)),
    display_name  text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 120),
    roles         text[] NOT NULL DEFAULT '{}',
    status        text NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','active','deactivated')),
    version       int  NOT NULL DEFAULT 1,
    idp_issuer    text,
    idp_subject   text,
    invited_by    text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    activated_at  timestamptz,
    last_seen_at  timestamptz,
    UNIQUE (tenant_id, email),
    UNIQUE (tenant_id, idp_issuer, idp_subject),
    CHECK ((idp_subject IS NULL) = (status = 'invited'))
  );
  ALTER TABLE users ENABLE ROW LEVEL SECURITY;
  ALTER TABLE users FORCE ROW LEVEL SECURITY;
  CREATE POLICY tenant_isolation ON users
    USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());
  ```
  Role values are validated in code (`Role`), not by a CHECK, so adding a role needs no migration.

## Owns

```text
services/pillar/src/hope_pillar/auth/**            (after A1 creates the package)
services/pillar/src/hope_pillar/api/me.py
services/pillar/src/hope_pillar/api/users.py
services/pillar/tests/test_auth_oidc.py
services/pillar/tests/test_users_api.py
services/pillar/tests/snapshots/openapi/me.json
services/pillar/tests/snapshots/openapi/users.json
db/migrations/0110_users.sql
apps/web/src/features/session/**
apps/web/src/api/session/**
apps/web/src/app/login/page.tsx
apps/web/src/app/settings/team/page.tsx
apps/web/.env.example (the NEXT_PUBLIC_HOPE_AUTH_MODE / NEXT_PUBLIC_HOPE_OIDC_* lines only)
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 In `oidc` mode a request without a bearer token gets 401 `unauthenticated` with `WWW-Authenticate: Bearer`.
- [ ] AC2 Tokens with a bad signature, `alg: none`, an HS256 key, the wrong `iss` or `aud`, or an expired `exp` get 401 `invalid_token`.
- [ ] AC3 An unknown `kid` refetches the JWKS once; a JWKS outage with no cached key gives 503 `idp_unavailable`.
- [ ] AC4 The first sign-in of an invited user with a verified matching email activates and binds the user and writes `user.activated`; an unverified email or no invite gives 403 `not_invited`.
- [ ] AC5 A deactivated user gets 403 `user_deactivated` on every endpoint, including the mounted profile router.
- [ ] AC6 Roles come from the `users` row, even when the token or an `X-Hope-Roles` header claims other roles.
- [ ] AC7 `mfa` is true only with a matching `amr` and an `auth_time` within the max age; HITL-5 authorize returns 403 for a stale step-up.
- [ ] AC8 Startup refuses `dev` mode when `HOPE_ENV=prod`, and refuses `oidc` mode without an issuer and audience.
- [ ] AC9 With an empty `users` table and `HOPE_BOOTSTRAP_ADMIN_EMAIL` set, that person can sign in as `org_admin`.
- [ ] AC10 `GET /v1/me` returns the user, roles, `mfa` and the tenant's single agency, or `agency: null` when no agency exists.
- [ ] AC11 Only `org_admin` can list, invite or change users (403 `forbidden` otherwise).
- [ ] AC12 An invite inserts an `invited` user, writes `user.invited`, and writes one `notification.requested` outbox row in the same transaction; a duplicate email gives 409 `user_exists`.
- [ ] AC13 PATCH enforces `If-Match` (428 / 412), `last_admin`, `cannot_deactivate_self`, `unknown_role` and `invalid_transition`, and writes exactly one audit row per real change.
- [ ] AC14 Every `users` and `audit_log` row written has `tenant_id = HOPE_TENANT_ID`.
- [ ] AC15 `last_seen_at` is written at most once per 5 minutes per user.
- [ ] AC16 OpenAPI snapshots `me.json` and `users.json` match.
- [ ] AC17 SC01 and SC17 meet their screen acceptance criteria.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/pillar/tests/test_auth_oidc.py::test_missing_bearer_is_401` | api |
| AC2 | `services/pillar/tests/test_auth_oidc.py::test_rejects_bad_tokens` (parametrized: bad sig, none, hs256, iss, aud, exp) | api |
| AC3 | `services/pillar/tests/test_auth_oidc.py::test_unknown_kid_refetches_once`, `::test_jwks_outage_is_503` | unit |
| AC4 | `services/pillar/tests/test_auth_oidc.py::test_first_login_binds_invite`, `::test_unverified_email_not_invited` | db |
| AC5 | `services/pillar/tests/test_auth_oidc.py::test_deactivated_user_blocked_everywhere` | db |
| AC6 | `services/pillar/tests/test_auth_oidc.py::test_roles_from_users_table` | db |
| AC7 | `services/pillar/tests/test_auth_oidc.py::test_mfa_requires_fresh_amr` | db |
| AC8 | `services/pillar/tests/test_auth_oidc.py::test_unsafe_config_refused` | unit |
| AC9 | `services/pillar/tests/test_auth_oidc.py::test_bootstrap_admin` | db |
| AC10 | `services/pillar/tests/test_users_api.py::test_me_with_and_without_agency` | db |
| AC11 | `services/pillar/tests/test_users_api.py::test_user_admin_requires_org_admin` | db |
| AC12 | `services/pillar/tests/test_users_api.py::test_invite_writes_user_audit_and_notification`, `::test_duplicate_invite_409` | db |
| AC13 | `services/pillar/tests/test_users_api.py::test_patch_rules` (parametrized per error code), `::test_patch_audit_rows` | db |
| AC14 | `services/pillar/tests/test_users_api.py::test_rows_use_configured_tenant` | db |
| AC15 | `services/pillar/tests/test_users_api.py::test_last_seen_throttled` | db |
| AC16 | `services/pillar/tests/test_openapi.py::test_router_snapshots` (existing, S00) | api |
| AC17 | see SC01 and SC17 test plans | unit |

Tests sign JWTs with a throwaway RSA key and serve the JWKS through a monkeypatched fetcher
(no network). Commands: the CI commands in `AGENTS.md`.

## Out of scope

SCIM provisioning, IdP group sync (unless Decision 3), multiple agencies or tenants, password
or magic-link login, API keys for connectors (they keep using the system DB role), session
revocation lists, per-user notification preferences (S12), e-signature (S19/S20).

## Decisions needed

1. **Web token handling.** Recommended: Authorization Code + PKCE in the browser
   (`features/session/oidc.ts`, WebCrypto, no new dependency), with the access token in memory
   and the PKCE verifier in `sessionStorage`; on 401 the app redirects to `/login`. The
   alternative is a BFF with an httpOnly cookie, which needs server routes and a session table.
2. **Role list.** Recommended: the eleven `Role` values in A2. Approval-hierarchy rules may only
   use these values (`board_treasurer` becomes `board_chair`). The alternative is to allow
   free-form roles from the profile, which makes `unknown_role` validation impossible.
3. **Roles from the IdP.** Recommended: Hope stores roles (SC17 is the source of truth). Optionally,
   `oidc_roles_claim` maps IdP groups to roles later, together with SCIM.
4. **Invite email.** Recommended: the invite carries only a link to `/login`. The invitee signs in
   with the IdP account whose verified email matches. No invite tokens.
5. **User list size.** Recommended: no pagination (a nonprofit team is well under 500 users).
6. **`HitlDecision.decided_by` value.** Recommended: `users.user_id` (a UUID string). Existing dev
   data that uses names like `dd-1` stays readable; SC15 shows "unknown user" for ids with no `users` row.

## References

- `packages/core/src/hope_core/auth.py` (S00), `services/pillar/src/hope_pillar/api/workflows.py::_lock_gate`
- `services/workflow/src/hope_workflow/policy.py::GATES`, `services/profile/src/hope_profile/validators.py::DEFAULT_HITL0_ROLES`
- `apps/web/src/api/session/` (S00), `apps/web/src/features/approvals/StepUpDialog.tsx`
- Blueprint 4.4, 6.2, 8.4. OpenID Connect Core 1.0 (`amr`, `auth_time`, `max_age`), RFC 7636 (PKCE), RFC 8176 (`amr` values).
