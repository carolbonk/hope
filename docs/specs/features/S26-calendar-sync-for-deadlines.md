# S26: Calendar sync for deadlines

| | |
|---|---|
| Wave | 3 |
| Depends on | S24, S12 |
| Screens | - (connection is managed on SC18, owned by S24) |
| Migrations | `db/migrations/0710_calendar_sync.sql` |
| Blueprint | 2.2 A12 (calendar milestones), 6.2 (Calendar: Google, MS Graph, dedicated calendar, ICS fallback; idempotent upserts) |
| Status | Draft |

## Goal

Every internal milestone and deadline that Hope schedules for a pursuit (go/no-go, budget
sign-off, compliance, executive approval, package ready, submission authorization, the internal
deadline and the funder deadline), plus post-award report due dates, appears in a dedicated
"Hope deadlines" calendar in the agency's Google or Microsoft 365 account, and stays in sync when
plans change or a pursuit ends.

## Current state

- `hope_workflow.deadlines.plan_deadlines(opportunity, now) -> DeadlinePlan`
  (`internal_deadline`, `funder_timezone`, `buffer_hours`, `milestones[]` of `Milestone(name,
  due_at, owner_role, gate)`); the milestone names are `go_no_go`, `budget_signoff`,
  `narrative_complete`, `compliance_attestation`, `executive_approval`, `package_ready`,
  `submission_authorization` (`MILESTONES`). The plan is computed in the `a12.plan_deadlines`
  activity at start and on every re-plan (revalidation, amendment) but is **not published**.
