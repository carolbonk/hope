# S13: Audit trail API and screen

| | |
|---|---|
| Wave | 1 |
| Depends on | S00 |
| Screens | [SC15](../screens/SC15-audit-trail.md) (also feeds the audit panel of SC08, built by S04) |
| Migrations | `db/migrations/0120_audit.sql` |
| Blueprint | 4.4 (approval log), 8.4 (Audit: append-only, hash-chained, exportable), 2 CFR 200 recordkeeping |
| Status | Draft |

## Goal

Anyone accountable for a grant (the ED, compliance officer, auditors at single-audit time) can
see who did what, when, and to which record, prove that the log hasn't been altered, and export
it. Every HITL decision, submission authorization and outbound package lands in the trail
automatically, not only the actions that happen to write rows today.

## Current state

- `audit_log` (`db/migrations/0001_core.sql`): `audit_id bigserial`, `tenant_id`, `actor`, `action`,
  `subject`, `detail jsonb`, `at`, `prev_hash`, `hash`. The `audit_chain()` BEFORE INSERT trigger
  takes a per-tenant advisory lock and sets
  `hash = sha256(coalesce(prev_hash,'') || actor || action || subject || detail::text || at::text)`.
  `audit_log_append_only` forbids UPDATE and DELETE. RLS `tenant_isolation` applies.
- Only one writer: `hope_profile.repository.ProfileRepository._audit` (`subject = "agency:<uuid>"`,
  actions such as profile proposal approve/reject).
- HITL decisions are written to `approvals` by `_decide` (pillar `api/workflows.py` after S00) and
  published as `hitl.decided`, but nothing writes `audit_log` for them. `route_outbound`
  (`hope_pillar.pillar.KafkaPostgresPillar.route_outbound`) writes `submission.authorized` to the outbox
  only.
- No read API, no index other than the primary key, no chain verification, and no export.
- After S00, `hope_core.audit.write_audit` exists if the S01 shared addition A3 is accepted
  (this spec depends on it as well; see Shared contract additions).

## Behaviour

### Subjects and actions

1. `subject` is always `"<entity_type>:<entity_id>"`. Entity types in use or added now:
   `agency`, `user`, `workflow`, `opportunity`, `framework`, `package`, `artifact`, `audit`.
   The migration adds generated columns `entity_type` and `entity_id` (split on the first `:`).
   A subject without `:` gets `entity_type = 'other'` and `entity_id` = the whole subject.
2. `actor` is a user id (UUID string from S01), an agent id (`agent:A10`), or a service
   (`system:pillar`, `system:bootstrap`). The API returns `actor_kind` = `user` | `agent` | `system`,
   derived from the prefix (no prefix means `user`).
3. `action` is a dotted verb, lower case. This spec writes: `hitl.requested`, `hitl.decided`,
   `submission.authorized`, `application.submitted`, `audit.exported`. Other specs write
   `user.*` (S01), `artifact.downloaded` (S03), and profile actions (existing).

### Audit projector (new writer)

4. `hope_pillar.audit_projector.AuditProjector` consumes topics `gop.hitl.events` and
   `gop.outbound.packages` with consumer group `pillar-audit` through
   `KafkaPostgresPillar.consume(...)` (idempotent via `processed_events`). For each event it writes
   one audit row through `write_audit`, in the same transaction that records the event in `processed_events`
   (so a redelivery never writes twice, and a crash never loses one):

   | Event | actor | action | subject | detail |
   |---|---|---|---|---|
   | `hitl.requested` (`HitlRequest`) | `system:<envelope.producer.service>` | `hitl.requested` | `workflow:<workflow_id>` | `{event_id, request_id, gate, artifact_hash, approver_roles, due_at}` |
   | `hitl.decided` (`HitlDecision`) | `decided_by` | `hitl.decided` | `workflow:<trace.correlation_id>` | `{event_id, request_id, gate, decision, artifact_hash, role, comment_present}` |
   | `submission.authorized` (`OutboundPackage`) | `authorized_by` | `submission.authorized` | `opportunity:<opportunity_id>` | `{event_id, channel, manifest_hash}` |
   | `application.submitted` | `system:<producer.service>` | `application.submitted` | `opportunity:<subject_id>` | `{event_id, tracking_id}` plus the payload's `package_id` if it has one |

   The comment text is not copied (it can hold confidential notes; it stays in `approvals`). If
   `hitl.decided` has no `trace.correlation_id`, use `workflow:unknown` and add `"correlation_missing": true`.
   An event whose payload doesn't validate is sent to the DLQ by the existing pillar consumer path.
   The `workflow` payload of `submission.authorized` sent by `hope_workflow`
   (`{"manifest_hash", "authorized_by"}`, see S22 Decision 1) is also accepted: validate as
   `OutboundPackage` first, then fall back to these two keys.
