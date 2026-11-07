# S23: Post-award tracking and outcome loop

> **Out of scope for the hackathon. Don't build this.** This spec belongs to the earlier design (the Phase 1 pipeline and the M0-M7 / S-spec roadmap). Hackathon agents build only H0-H5 (see [`README.md`](../README.md)). Keep this file for after the hackathon.

| | |
|---|---|
| Wave | 3 |
| Depends on | S04 |
| Screens | SC23 |
| Migrations | `db/migrations/1400_awards.sql` |
| Blueprint | 4.3 (`Submitted -> Awarded | NotAwarded`, `Awarded -> PostAward`), 6.2 (CRM award records), 12 (P4 outcome capture, P5 post-award) |
| Status | Draft |

## Goal

After a submission, staff record the funder's decision. An award becomes a tracked record
with its amount, period and funder reports, and Hope reminds the owners before each report is
due. Every outcome (won or lost, with the reason) is published so matching can learn from it.
Today the lifecycle workflow ends at `Submitted` and nothing records what happened next.

## Current state

- `hope_core.schemas.lifecycle` allows `Submitted -> Awarded`, `Submitted -> NotAwarded`,
  `Awarded -> PostAward`; `PostAward` and `NotAwarded` are terminal.
- `OpportunityLifecycleWorkflow.run` returns a `LifecycleOutcome` when it reaches `Submitted`
  (or a terminal state). Nothing moves a workflow past `Submitted`.
- `tenant_opportunity` is mirrored by the workflow's `platform.mirror_state` activity;
  `workflow_transitions` and `GET /v1/workflows?state=Submitted` exist after S04.
- `a12.notify` and the notification centre exist after S12; `NotificationKind` has no report kinds.
- `AgencyProfile.grant_history[]` holds past grants with `funder_id` and `outcome`
  (`awarded | pending | declined | withdrawn`), used by `hope_matching.recommender.funder_relationship`.
- S00 created the `services/awards` skeleton and the empty mounted router
  `hope_pillar/api/awards.py`; `apps/web/src/features/awards/` and `/awards` routes show
  `ComingSoon`.

## Behaviour

1. **Record an outcome.** `POST /v1/awards` with `outcome` `awarded` or `not_awarded`.
   Roles: `development_director`, `executive_director`. In one tenant transaction:
   - the workflow must exist and `tenant_opportunity.state = 'Submitted'`, else
     `409 invalid_state` (with `state`); an outcome already recorded for the opportunity and agency
     -> `409 award_exists` (with `award_id`);
   - `awarded` requires `amount` (`Money`, entered by a human; `amount_minor > 0`), `period_start`
     < `period_end`, and optional `award_number`, `notice_sha256` (an artifact already uploaded via
     `POST /v1/ingest/artifacts`; unknown -> `422 unknown_artifact`), and `reports[]`;
   - `not_awarded` requires `reason_code` (`not_funded_score | ineligible | budget | late_or_incomplete
     | funder_priorities | unknown`) and optional `feedback` (max 4,000 chars, stored as untrusted text);
   - insert `awards` (+ `award_reports`), and write `award.outcome_recorded` (shared addition) to the
     outbox with `trace.correlation_id = workflow_id`.
   Response `201` with the award. `lifecycle_state` in the response is still `Submitted`; it changes
   when the post-award workflow runs (step 3).
2. **Reports schedule.** The client sends the reports (SC23 offers presets; the server only
   validates). Each report: `kind` (`progress | financial | final_progress | final_financial |
   other`), `title` (1-120 chars), `due_on` (date, funder timezone in `timezone`). Rules: every
   `due_on` is between `period_start` and `period_end + 120 days`; at most 60 reports;
   `final_*` kinds at most once each. Violations -> `422 invalid_report_schedule` with
   `errors[]` (`{index, field, message}`). An award may have zero reports.