- `opportunity.state_changed` (with S04's `OpportunityStateChanged` payload) is published on every
  transition; S23 publishes `award.outcome_recorded` / `award.reports_changed`.
- S24 provides the integrations framework: OAuth connect/disconnect on SC18, stored per-integration
  credentials, `GET /v1/integrations`, and a sync trigger `POST /v1/integrations/{kind}/sync`.
  Its exact Python API is defined in S24 (referred to below as `IntegrationCredentials`).
- S12 owns `services/notifications`; S26 owns only `services/notifications/src/hope_notifications/calendar/`.

## Behaviour

1. **Plan event.** The workflow publishes `deadline.plan_updated` (shared addition) after every
   `a12.plan_deadlines` call, with the full plan, `workflow_id`, `opportunity_id`, `agency_id`,
   the opportunity title and `application_due`.
2. **Sync worker.** `hope_notifications.calendar.worker` (run
   `python -m hope_notifications.calendar.worker`, consumer group `calendar-sync`) consumes
   `deadline.plan_updated`, `opportunity.state_changed`, `award.outcome_recorded` and
   `award.reports_changed`. Nothing happens unless a calendar integration (`google_calendar` or
   `microsoft_calendar`) is connected; with none, events are acknowledged and skipped.
3. **Desired events.** For a plan: one event per milestone, one for the internal deadline
   ("Internal deadline: {title}") and one for the funder deadline ("Funder deadline: {title}").
   For an award: one per report not yet submitted. Each has a stable `external_id`
   `hope:{tenant_id}:{workflow_id}:{key}` (key = milestone name, `internal_deadline`,
   `funder_deadline`, or `report:{report_id}`), following the 6.2 idempotent-upsert rule.
4. **Event content.** Title: `"{Milestone label}: {opportunity title}"` (labels: "Go / No-Go",
   "Budget sign-off", "Narrative complete", "Compliance attestation", "Executive approval",
   "Package ready", "Submission authorization"; reports use the report title). Timed event of 30
   minutes ending at `due_at`, in `funder_timezone` (reports: the award `timezone`). Description:
   the owner role, the gate, and a link `{HOPE_WEB_BASE_URL}/workflows/{workflow_id}` (reports:
   `/awards/{award_id}`). No budget figures, narrative text or profile data (8.4). No attendees and
   no reminders (S12 handles reminders), so the provider never emails anyone.
5. **Reconcile.** For each `(workflow_id)`, compare desired events with `calendar_events` by
   `external_id` and `content_hash` (`hope_core.hashing.content_hash` of title, start, end,
   description):
   - new -> provider create, store `provider_event_id`, `etag`;
   - changed hash -> provider update (send `If-Match: etag`; a 412 means it was edited in the
     calendar: overwrite anyway, because Hope's plan is the source of truth, and log
     `calendar.overwritten` to `audit_log`);
   - no longer desired (milestone dropped because it is in the past at re-plan, or report submitted)
     -> keep past events, delete future ones.
6. **Ending.** `opportunity.state_changed` into a terminal state (`Declined`, `Expired`,
   `Ineligible`, `Archived`, `Discarded`, `NotAwarded`) deletes that workflow's future events;
   `Submitted` deletes future pre-submission milestones but keeps nothing else. A deleted
   provider event that is already gone (404/410) counts as deleted.
7. **Dedicated calendar.** On first sync the worker creates a calendar named "Hope deadlines"
   (Google `calendars.insert`; Graph `POST /me/calendars`) and stores its id in
   `calendar_targets`. If the user deletes it in the provider, the next write gets 404, the worker
   creates a new one and re-creates all future events.
8. **Providers.** `CalendarProvider` protocol: `ensure_calendar() -> str`,
   `upsert(calendar_id, event: CalendarEvent, provider_event_id: str | None, etag: str | None) ->
   (provider_event_id, etag)`, `delete(calendar_id, provider_event_id)`. Implementations:
   `GoogleCalendarProvider` (Calendar API v3 `events.insert` / `events.patch` / `events.delete`,
   scope `https://www.googleapis.com/auth/calendar.app.created`) and `GraphCalendarProvider`
   (`POST/PATCH/DELETE /me/calendars/{id}/events`, scope `Calendars.ReadWrite`). Both use `httpx`
   with tokens from `IntegrationCredentials` (S24), refreshing on 401 once.
9. **Errors.** 429/5xx: retry with backoff (1 s, 4 s, 16 s, then requeue the workflow's reconcile
   in 10 min). 401 after refresh or 403: mark the target `needs_reauth` and stop syncing until S24
   reconnects (SC18 shows it through S24's integration status). Every failure is recorded on the
   `calendar_events` row (`status = 'failed'`, `last_error`).
10. **Full resync.** `POST /v1/integrations/google_calendar/sync` (S24's endpoint) calls
    `calendar.resync_all()` through S24's sync hook: reconcile every non-terminal workflow and
    every active award.
11. **No LLM.**

## Contracts

- **Shared models used:** `DeadlinePlan`, `Milestone` (`hope_core.schemas.workflow`),
  `OpportunityStateChanged` (S04), `AwardOutcomeRecorded`, `AwardReportsChanged` (S23),
  `TERMINAL` (`hope_core.schemas.lifecycle`), `content_hash`.
- **Shared contract additions** (C3):
  - `EventType.DEADLINE_PLAN_UPDATED = "deadline.plan_updated"` on `gop.opportunity.events`, with
    payload `DeadlinePlanUpdated(workflow_id: str, opportunity_id: UUID, agency_id: UUID,
    title: str, application_due: datetime | None, plan: DeadlinePlan)`; the workflow publishes it
    after each `a12.plan_deadlines` (workflow file change made by C3).
  - S24's integration kinds include `google_calendar` and `microsoft_calendar` with the scopes in
    step 8, and S24's sync hook registry lets S26 register `resync_all`.
- **Events:** consumes the four events in step 2; produces none (audit rows only).
- **Endpoints:** none of its own (see Decisions needed for the ICS feed).
- **Database** (`0710_calendar_sync.sql`, RLS `tenant_isolation` on both tables):

```sql
CREATE TABLE calendar_targets (
  tenant_id     uuid NOT NULL REFERENCES tenants,
  provider      text NOT NULL CHECK (provider IN ('google_calendar','microsoft_calendar')),
  calendar_id   text NOT NULL,
  status        text NOT NULL CHECK (status IN ('active','needs_reauth')),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, provider)
);
CREATE TABLE calendar_events (
  tenant_id          uuid NOT NULL REFERENCES tenants,
  provider           text NOT NULL,
  external_id        text NOT NULL,
  workflow_id        text NOT NULL,
  provider_event_id  text,
  etag               text,
  starts_at          timestamptz NOT NULL,
  content_hash       text NOT NULL,
  status             text NOT NULL CHECK (status IN ('synced','deleted','failed')),
  last_error         text,
  updated_at         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, provider, external_id)
);
CREATE INDEX calendar_events_wf ON calendar_events (tenant_id, workflow_id);
```

## Owns

```text
services/notifications/src/hope_notifications/calendar/**
services/notifications/tests/calendar/**
db/migrations/0710_calendar_sync.sql
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 With no calendar integration connected, events are acknowledged and nothing is written.
- [ ] AC2 A `deadline.plan_updated` creates one event per milestone plus the internal and funder deadlines, with the titles, 30-minute timing in the funder timezone, description and no attendees/reminders as specified.
- [ ] AC3 Re-delivering the same plan makes no provider calls; a changed plan updates only changed events and deletes future events that are no longer planned.
- [ ] AC4 A terminal state deletes the workflow's future events; past events stay; a 404/410 on delete counts as deleted.
- [ ] AC5 A 412 on update overwrites the event and writes `calendar.overwritten` to `audit_log`.
- [ ] AC6 429/5xx retry with the backoff and requeue; 401 after one refresh or 403 marks the target `needs_reauth` and stops syncing.
- [ ] AC7 A deleted dedicated calendar is re-created and all future events re-synced.
- [ ] AC8 Award reports produce events until submitted, then their future events are deleted.
- [ ] AC9 Google and Graph adapters send the documented requests (recorded with `httpx.MockTransport`).
- [ ] AC10 RLS isolates both tables.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/notifications/tests/calendar/test_sync.py::test_skips_without_integration` | unit |
| AC2 | `test_sync.py::test_plan_creates_events` | unit |
| AC3 | `test_sync.py::test_idempotent_and_incremental` | db |
| AC4 | `test_sync.py::test_terminal_deletes_future`, `::test_delete_gone_is_ok` | db |
| AC5 | `test_sync.py::test_conflict_overwrites_and_audits` | db |
| AC6 | `test_sync.py::test_retry_and_needs_reauth` | unit |
| AC7 | `test_sync.py::test_recreates_deleted_calendar` | unit |
| AC8 | `test_sync.py::test_award_reports_events` | db |
| AC9 | `services/notifications/tests/calendar/test_google.py::test_requests`, `test_graph.py::test_requests` | unit |
| AC10 | `test_sync.py::test_rls` | db |

Fixtures: a `DeadlinePlan` from `plan_deadlines(factories.grant_opportunity(...), now)` for a
Grants.gov opportunity due in 40 days (`America/New_York`), the same plan re-planned with a new
deadline, a `FakeCalendarProvider` recording calls, recorded Google/Graph responses.
Commands: the CI commands in `AGENTS.md`.

## Out of scope

Per-user personal calendars, inviting attendees, two-way sync (calendar edits never change Hope's
plan), Outlook/Google reminders, the integration connect UI (S24).

## Decisions needed

- **ICS fallback.** Blueprint 6.2 lists an ICS fallback. Recommended: defer; if needed, add
  `GET /v1/calendar/feed.ics?token=` (catalog addition, new router `api/calendar.py` owned by S26)
  in a follow-up.
- **Event shape.** Recommended: 30-minute timed events ending at the due time (shows the exact
  cut-off); the alternative is all-day events on the due date.
- **Both providers connected.** Recommended: sync to every connected provider independently.

## References

- `services/workflow/src/hope_workflow/deadlines.py` (`plan_deadlines`, `MILESTONES`)
- Blueprint 2.2 A12, 6.2 (integration principles).
- Google Calendar API v3 events: https://developers.google.com/calendar/api/v3/reference/events
- Microsoft Graph calendar events: https://learn.microsoft.com/graph/api/calendar-post-events