5. Worker entry point `hope-pillar-audit` = `hope_pillar.audit_projector:main` (shared addition B2),
   reading `HopeSettings.database_system_url` and `HopeSettings.kafka_bootstrap`. It sets
   `app.tenant_id` per event from `envelope.tenant_id` (single tenant, but RLS still applies).

### Read API

6. `GET /v1/audit` returns entries newest first, keyset-paginated on `audit_id`.
   Query params (all optional, ANDed):
   - `entity_type` (one of the entity types above), `entity_id` (exact; requires `entity_type`, else
     422 `entity_type_required`). SC08 calls `entity_type=workflow&entity_id=<workflow_id>`.
   - `actor` (exact), `action` (exact, or a prefix ending in `.*`, e.g. `hitl.*`).
   - `from`, `to` (ISO 8601 with offset; `from` inclusive, `to` exclusive; `from >= to` -> 422 `invalid_range`).
   - `limit` 1-200 (default 50), `cursor` (opaque base64url of the last `audit_id`; tampered -> 422 `invalid_cursor`).
7. Roles: `org_admin`, `executive_director`, `compliance_officer`, `finance_director`,
   `development_director`, `aor` can read (`require_roles`). Anyone else -> 403 `forbidden`.
   (Decision 1.) Reads themselves aren't audited, except exports (step 10).
8. `detail` is returned as stored. Keys listed in `REDACTED_DETAIL_KEYS = {"comment", "ip", "user_agent"}`
   are replaced by `"[redacted]"` for everyone except `org_admin` and `compliance_officer`.
9. `GET /v1/audit/verify?from_id=&to_id=` (same roles) recomputes the chain in SQL over the range
   (default: the whole tenant chain) using the exact trigger expression and
   `lag(hash) OVER (ORDER BY audit_id)`, and returns the first broken link. For more than 100,000 rows it
   checks only the last 100,000 and says so (`checked_from_id`). Statement timeout 10 s -> 503 `verify_timeout`.
10. `GET /v1/audit/export?<same filters as step 6>&format=csv|jsonl` requires `org_admin` or
    `compliance_officer` **and** `principal.mfa` (else 403 `step_up_required`). It streams up to
    100,000 rows (more -> 422 `export_too_large`, narrow the range) with
    `Content-Disposition: attachment; filename="hope-audit-<from>-<to>.csv"`. Columns:
    `audit_id, at, actor, actor_kind, action, entity_type, entity_id, detail_json, prev_hash, hash`.
    Before streaming it writes `audit.exported` (`subject = "audit:export"`, detail = the filters and row count).
    No redaction for these two roles.

## Contracts

- **Shared models used:** `hope_core.auth.Principal`, `require_roles`; `hope_core.errors.Problem`;
  `hope_core.schemas.hitl.HitlRequest`, `HitlDecision` (with `role`, S00); `hope_core.pillar.OutboundPackage`;
  `hope_core.topics.Topic`, `EventType`.
- **Shared contract additions:**
  - **B1** `hope_core.audit.write_audit(...)` (the same item as S01 A3), plus
    `AuditEntity = Literal["agency","user","workflow","opportunity","framework","package","artifact","audit","other"]`
    and `subject_for(entity: AuditEntity, entity_id: str | UUID) -> str`.
  - **B2** `[project.scripts] hope-pillar-audit = "hope_pillar.audit_projector:main"` in
    `services/pillar/pyproject.toml`, so this spec never edits the shared pyproject.
  - **B3** Web: `nav.ts` entry `/audit` with `roles` = the six read roles of step 7.
- **Events:** consumes `hitl.requested`, `hitl.decided`, `submission.authorized` (`gop.hitl.events`)
  and `application.submitted` (`gop.outbound.packages`). Produces none.