3. **Post-award workflow.** `hope_workflow.postaward.starter` (consumer group
   `post-award-starter`) consumes `award.outcome_recorded` and starts `PostAwardWorkflow` with ID
   `post-award:{tenant_id}:{agency_id}:{opportunity_id}` (`USE_EXISTING`, so redelivery is safe)
   on task queue `q.workflow`. The workflow:
   - calls `assert_transition(Submitted, Awarded | NotAwarded)`, mirrors the state through the
     existing `platform.mirror_state` activity and publishes `opportunity.state_changed`
     (`OpportunityStateChanged` with `actor` = the user who recorded the outcome);
   - for `not_awarded`, stops there (terminal);
   - for `awarded`, then transitions `Awarded -> PostAward` and starts report reminders: for each
     report not yet `submitted`/`accepted`, timers at `due - 30 d`, `due - 7 d`, `due - 1 d`
     (computed at 09:00 in the report's `timezone`, skipped if in the past), and at `due + 1 d`
     for overdue. Before each reminder, the activity `postaward.report_status` reads the report;
     a submitted or accepted report gets no reminder. Reminders go through `a12.notify` with kinds
     `report_due` / `report_overdue` to `recipient_roles` = the report's `owner_role`
     (`finance_director` for financial kinds, `development_director` otherwise) and
     `request_id = null`, `link = /awards/{award_id}`.
   - Report schedule edits (step 4) emit `award.reports_changed`; the starter signals
     `reports_changed` to the running workflow, which reloads the schedule and re-plans timers.
   - The workflow completes when every report is `submitted` or `accepted`, or 180 days after
     `period_end`, whichever is first; then the award `status` becomes `closed`.
4. **Update a report.** `PUT /v1/awards/{award_id}/reports/{report_id}` with `status`
   (`upcoming | in_progress | submitted | accepted`), optional `submitted_on` (required for
   `submitted`/`accepted`, not in the future), `artifact_sha256`, `notes` (max 4,000), `due_on`
   (only while `upcoming`), and `version` (optimistic concurrency). Roles: `development_director`,
   `finance_director`, `program_lead`, `executive_director`. Mismatched `version` ->
   `409 version_conflict` with `current_version`. Moving backwards from `accepted` -> `422
   invalid_transition`. Writes `award.reports_changed` to the outbox.
   `overdue` is never stored: the API derives it (`status` in `upcoming | in_progress` and
   `due_on` < today in the report's timezone).
5. **Outcome loop.** `award.outcome_recorded` carries `funder_id`, `outcome`, `reason_code` and
   `amount`, so (outside this spec) the profile service can append to `grant_history` through its
   normal proposal flow and matching can use it as a training signal. S23 only publishes.
6. **No LLM** anywhere in this spec. Amounts, dates and statuses are human-entered and validated
   by code.

## Contracts

- **Shared models used:** `Money` (`hope_core.money`), `OpportunityState`, `assert_transition`,
  `OpportunityStateChanged` (S04's addition), `NotificationRequest`, `ProjectionRow`,
  `LifecycleInput` (`hope_core.schemas.workflow`), `Principal`, `Problem` errors.
- **Shared contract additions** (C3):
  - `hope_core.schemas.awards`: `AwardOutcomeRecorded` (`award_id: UUID`, `workflow_id: str`,
    `opportunity_id: UUID`, `agency_id: UUID`, `funder_id: str | None`, `outcome:
    Literal["awarded", "not_awarded"]`, `amount: Money | None`, `period_start: date | None`,
    `period_end: date | None`, `reason_code: str | None`, `recorded_by: str`, `recorded_at:
    datetime`) and `AwardReportsChanged` (`award_id`, `workflow_id`, `version: int`).
  - `EventType.AWARD_OUTCOME_RECORDED = "award.outcome_recorded"` and
    `EventType.AWARD_REPORTS_CHANGED = "award.reports_changed"`, both on `gop.opportunity.events`.
  - `NotificationKind` gains `report_due` and `report_overdue`.
  - `hope-awards` added to `services/pillar/pyproject.toml` so `api/awards.py` can mount
    `hope_awards.api.router` (same pattern as `api/agencies.py` mounting `hope_profile.api`).
- **Events:** produces `award.outcome_recorded`, `award.reports_changed` (producer `pillar`
  via `hope_awards.api`), `opportunity.state_changed` and `notification.requested` (from the
  post-award workflow). Consumes `award.outcome_recorded`, `award.reports_changed`.
- **Endpoints** (router `hope_awards.api.router`, mounted by `hope_pillar/api/awards.py`):

`POST /v1/awards`:

```json
{
  "workflow_id": "opportunity-lifecycle:…",
  "outcome": "awarded",
  "award_number": "H1ARH12345",
  "amount": { "amount_minor": 29850000, "currency": "USD" },
  "period_start": "2027-01-01",
  "period_end": "2028-12-31",
  "timezone": "America/New_York",
  "notice_sha256": null,
  "reports": [
    { "kind": "progress", "title": "Year 1 progress report", "due_on": "2027-12-31" },
    { "kind": "financial", "title": "SF-425 Year 1", "due_on": "2028-01-30" },
    { "kind": "final_progress", "title": "Final progress report", "due_on": "2029-03-31" },
    { "kind": "final_financial", "title": "Final SF-425", "due_on": "2029-04-30" }
  ]
}
```

`not_awarded` body: `{"workflow_id": "…", "outcome": "not_awarded", "reason_code":
"funder_priorities", "feedback": "Reviewers wanted a larger rural footprint."}`.
`201` -> the `Award` document below. Errors: `403 forbidden`, `404 not_found` (workflow),
`409 invalid_state`, `409 award_exists`, `422 invalid_report_schedule`, `422 unknown_artifact`,
`422 validation_error`.

`GET /v1/awards`. Any role. Query: `status` (`active | closed | not_awarded | all`, default
`active`), `due_within_days` (reports due within N days), `cursor`, `limit` (1-100, default 50).

```json
{
  "items": [
    {
      "award_id": "b2f0…",
      "workflow_id": "opportunity-lifecycle:…",
      "opportunity_id": "9a3e…",
      "title": "Rural Health Care Services Outreach Program",
      "funder_name": "HRSA",
      "outcome": "awarded",
      "status": "active",
      "amount": { "amount_minor": 29850000, "currency": "USD" },
      "period_start": "2027-01-01",
      "period_end": "2028-12-31",
      "next_report": { "report_id": "…", "title": "Year 1 progress report", "kind": "progress",
                       "due_on": "2027-12-31", "status": "upcoming", "overdue": false },
      "overdue_count": 0,
      "recorded_at": "2026-12-15T16:00:00Z"
    }
  ],
  "totals": { "active": 3, "awarded_amount": { "amount_minor": 61200000, "currency": "USD" },
              "reports_due_30d": 2, "overdue": 1 },
  "next_cursor": null
}
```

Sort: awards with overdue reports first, then by `next_report.due_on` ascending (nulls last),
then `recorded_at` desc. `totals` sums `amount` of `active` awards (single currency in the MVP;
mixed currencies -> `awarded_amount: null`).

`GET /v1/awards/{award_id}`. Any role. The list item plus `award_number`, `timezone`,
`notice_sha256`, `reason_code`, `feedback`, `recorded_by`, `lifecycle_state` (from
`tenant_opportunity`), `version`, and `reports[]`:

```json
{ "report_id": "…", "kind": "financial", "title": "SF-425 Year 1", "due_on": "2028-01-30",
  "status": "in_progress", "overdue": false, "owner_role": "finance_director",
  "submitted_on": null, "artifact_sha256": null, "notes": "", "version": 3,
  "updated_by": "u-femi", "updated_at": "2027-12-20T10:00:00Z" }
```

`404 not_found`.

`PUT /v1/awards/{award_id}/reports/{report_id}`: body `{"status": "submitted", "submitted_on":
"2028-01-28", "artifact_sha256": null, "notes": "Submitted in PMS", "version": 3}`. `200` -> the
report. Errors: `403 forbidden`, `404 not_found`, `409 version_conflict`, `422 invalid_transition`,
`422 validation_error`.

Catalog addition: `POST /v1/awards/{award_id}/reports` (add a report later,
same rules as step 2) and `DELETE /v1/awards/{award_id}/reports/{report_id}` (only `upcoming`).

- **Database** (`1400_awards.sql`, RLS `tenant_isolation` on both tables):

```sql
CREATE TABLE awards (
  award_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants,
  workflow_id     text NOT NULL,
  opportunity_id  uuid NOT NULL REFERENCES opportunities,
  agency_id       uuid NOT NULL REFERENCES agencies,
  outcome         text NOT NULL CHECK (outcome IN ('awarded','not_awarded')),
  status          text NOT NULL CHECK (status IN ('active','closed','not_awarded')),
  award_number    text,
  amount_minor    bigint CHECK (amount_minor > 0),
  currency        char(3),
  period_start    date,
  period_end      date,
  timezone        text,
  notice_sha256   text,
  reason_code     text,
  feedback        text,
  recorded_by     text NOT NULL,
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  version         int NOT NULL DEFAULT 1,
  UNIQUE (tenant_id, opportunity_id, agency_id),
  CHECK (outcome = 'not_awarded' OR (amount_minor IS NOT NULL AND period_start < period_end))
);
CREATE TABLE award_reports (
  report_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants,
  award_id        uuid NOT NULL REFERENCES awards,
  kind            text NOT NULL,
  title           text NOT NULL,
  due_on          date NOT NULL,
  owner_role      text NOT NULL,
  status          text NOT NULL CHECK (status IN ('upcoming','in_progress','submitted','accepted')),
  submitted_on    date,
  artifact_sha256 text,
  notes           text NOT NULL DEFAULT '',
  version         int NOT NULL DEFAULT 1,
  updated_by      text NOT NULL,
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX award_reports_due ON award_reports (tenant_id, due_on) WHERE status IN ('upcoming','in_progress');
```

Every report change also appends to `audit_log` (`action = 'award_report.updated'`).

## Owns

```text
services/awards/**
services/pillar/src/hope_pillar/api/awards.py
services/pillar/tests/test_awards_api.py
services/pillar/tests/snapshots/openapi/awards.json
services/workflow/src/hope_workflow/postaward/**
services/workflow/tests/test_postaward.py
db/migrations/1400_awards.sql
apps/web/src/api/awards/**
apps/web/src/features/awards/**
apps/web/src/app/awards/page.tsx
apps/web/src/app/awards/[awardId]/page.tsx
uv.lock (regenerated only)
docs/specs/README.md (this spec's status row only)
```

The worker registration of `PostAwardWorkflow` goes in `hope_workflow/postaward/worker.py`
(`python -m hope_workflow.postaward.worker`), so `hope_workflow/worker.py` (S07) is not edited.

## Acceptance criteria

- [ ] AC1 `POST /v1/awards` records `awarded` and `not_awarded` outcomes only for workflows in `Submitted`, returns 201, and writes `award.outcome_recorded` in the same transaction.
- [ ] AC2 A second outcome returns `409 award_exists`; a workflow in another state returns `409 invalid_state`.
- [ ] AC3 Report schedules are validated (`422 invalid_report_schedule` with per-row errors); amounts must be positive and human-entered.
- [ ] AC4 `PostAwardWorkflow` moves `Submitted -> Awarded -> PostAward` (or `-> NotAwarded`) with `assert_transition`, mirrors each state and publishes `opportunity.state_changed`.
- [ ] AC5 Report reminders fire at T-30d, T-7d, T-1d and +1d at 09:00 in the report's timezone, skip submitted reports, and re-plan after `reports_changed`.
- [ ] AC6 The workflow completes and the award becomes `closed` when all reports are submitted/accepted or 180 days after `period_end`.
- [ ] AC7 Report updates enforce `version` (`409 version_conflict`), the status rules (`422 invalid_transition`) and roles; `overdue` is derived, not stored.
- [ ] AC8 `GET /v1/awards` filters, sorts (overdue first, then next due) and computes `totals`; `GET /v1/awards/{id}` returns reports and `lifecycle_state`.
- [ ] AC9 RLS isolates `awards` and `award_reports`; report changes append to `audit_log`.
- [ ] AC10 The OpenAPI snapshot `openapi/awards.json` matches.
- [ ] AC11 SC23 meets its acceptance criteria.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/pillar/tests/test_awards_api.py::test_record_awarded_and_not_awarded` | db |
| AC2 | `test_awards_api.py::test_award_exists_and_invalid_state` | db |
| AC3 | `services/awards/tests/test_schedule.py::test_schedule_validation` (parametrized), `test_awards_api.py::test_amount_required_positive` | unit, db |
| AC4 | `services/workflow/tests/test_postaward.py::test_awarded_to_post_award`, `::test_not_awarded_terminal` | unit (time-skipping) |
| AC5 | `test_postaward.py::test_report_reminders_schedule`, `::test_submitted_report_skipped`, `::test_reports_changed_replans` | unit (time-skipping) |
| AC6 | `test_postaward.py::test_completes_and_closes_award` | unit (time-skipping) |
| AC7 | `test_awards_api.py::test_report_update_version_and_transitions`, `services/awards/tests/test_status.py::test_overdue_derived` | db, unit |
| AC8 | `test_awards_api.py::test_list_sort_filters_totals`, `::test_get_award_detail` | db |
| AC9 | `services/awards/tests/test_repository.py::test_rls_and_audit` | db |
| AC10 | `services/pillar/tests/test_openapi.py::test_router_snapshots` | api |
| AC11 | see SC23 | unit |

Fixtures: a workflow seeded in `Submitted` (S04's `tenant_opportunity` + `workflow_transitions`),
one award with four reports (one overdue, one in progress, one submitted, one upcoming), one
`not_awarded` outcome. Commands: the CI commands in `AGENTS.md`.

## Out of scope

Drawdowns and spending against the award (ERP, S25), automatic report drafting, pushing awards to
the CRM (S24 follow-up), funder portal report submission, updating `grant_history` (profile
consumer, follow-up), re-opening an outcome.

## Decisions needed

- **Lifecycle after `Submitted`.** Recommended: a separate `PostAwardWorkflow` (above) so the
  long-lived post-award timers don't keep the pre-award workflow's history open; the alternative
  is to keep `OpportunityLifecycleWorkflow` running with `continue_as_new`.
- **Who updates `grant_history`.** Recommended: the profile service consumes
  `award.outcome_recorded` and commits a non-protected change (C3 or a profile follow-up).
- **Federal report presets.** Recommended presets in SC23: annual progress (RPPR) + annual SF-425
  + final versions due 120 days after `period_end`; users can edit every date.

## References

- `packages/core/src/hope_core/schemas/lifecycle.py`, `hope_core/money.py`
- `services/workflow/src/hope_workflow/{workflow,activities,deadlines}.py`
- S04 (`workflow_transitions`, `GET /v1/workflows`), S12 (notification kinds)
- Blueprint 4.3, 6.2, 12.
