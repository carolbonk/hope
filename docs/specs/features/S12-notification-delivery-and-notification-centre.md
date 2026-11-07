# S12: Notification delivery and notification centre

> **Out of scope for the hackathon. Don't build this.** This spec belongs to the earlier design (the Phase 1 pipeline and the M0-M7 / S-spec roadmap). Hackathon agents build only H0-H5 (see [`README.md`](../README.md)). Keep this file for after the hackathon.

| | |
|---|---|
| Wave | 1 |
| Depends on | S00 |
| Screens | SC16 (plus the shell's unread bell, see Shared contract additions) |
| Migrations | `db/migrations/0700_notifications.sql` |
| Blueprint | 2.2 A12, 4.4 (gate mechanics: notify), 6.2 (Notifications), 7.2 (`gop.notifications`) |
| Status | Draft |

## Goal

Every `notification.requested` the workflow emits (gate requests, rejections, SLA
escalations, milestones, T-72h/T-24h deadline warnings, expiry, revalidation) reaches the right
people: in the app for everyone with the recipient role, and by email or Slack according to each
user's preferences and quiet hours. Users get a notification centre to read, filter and act on
them. Today the workflow's `a12.notify` activity publishes the event and hands it to
`StubChannel`s that only append to a list.

## Current state

- `hope_workflow.activities.PlatformActivities.notify` publishes `notification.requested`
  (topic `gop.notifications`, producer `workflow`/`A12`) with payload `NotificationRequest`
  (S00 moves it to `hope_core.schemas.workflow`): `notification_id`, `tenant_id`, `workflow_id`,
  `subject_id` (opportunity id), `kind` (`hitl_requested | hitl_rejected | escalation |
  milestone | deadline_warning | expired | revalidation`), `recipient_roles`, `title`, `body`,
  `channels` (default `["in_app", "email"]`; `in_app | email | slack | sms`), `gate`.
- `hope_workflow.ports.StubChannel` is the only channel adapter.
- S00 creates the `services/notifications` skeleton (`hope_notifications/__init__.py`, import
  test), the empty mounted router `hope_pillar/api/notifications.py`, the event type
  `notification.delivered` and `apps/web/src/features/notifications/`, `api/notifications/`
  placeholders.
- There is no user directory yet (S01 adds users in the same wave). Principals carry `user_id`
  and `roles` (`hope_core.auth.Principal`).

## Behaviour

### Intake

1. `hope_notifications.worker` (run `python -m hope_notifications.worker`, `hope_system` URL)
   subscribes to `notification.requested` with group `notifications`. For each envelope, in one
   transaction: skip if `processed_events` has `(notifications, event_id)`; validate the payload
   as `NotificationRequest` (invalid -> dead-letter via the pillar's DLQ, no row); insert one
   `notifications` row (`ON CONFLICT (notification_id) DO NOTHING`); then plan deliveries.
2. **In-app is always on.** A notification is visible to a user when `recipient_user =
   user_id` or `recipient_roles && principal.roles`. No per-user rows are created, so a role
   granted later sees past notifications for that role (Decisions needed). In-app can't be
   turned off in preferences, because gate requests must not be missed.
3. **External channels.** For each channel in `channels` other than `in_app`, resolve the
   recipients through `RecipientDirectory.users_with_roles(roles) -> list[Recipient(user_id,
   email, slack_member_id, timezone)]`. S12 ships `SettingsDirectory`, configured by
   `HOPE_NOTIFY_DIRECTORY` (JSON list of `{user_id, roles, email, slack_member_id, timezone}`);
   S01 later provides a database-backed directory behind the same protocol. For each recipient,
   apply that user's preferences (step 6); create one `notification_deliveries` row per
   `(notification_id, channel, recipient)` with status `queued`, `deferred` (quiet hours, with
   `next_attempt_at`) or `suppressed` (preference off). A recipient with no address for a channel
   gets `suppressed` with `last_error = 'no_address'`.
4. **Sending.** The worker's delivery loop picks `queued` rows and due `deferred` rows
   (`FOR UPDATE SKIP LOCKED`, batch 50). Adapters:
   - `EmailChannel`: SMTP (`HOPE_SMTP_URL`, `HOPE_NOTIFY_FROM`); SES/SendGrid later behind the
     same protocol. Subject = `title`; body = plain text `body` plus a link built from
     `HOPE_WEB_BASE_URL` and the notification's `link`. No artifact contents, money or profile
     data in email (data governance 8.4): only the title, the gate and the link.
   - `SlackChannel`: posts to the user (`chat.postMessage` with `slack_member_id`) using
     `HOPE_SLACK_BOT_TOKEN`; S24 later replaces the token with the integration's credential.
   - `sms` is accepted in requests but always `suppressed` with `last_error = 'channel_unavailable'`
     in the MVP.
   - Unset configuration -> that channel's deliveries are `suppressed` with
     `last_error = 'channel_disabled'`; nothing fails.
   On success: `status = 'sent'`, `sent_at`, and `notification.delivered`
   (`NotificationDelivered`, S00) through the outbox. On a transient error (timeout, 5xx, SMTP
   4xx): retry with backoff 1 min, 5 min, 30 min (`attempts` max 4), then `status = 'failed'`.
   On a permanent error (SMTP 5xx, Slack `user_not_found`): `failed` at once.
5. **Links.** `link` is computed at insert: `gate` and `request_id` present -> `/approvals/{request_id}`;
   otherwise `workflow_id` present -> `/workflows/{workflow_id}`; else null.
6. **Preferences.** Stored per user: for each `kind`, the enabled external channels; plus
   optional quiet hours (`start`, `end` as `HH:MM`, `timezone` IANA). Defaults when the user has
   none: email on for `hitl_requested`, `escalation`, `deadline_warning`, `expired`; email off for
   `milestone`, `hitl_rejected`, `revalidation`; Slack off for all. Urgent kinds (`escalation`,
   `deadline_warning`, `expired`) ignore quiet hours. A request's `channels` is the upper bound:
   preferences can only remove channels.
7. **Reading.** `POST /v1/notifications/{id}/read` and `POST /v1/notifications/read-all` write
   `notification_reads` rows (idempotent). Read state is per user.
8. **Retention.** Notifications older than 180 days are hidden from the list (query filter);
   deletion is S30's retention job. Notifications are never edited.
9. **LLM.** None. Digest summaries are out of scope.

## Contracts

- **Shared models used:** `NotificationRequest`, `NotificationKind`, `Channel`
  (`hope_core.schemas.workflow`, S00), `NotificationDelivered` (S00), `Gate`,
  `PillarEnvelope`, `Principal`, `Problem` errors (`hope_core.errors`).
- **Shared contract additions** (S00 or C2):
  - `NotificationRequest.request_id: UUID | None = None` (the HITL request a gate notification is
    about, so the link can open SC06) and `NotificationRequest.recipient_user: str | None = None`
    (direct notifications, for example the decider of a rejected gate). The workflow's
    `_notify` passes `request_id` for gate kinds.
  - `NotificationRequest.subject_title: str | None = None` (opportunity title at send time, so
    SC16 doesn't need a second call per row).
  - `NotificationDelivered` payload: `notification_id`, `channel`, `recipient` (user id),
    `status` (`sent | failed | suppressed`), `at`.
  - Web shell: `components/AppShell.tsx` gets a `NotificationBell` (bell icon, unread count badge
    "9+", link to `/notifications`) that calls `api.notifications.unreadCount()` every 60 s and on
    window focus. Built in S00/C2 because S00 owns the shell; S12 provides the client method.
- **Events:** consumes `notification.requested` (`gop.notifications`); produces
  `notification.delivered` (`gop.notifications`, producer `notifications`; consumer: S13 audit).
- **Endpoints** (router `hope_pillar/api/notifications.py`; SQL through `TxDep`, no import of
  `hope_notifications` so the pillar gets no new dependency):

`GET /v1/notifications`. Any signed-in user; only notifications visible to them (step 2).
Query: `unread` (bool), `kind` (repeatable), `cursor`, `limit` (1-100, default 30).

```json
{
  "items": [
    {
      "notification_id": "7c1e…",
      "kind": "hitl_requested",
      "title": "Go / No-Go needed: Rural Health Care Services Outreach Program",
      "body": "",
      "subject_title": "Rural Health Care Services Outreach Program",
      "gate": "HITL-1",
      "request_id": "3d4a…",
      "workflow_id": "opportunity-lifecycle:…",
      "link": "/approvals/3d4a…",
      "urgent": false,
      "created_at": "2026-11-07T14:58:02Z",
      "read_at": null
    }
  ],
  "unread_count": 4,
  "next_cursor": "eyJ…"
}
```

Order: `created_at` desc, then `notification_id`. `urgent` = kind in (`escalation`,
`deadline_warning`, `expired`). `unread_count` ignores `kind` and paging.
Errors: `400 invalid_cursor`, `422 validation_error`.

`POST /v1/notifications/{notification_id}/read`. `204`. Not visible or unknown -> `404 not_found`.

`POST /v1/notifications/read-all` (catalog addition). Body optional `{"kind": ["milestone"]}`.
`200 {"marked": 12}`.

`GET /v1/me/notification-preferences`. `200`:

```json
{
  "kinds": {
    "hitl_requested": { "email": true, "slack": false },
    "hitl_rejected": { "email": false, "slack": false },
    "escalation": { "email": true, "slack": false },
    "milestone": { "email": false, "slack": false },
    "deadline_warning": { "email": true, "slack": false },
    "expired": { "email": true, "slack": false },
    "revalidation": { "email": false, "slack": false }
  },
  "quiet_hours": { "start": "20:00", "end": "07:00", "timezone": "America/Chicago" },
  "channels_available": { "email": true, "slack": false, "sms": false },
  "updated_at": null
}
```

`channels_available` reflects configuration (step 4). `PUT` takes the same body without
`channels_available`/`updated_at`; every kind must be present; `quiet_hours` may be null.
Errors: `422 validation_error` (unknown kind, bad `HH:MM`, unknown timezone,
`start == end`), `422 channel_unavailable` (enabling a channel that `channels_available` marks
false). Returns `200` with the saved document.

- **Database** (`0700_notifications.sql`; RLS `tenant_isolation` on every table, as in `0001_core.sql`):

```sql
CREATE TABLE notifications (
  notification_id  uuid PRIMARY KEY,
  tenant_id        uuid NOT NULL REFERENCES tenants,
  event_id         uuid NOT NULL,
  kind             text NOT NULL,
  title            text NOT NULL,
  body             text NOT NULL DEFAULT '',
  subject_id       text NOT NULL,
  subject_title    text,
  workflow_id      text,
  gate             text,
  request_id       uuid,
  link             text,
  recipient_roles  text[] NOT NULL DEFAULT '{}',
  recipient_user   text,
  channels         text[] NOT NULL,
  created_at       timestamptz NOT NULL
);
CREATE INDEX notifications_feed ON notifications (tenant_id, created_at DESC, notification_id);
CREATE INDEX notifications_roles ON notifications USING gin (recipient_roles);
CREATE TRIGGER notifications_append_only BEFORE UPDATE OR DELETE ON notifications
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

CREATE TABLE notification_reads (
  tenant_id        uuid NOT NULL REFERENCES tenants,
  notification_id  uuid NOT NULL REFERENCES notifications,
  user_id          text NOT NULL,
  read_at          timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (notification_id, user_id)
);

CREATE TABLE notification_deliveries (
  delivery_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants,
  notification_id  uuid NOT NULL REFERENCES notifications,
  channel          text NOT NULL CHECK (channel IN ('email','slack','sms')),
  recipient        text NOT NULL,
  status           text NOT NULL CHECK (status IN ('queued','deferred','sent','failed','suppressed')),
  attempts         int  NOT NULL DEFAULT 0,
  last_error       text,
  next_attempt_at  timestamptz,
  sent_at          timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (notification_id, channel, recipient)
);
CREATE INDEX notification_deliveries_due ON notification_deliveries (next_attempt_at)
  WHERE status IN ('queued','deferred');

CREATE TABLE notification_preferences (
  tenant_id    uuid NOT NULL REFERENCES tenants,
  user_id      text NOT NULL,
  preferences  jsonb NOT NULL,
  updated_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, user_id)
);
```

- **Settings** (`hope_notifications.settings.NotificationSettings`, prefix `HOPE_`):
  `smtp_url`, `notify_from`, `slack_bot_token`, `notify_directory`, `web_base_url`,
  `notify_batch_size = 50`.

## Owns

```text
services/notifications/** (except calendar/, which S26 owns)
services/pillar/src/hope_pillar/api/notifications.py
services/pillar/tests/test_notifications_api.py
services/pillar/tests/snapshots/openapi/notifications.json
db/migrations/0700_notifications.sql
apps/web/src/api/notifications/**
apps/web/src/features/notifications/**
apps/web/src/app/notifications/page.tsx
uv.lock (regenerated only)
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 Each `notification.requested` creates exactly one `notifications` row, also on redelivery; an invalid payload is dead-lettered.
- [ ] AC2 A user sees a notification when their roles overlap `recipient_roles` or they are `recipient_user`, and never otherwise.
- [ ] AC3 Deliveries follow preferences, defaults, the request's `channels` upper bound and quiet hours (urgent kinds bypass); missing address and disabled channels are `suppressed` with the reason.
- [ ] AC4 Sending retries transient errors with the 1/5/30 min backoff up to 4 attempts, fails permanent errors at once, and writes `notification.delivered` for each final status.
- [ ] AC5 Email contains only the title, gate and link (no body fields beyond `body`, no money).
- [ ] AC6 `link` is `/approvals/{request_id}` for gate notifications and `/workflows/{workflow_id}` otherwise.
- [ ] AC7 `GET /v1/notifications` filters by `unread` and `kind`, pages by cursor, and returns `unread_count`; read and read-all are idempotent and per user.
- [ ] AC8 Preferences GET returns defaults for a new user; PUT validates kinds, times, timezone and available channels with the listed codes.
- [ ] AC9 RLS isolates every new table; `notifications` is append-only.
- [ ] AC10 The OpenAPI snapshot `openapi/notifications.json` matches.
- [ ] AC11 SC16 meets its acceptance criteria.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/notifications/tests/test_intake.py::test_one_row_per_request`, `::test_invalid_payload_dead_lettered` | db |
| AC2 | `services/pillar/tests/test_notifications_api.py::test_visibility_by_role_and_user` | db |
| AC3 | `services/notifications/tests/test_planning.py::test_preferences_defaults_and_quiet_hours` (parametrized), `::test_suppressed_reasons` | unit |
| AC4 | `services/notifications/tests/test_delivery.py::test_retry_backoff`, `::test_permanent_failure`, `::test_delivered_event` | db |
| AC5 | `test_delivery.py::test_email_content_minimal` | unit |
| AC6 | `services/notifications/tests/test_intake.py::test_link` | unit |
| AC7 | `test_notifications_api.py::test_list_filters_cursor_unread_count`, `::test_read_and_read_all_idempotent` | db |
| AC8 | `test_notifications_api.py::test_preferences_defaults`, `::test_preferences_validation` | db |
| AC9 | `services/notifications/tests/test_schema.py::test_rls_and_append_only` | db |
| AC10 | `services/pillar/tests/test_openapi.py::test_router_snapshots` (S00) | api |
| AC11 | see SC16 | unit |

Fixtures: SMTP via `aiosmtpd`-free fake (`FakeSmtp` adapter capturing messages), Slack via
`httpx.MockTransport`; a `SettingsDirectory` with three users (`u-dana` executive_director +
development_director, `u-femi` finance_director, `u-sam` compliance_officer without email).
Commands: the CI commands in `AGENTS.md`.

## Out of scope

SMS delivery, digests (LLM summaries), push notifications, calendar sync (S26), a user
directory (S01), per-channel templates beyond plain text.

## Decisions needed

- **Role-based visibility of past notifications.** A user given a role later sees that role's
  history. Recommended: accept for the MVP (single small team); S01 can add a `granted_at` cutoff.
- **Email provider.** Recommended: SMTP for the MVP (works with SES SMTP and SendGrid SMTP);
  API adapters later.
- **Slack target.** Recommended: DM to the user; a shared channel option is a follow-up.

## References

- `services/workflow/src/hope_workflow/{contracts,activities,ports}.py` (`NotificationRequest`, `notify`, `StubChannel`)
- `services/pillar/src/hope_pillar/{dlq,outbox}.py`, `db/migrations/0001_core.sql` (`processed_events`, RLS pattern)
- Blueprint 2.2 A12, 4.4, 6.2, 8.4.