- **Endpoints** (router `services/pillar/src/hope_pillar/api/audit.py`):

  `GET /v1/audit?entity_type=workflow&entity_id=wf-7f3a&limit=2` -> 200:
  ```json
  {
    "items": [
      {
        "audit_id": 1842,
        "at": "2026-11-07T14:58:03.120Z",
        "actor": "6f1c2a9e-3d4b-4c55-9a1e-0b7f2d8c4e11",
        "actor_kind": "user",
        "action": "hitl.decided",
        "entity_type": "workflow",
        "entity_id": "wf-7f3a",
        "subject": "workflow:wf-7f3a",
        "detail": {"event_id": "0b5a…", "request_id": "c2d1…", "gate": "HITL-2", "decision": "approve",
                   "artifact_hash": "sha256:9f2c…", "role": "finance_director", "comment_present": true},
        "hash": "4be1…e09a",
        "prev_hash": "77c0…1d3f"
      },
      {
        "audit_id": 1790,
        "at": "2026-11-06T09:12:44.501Z",
        "actor": "system:workflow",
        "actor_kind": "system",
        "action": "hitl.requested",
        "entity_type": "workflow",
        "entity_id": "wf-7f3a",
        "subject": "workflow:wf-7f3a",
        "detail": {"event_id": "a11e…", "request_id": "c2d1…", "gate": "HITL-2",
                   "artifact_hash": "sha256:9f2c…", "approver_roles": ["finance_director"], "due_at": "2026-11-09T09:12:44Z"},
        "hash": "77c0…1d3f",
        "prev_hash": "01aa…93be"
      }
    ],
    "next_cursor": "MTc5MA"
  }
  ```
  403 `forbidden`; 422 `entity_type_required` | `invalid_range` | `invalid_cursor` | `validation_error`.

  `GET /v1/audit/verify` -> 200:
  ```json
  {"valid": true, "checked": 1842, "checked_from_id": 1, "checked_to_id": 1842,
   "head_hash": "4be1…e09a", "first_broken_id": null, "verified_at": "2026-11-07T15:02:10Z"}
  ```
  When broken: `"valid": false, "first_broken_id": 1201, "reason": "hash_mismatch" | "prev_hash_mismatch"`.
  403 `forbidden`; 503 `verify_timeout`.

  `GET /v1/audit/export?from=2026-10-01T00:00:00Z&to=2026-11-01T00:00:00Z&format=csv` -> 200
  `text/csv` (or `application/x-ndjson`). 403 `forbidden` | `step_up_required`; 422 `export_too_large`.

- **Database** (`db/migrations/0120_audit.sql`):
  ```sql
  ALTER TABLE audit_log
    ADD COLUMN entity_type text GENERATED ALWAYS AS
      (CASE WHEN position(':' in subject) > 0 THEN split_part(subject, ':', 1) ELSE 'other' END) STORED,
    ADD COLUMN entity_id text GENERATED ALWAYS AS
      (CASE WHEN position(':' in subject) > 0 THEN substr(subject, position(':' in subject) + 1) ELSE subject END) STORED;
  CREATE INDEX audit_log_entity ON audit_log (tenant_id, entity_type, entity_id, audit_id DESC);
  CREATE INDEX audit_log_actor  ON audit_log (tenant_id, actor, audit_id DESC);
  CREATE INDEX audit_log_action ON audit_log (tenant_id, action text_pattern_ops, audit_id DESC);
  CREATE INDEX audit_log_at     ON audit_log (tenant_id, at);
  ```
  Generated columns don't change the hash input (the trigger hashes `subject`), so existing rows stay valid.
  Adding stored generated columns rewrites the table once; at MVP size that is acceptable (Decision 3).
  The migration touches a core table (`0001`) from the pillar range; see Catalog changes.

## Owns

```text
services/pillar/src/hope_pillar/api/audit.py
services/pillar/src/hope_pillar/audit_projector.py
services/pillar/tests/test_audit_api.py
services/pillar/tests/test_audit_projector.py
services/pillar/tests/snapshots/openapi/audit.json
db/migrations/0120_audit.sql
apps/web/src/features/audit/**
apps/web/src/api/audit/**
apps/web/src/app/audit/page.tsx
docs/specs/README.md (this spec's status row only)
```

## Acceptance criteria

- [ ] AC1 After the migration, every existing row has the right `entity_type`/`entity_id`, and the whole chain still verifies.
- [ ] AC2 The projector writes exactly one row per event for the four event types with the actor, action, subject and detail in the table; replaying the same events writes nothing more.
- [ ] AC3 The audit row and the `processed_events` row commit together (an injected failure between them leaves neither).
- [ ] AC4 `hitl.decided` detail never contains the comment text.
- [ ] AC5 `GET /v1/audit` filters by entity, actor, action (exact and `.*` prefix) and time range, newest first, with a working cursor; `entity_id` without `entity_type` is 422.
- [ ] AC6 Roles outside the six read roles get 403; `comment`/`ip`/`user_agent` detail keys are redacted except for `org_admin` and `compliance_officer`.
- [ ] AC7 `/v1/audit/verify` returns `valid: true` on an intact chain and the first broken id after a row is tampered with (by the admin role with the trigger disabled, in the test only).
- [ ] AC8 Export requires one of the two roles plus `mfa`, writes `audit.exported` first, streams CSV and JSONL with the listed columns, and refuses more than 100,000 rows.
- [ ] AC9 Every response is scoped to `HOPE_TENANT_ID` (rows of another tenant never appear).
- [ ] AC10 The `audit.json` OpenAPI snapshot matches.
- [ ] AC11 SC15 meets its screen acceptance criteria.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/pillar/tests/test_audit_api.py::test_migration_backfills_entity_columns` | db |
| AC2 | `services/pillar/tests/test_audit_projector.py::test_projects_each_event_type_once` | db |
| AC3 | `services/pillar/tests/test_audit_projector.py::test_audit_and_processed_commit_together` | db |
| AC4 | `services/pillar/tests/test_audit_projector.py::test_decision_comment_not_copied` | db |
| AC5 | `services/pillar/tests/test_audit_api.py::test_filters_and_cursor` (parametrized), `::test_entity_id_requires_type` | db |
| AC6 | `services/pillar/tests/test_audit_api.py::test_read_roles`, `::test_detail_redaction` | db |
| AC7 | `services/pillar/tests/test_audit_api.py::test_verify_intact_and_tampered` | db |
| AC8 | `services/pillar/tests/test_audit_api.py::test_export_requires_step_up`, `::test_export_formats`, `::test_export_limit` | db |
| AC9 | `services/pillar/tests/test_audit_api.py::test_other_tenant_rows_hidden` | db |
| AC10 | `services/pillar/tests/test_openapi.py::test_router_snapshots` | api |
| AC11 | see SC15 | unit |

The projector tests use `InMemoryPillar`-style envelopes fed straight into `AuditProjector.handle(cur, envelope)`;
one Kafka test (`@pytest.mark.db`, skipped without Redpanda) runs the consumer end to end.

## Out of scope

Auditing every read of restricted data (that needs a read hook in every router; S30), model-call
metadata (S29), external anchoring of the head hash (Decision 4), retention and legal hold, and
DSAR exports.

## Decisions needed

1. **Who can read the trail.** Recommended: the six roles in step 7. `grant_writer`, `program_lead`
   and `viewer` can't, so SC08 hides its audit panel for them.
2. **Display names.** S01 (same wave) owns `users`, so S13 returns only `actor` ids. Recommended:
   once S01 is Done, C2 adds `actor_display_name` (a `LEFT JOIN users`) to this endpoint. Until then
   SC15 shows the id, shortened.
3. **Generated columns vs. parsing per query.** Recommended: generated columns (indexable). If the
   table is already large in some environment, use a functional index on `split_part(subject, ':', 1)` instead.
4. **Anchoring.** Recommended: not in MVP. Later, publish the daily head hash to an external store.

## References

- `db/migrations/0001_core.sql` (`audit_log`, `audit_chain`), `services/profile/src/hope_profile/repository.py::_audit`
- `services/pillar/src/hope_pillar/pillar.py::route_outbound`, `services/pillar/src/hope_pillar/projector.py`
- Blueprint 4.4, 8.4; 2 CFR 200.334 (record retention)
