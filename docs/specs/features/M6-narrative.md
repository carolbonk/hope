# M6: Narrative drafting (OpenAI, budget placeholders, editable draft)

> **Out of scope for the hackathon. Don't build this.** This spec belongs to the earlier design (the Phase 1 pipeline and the M0-M7 / S-spec roadmap). Hackathon agents build only H0-H5 (see [`README.md`](../README.md)). Keep this file for after the hackathon.

| | |
|---|---|
| Wave | MVP (parallel with M1-M5, M7, after M0) |
| Depends on | M0 |
| Screens | SC19 |
| Migrations | `db/migrations/0800_narratives.sql` (range 0800-0809) |
| Blueprint | 2.2 A9 (narrative), 8.1 (no LLM money), 8.2 (grounding), 8.3 (untrusted content) |
| Status | Draft |

## Goal

Once the budget exists, a grant writer opens the draft workspace (SC19), clicks **Draft with
AI**, and within about a minute gets a complete narrative. There is one section per RFP
requirement, written from the agency's own profile. Every dollar figure is a
`{{budget.*}}` placeholder that resolves live from the budget ledger, and any number Hope can't
trace back to the ledger or the profile is flagged. The writer edits and saves sections, and
M7 packages the result.

## Current state

After M0 (assumed merged):

- `services/drafting` exists with `hope_drafting/ports.py`, where
  `draft_sections(framework, opportunity, profile, ledger) -> list[NarrativeSection]` raises
  `NotImplementedError`.
- `hope_core.schemas.NarrativeSection` has the fields `section_id`, `title`, `body_md`,
  `placeholders: list[str]`, `evidence_ids` and `content_hash`.
- `hope_core.model_gateway`:
  - `default_gateway()` returns OpenAI when `HOPE_OPENAI_API_KEY` is set, otherwise `MockProvider`;
  - `RunBudget(max_calls, max_tokens)` raises `BudgetExceededError`;
  - `untrusted()` wraps document text.
- `services/pillar/src/hope_pillar/api/narratives.py` is an empty mounted router.
  Request-scoped DB access uses `TxDep` (`hope_pillar.api.deps.Tx`: `cur`, `principal`, `services`).
- `hope_core.auth.Role`: `development_director`, `program_director`, `finance_director`,
  `executive_director`, `aor`, `admin`.
- Core tables (0001):
  - `frameworks`: `framework_id`, `opportunity_id`, `agency_id`, `version`, `status`,
    `framework` jsonb, `content_hash`;
  - `budget_ledgers`: `framework_id`, `ledger` jsonb, `content_hash`, `created_at`;
  - `opportunity_versions`: `normalized` jsonb = `GrantOpportunity`;
  - `tenant_opportunity`: `state`, `workflow_id`;
  - `agency_profile_versions`.
- M4 calls `draft_sections` when the workflow enters `Drafting`. M7 reads the sections to build
  the package.
- Web: `/frameworks/[frameworkId]/draft` renders M0's `ComingSoon`. `apps/web/src/api/proposal/`
  is an empty client split by M0.

## Behaviour

### Sections to draft

1. The section plan is computed by `hope_drafting.plan.section_plan(opportunity)`.
   - Each `opportunity.requirements.sections[]` (`RequirementSection`) becomes one section,
     in RFP order, with the same `section_id` and `title`. It carries `instructions`,
     `word_limit`, `page_limit` and `evaluation_criteria`.
   - When the RFP lists no sections, the default plan is:

     | `section_id` | Title | Word limit |
     |---|---|---|
     | `project_summary` | Project summary | 250 |
     | `statement_of_need` | Statement of need | 600 |
     | `approach` | Project design and approach | 900 |
     | `outcomes` | Goals, objectives and outcomes | 600 |
     | `capacity` | Organizational capacity | 500 |
     | `budget_narrative` | Budget narrative | 400 |

     Each has generic instructions.

### Grounding (what the model sees)

2. For each section, `hope_drafting.grounding.build_context(...)` builds numbered evidence
   items. Each has an `id`, a label and text:
   - `rfp:{section_id}`: the requirement's title, instructions and evaluation criteria,
     wrapped with `untrusted(text, "rfp")`;
   - `rfp:summary`: the opportunity title, funder name, `project_period_months`, plus the
     award floor and ceiling given **as placeholders only** (`{{budget.request_total}}` is the
     only money the model may write);
   - `profile:mission`, `profile:vision`, `profile:theory_of_change`, `profile:focus_areas`;
   - `profile:program:{program_id}`: name, description, geography and target demographics;
   - `profile:outcome:{metric_id}`: label, value, unit and period;
   - `profile:capacity`;
   - `profile:grant_history:{n}`: funder and outcome, with **no amounts**;
   - `memory:{chunk_id}`: up to 3 hits from `hope_profile.memory.NarrativeMemory.search(tenant,
     query=section title + instructions, k=3, approved_only=True)`, if any chunks exist.
     These are also wrapped with `untrusted`.
3. Allowed placeholders form a fixed vocabulary. Each resolves from the latest
   `BudgetLedger` for the framework:

   | Placeholder | Resolves to |
   |---|---|
   | `{{budget.request_total}}` | `totals.request_minor` |
   | `{{budget.direct_total}}` | `totals.direct_minor` |
   | `{{budget.indirect_total}}` | `totals.indirect_minor` |
   | `{{budget.mtdc_base}}` | `totals.mtdc_base_minor` |
   | `{{budget.cost_share_total}}` | `totals.cost_share_minor` |
   | `{{budget.project_total}}` | `totals.project_total_minor` |
   | `{{budget.periods}}` | `periods` |
   | `{{budget.category.<category>}}` | the sum of `line_items[].amount_minor` where `category == <category>` and `funding_source == "request"` |

   `<category>` is any `BudgetCategory`: `personnel`, `fringe`, `travel`, `equipment`,
   `supplies`, `contractual`, `construction`, `other`, `indirect`. Money is formatted with
   `Money.format()` without the currency code, for example `$185,000.00` → `$185,000`
   (whole dollars when the cents are 0).

### Drafting a section (LLM suggests, code decides)

4. For each section, there is one call:
   `gateway.structured(ModelTier.FRONTIER, messages, SectionDraft, budget=run_budget)`.
   - The system prompt says:
     - write only from the evidence items;
     - cite the evidence ids used;
     - never write a dollar amount, percentage of the budget or count of money, and use the
       placeholders instead;
     - never invent statistics;
     - markdown only, no headings above `###`;
     - stay under the word limit.
   - The response model `SectionDraft` (service-private) has
     `body_md: str = Field(max_length=20000)` and `evidence_ids: list[str]`.
5. Code post-processes every draft (`hope_drafting.checks`):
   1. `placeholders` = every `{{...}}` token in `body_md`. An unknown key is a finding
      `unknown_placeholder`.
   2. `evidence_ids` is limited to ids that exist in the context; unknown ids are dropped.
   3. **Number trace.** `checks.untraced_numbers(body_md, allowed)` finds every numeric
      token outside placeholders (regex `\$?\d[\d,]*(\.\d+)?%?`). Two kinds of token are
      exempt: ordered-list markers at the start of a line (`^\s*\d+\.\s`), and `section_id`
      digits inside headings.
      - Any token with `$` is a finding `literal_money`.
      - Every other token, normalized (no commas, no `%`), must equal a number in `allowed`.
        Otherwise it is a finding `untraced_number`. `allowed` contains:
        - every number in the context texts;
        - every numeric profile field (`outcomes[].value`, `annual_served`,
          `grant_writer_fte`, `monthly_hours_available`, `max_concurrent_applications`,
          `fringe_rate_bps / 100`, `indirect_rate.rate_bps / 100`);
        - the opportunity's `project_period_months`;
        - the years in `period` fields.
   4. Word count (whitespace tokens of the **rendered** text) above `word_limit` is a finding
      `over_word_limit`. Above `page_limit × 500` it is a warning `may_exceed_page_limit`.
6. If step 5 finds `literal_money`, `untraced_number` or `unknown_placeholder`, the section is
   **retried once** with an extra user message listing the offending tokens: "Remove or
   replace these; use only evidence numbers or placeholders: …". If they remain, the section
   is saved with `status = "needs_review"` and its `findings`. The model output is never
   silently altered.
7. `content_hash = content_hash({"section_id", "title", "body_md"})`. The draft hash is
   `content_hash([{section_id, content_hash}, …])` in plan order. M4 uses the draft hash as
   the HITL-4 artifact hash.

### Token and cost budget per draft

8. `DraftingSettings` (prefix `HOPE_DRAFTING_`, in `hope_drafting/settings.py`):

   | Setting | Default |
   |---|---|
   | `max_tokens_per_draft` | `60000` |
   | `max_calls_per_draft` | `16` |
   | `max_usd_per_draft` | `0.50` |
   | `usd_per_1k_tokens` | `0.0006` (the gpt-4o-mini output price, used for all tokens as a ceiling) |
   | `max_parallel_sections` | `3` |

   - Each run gets one `RunBudget(max_calls, max_tokens=min(max_tokens_per_draft,
     floor(max_usd_per_draft / usd_per_1k_tokens × 1000)))`.
   - When `BudgetExceededError` is raised, the sections finished so far are kept, the run is
     marked `budget_exceeded`, and the remaining sections keep their previous version (or none).
   - `cost_usd = tokens_used / 1000 × usd_per_1k_tokens`, stored on the run.

### Runs, persistence and the port

9. `hope_drafting.ports.draft_sections(framework, opportunity, profile, ledger)` (M4 calls it
   from the workflow):
   - creates a run with `requested_by = "workflow"`;
   - drafts every planned section, up to `max_parallel_sections` at a time
     (`concurrent.futures.ThreadPoolExecutor`);
   - persists each section as a new version through `hope_drafting.store`, in `tenant_tx`
     with `HOPE_TENANT_ID`;
   - returns the current `NarrativeSection` list in plan order.

   It is idempotent per `(framework_id, framework.content_hash)`: if a `succeeded` run for
   the same framework hash exists, it returns the stored sections without calling the model.
10. `POST /v1/frameworks/{id}/narratives/draft` starts a run in a FastAPI `BackgroundTask`
    and returns `202` with the run. Only one run may be active per framework:
    `409 draft_in_progress`.
    - A `running` row older than 10 minutes counts as failed (`error_code = "timeout"`) so it
      can't block forever.
    - An optional `section_ids` redrafts only those sections. Optional `guidance` (≤ 500
      chars, the user's note, for example "shorter, mention rural focus") is added to the
      prompt as untrusted user guidance.
11. Human edits (`PUT .../narratives/{section_id}`) store a new version with `source =
    "human"`. They re-run step 5's checks (findings are shown, never blocking) and recompute
    `content_hash`. A save must send `base_hash`; a mismatch returns `409 stale_artifact`
    with `current_hash`.
12. Locking. When `tenant_opportunity.state` for the framework's opportunity is `Packaging`
    or later (`AwaitingSubmissionAuth`, `Submitted`, …), drafts and edits return
    `409 draft_locked`. Editing while `AwaitingExecApproval` is allowed, and it changes the
    draft hash. That voids the open HITL-4 request (M3/M4 rule: approvals bind to the hash).
13. Every run and every human save writes `audit_log`:
    - actions `narrative.draft_started`, `narrative.draft_finished` (detail
      `{run_id, status, tokens_used, cost_usd}`) and `narrative.section_saved` (detail
      `{section_id, version, content_hash}`);
    - `actor` = the principal user id or `workflow`.

    No pillar event types are added for the MVP.

### API rendering

14. `GET` resolves placeholders against the framework's latest ledger
    (`SELECT ledger FROM budget_ledgers WHERE framework_id = %s ORDER BY created_at DESC LIMIT 1`)
    and returns both `body_md` (with placeholders) and `rendered_md`.
    - Without a ledger, placeholders render as `[budget pending]` and `budget_ready: false`.
    - When the ledger changes later, the rendered text updates automatically. `body_md` and
      `content_hash` don't change.

### What the LLM may and may not do

The LLM only writes `SectionDraft.body_md` and `evidence_ids`. It never writes money (that is
enforced by `literal_money`), never decides status, never resolves placeholders, and never
sees amounts. When `HOPE_OPENAI_API_KEY` is unset, `default_gateway()` is `MockProvider` with
the responder in `hope_drafting.testing.mock_responder`. That responder returns deterministic
section text built from the evidence items, so the demo and CI run offline.

## Contracts

- **Shared models used:** `NarrativeSection`, `ProposalFramework`, `BudgetLedger`,
  `GrantOpportunity`, `RequirementSection`, `AgencyProfile`, `Money`, `content_hash`,
  `ModelGateway`/`ModelTier`/`RunBudget`/`BudgetExceededError`/`untrusted`/`default_gateway`,
  `hope_core.auth.Role`/`require_roles`, `hope_core.errors.Problem`.
- **Service-private models** (`hope_drafting.models`): `SectionPlanItem`, `EvidenceItem`,
  `SectionDraft`, `Finding {code, token?, detail}`, `DraftRun`, `SectionView`, `NarrativesView`.
- **Events:** none.
- **Endpoints** (router `hope_pillar.api.narratives`, prefix `/v1`). The demo user comes from
  M0 headers. Every error is `application/problem+json` with `code`.

  **Roles**

  | Action | Roles |
  |---|---|
  | View | any role |
  | Draft and edit | `development_director`, `program_director`, `admin` |

  `GET /v1/frameworks/{framework_id}/narratives` returns `200`:

  ```json
  {
    "framework_id": "7b0f3c2a-5d1e-4b8a-9c3f-2e6d1a4b5c70",
    "opportunity": {"opportunity_id": "3f2a…", "title": "Youth STEM Mentoring Demonstration Grants",
                    "funder_name": "Administration for Children and Families",
                    "application_due": "2026-12-22T21:59:00Z"},
    "workflow": {"workflow_id": "wf-3f2a…", "state": "Drafting"},
    "locked": false,
    "budget_ready": true,
    "draft_hash": "sha256:91ce…",
    "ready": false,
    "run": {"run_id": "c1d2…", "status": "succeeded", "requested_by": "u-demo",
            "section_ids": ["project_summary", "statement_of_need", "approach", "outcomes", "capacity", "budget_narrative"],
            "completed_section_ids": ["project_summary", "statement_of_need", "approach", "outcomes", "capacity", "budget_narrative"],
            "tokens_used": 18450, "cost_usd": 0.0111, "started_at": "2026-11-08T14:02:11Z",
            "finished_at": "2026-11-08T14:02:49Z", "error_code": null},
    "sections": [
      {"section_id": "budget_narrative", "title": "Budget narrative", "version": 2, "source": "ai",
       "status": "drafted",
       "body_md": "We request {{budget.request_total}} over {{budget.periods}} year(s). Personnel ({{budget.category.personnel}}) funds the program coordinator…",
       "rendered_md": "We request $185,000 over 1 year(s). Personnel ($120,000) funds the program coordinator…",
       "placeholders": ["budget.request_total", "budget.periods", "budget.category.personnel"],
       "evidence_ids": ["rfp:budget_narrative", "profile:program:prog-stem"],
       "requirement": {"instructions": "Justify each cost category.", "word_limit": 400, "page_limit": null,
                       "evaluation_criteria": ["Costs are reasonable and allocable"]},
       "word_count": 212, "findings": [],
       "content_hash": "sha256:a41f…", "updated_by": "u-demo", "updated_at": "2026-11-08T14:02:47Z"},
      {"section_id": "outcomes", "title": "Goals, objectives and outcomes", "version": 1, "source": "ai",
       "status": "needs_review", "body_md": "…serving 450 students…", "rendered_md": "…",
       "placeholders": [], "evidence_ids": ["profile:outcome:youth-served"],
       "requirement": {"instructions": "…", "word_limit": 600, "page_limit": null, "evaluation_criteria": []},
       "word_count": 488,
       "findings": [{"code": "untraced_number", "token": "450", "detail": "Not found in the profile, RFP or budget"}],
       "content_hash": "sha256:5be0…", "updated_by": "workflow", "updated_at": "2026-11-08T14:02:40Z"}
    ],
    "evidence": {"rfp:budget_narrative": {"label": "RFP: Budget narrative", "text": "Justify each cost category."},
                 "profile:program:prog-stem": {"label": "Program: After-school STEM Lab", "text": "Weekly robotics…"}}
  }
  ```

  - `sections` are in plan order. Planned sections that are not drafted yet appear with
    `version: 0`, `status: "not_started"`, `body_md: ""`, `content_hash: null`.
  - `ready` is true when every planned section has `version ≥ 1` and no section has
    `status == "needs_review"`.
  - `run` is the latest run, or `null` before the first one. `workflow` is `null` when no
    `tenant_opportunity` row exists for the framework's opportunity. `evidence` holds every
    id referenced by any section.
  - Errors: `404 not_found` when there is no framework.

  `POST /v1/frameworks/{framework_id}/narratives/draft`, roles draft. The body is optional:

  ```json
  {"section_ids": ["outcomes"], "guidance": "Use the outcome numbers from our profile only."}
  ```

  `202` returns `{"run": {…DraftRun, "status": "running", "completed_section_ids": []}}`.

  | Status | Code | When |
  |---|---|---|
  | 400 | `unknown_section` | with `section_ids[]` that are not in the plan |
  | 403 | `forbidden` | |
  | 404 | `not_found` | |
  | 409 | `draft_in_progress` | with `run_id` |
  | 409 | `draft_locked` | with `state` |
  | 409 | `budget_missing` | no ledger yet; with `detail` "Finish the budget first" |
  | 422 | `validation_failed` | `guidance` over 500 chars |

  The run's final `status` is one of:
  - `succeeded`;
  - `partial`, when some sections failed validation after the retry; they are still saved as
    `needs_review`;
  - `budget_exceeded`;
  - `failed`, with `error_code` set to `provider_error` (OpenAI error after
    `ModelGateway` failover), `timeout` or `internal`.

  `PUT /v1/frameworks/{framework_id}/narratives/{section_id}`, roles draft:

  ```json
  {"body_md": "We request {{budget.request_total}} to expand mentoring to two new schools…", "base_hash": "sha256:a41f…"}
  ```

  `200` returns the updated `SectionView` (`source: "human"`, `status: "edited"`, or
  `"needs_review"` if checks find untraced numbers, new `version` and `content_hash`) plus the
  new `draft_hash`: `{"section": {…}, "draft_hash": "sha256:…"}`.

  | Status | Code | When |
  |---|---|---|
  | 403 | `forbidden` | |
  | 404 | `not_found` | framework or section not in the plan |
  | 409 | `stale_artifact` | with `current_hash` |
  | 409 | `draft_locked` | |
  | 409 | `draft_in_progress` | |
  | 422 | `validation_failed` | empty body, or over 20,000 chars |
  | 422 | `unknown_placeholder` | with `keys[]` |

  A save that changes nothing returns `200` with the same version.

- **Database** (`0800_narratives.sql`):

  ```sql
  CREATE TABLE narrative_draft_runs (
    run_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL REFERENCES tenants,
    framework_id   uuid NOT NULL REFERENCES frameworks,
    framework_hash text NOT NULL,
    status         text NOT NULL DEFAULT 'running'
                   CHECK (status IN ('running','succeeded','partial','budget_exceeded','failed')),
    section_ids    jsonb NOT NULL,
    completed_section_ids jsonb NOT NULL DEFAULT '[]',
    guidance       text,
    tokens_used    int NOT NULL DEFAULT 0,
    cost_usd       numeric(10,4) NOT NULL DEFAULT 0,
    model          text,
    error_code     text,
    requested_by   text NOT NULL,
    started_at     timestamptz NOT NULL DEFAULT now(),
    finished_at    timestamptz
  );
  CREATE UNIQUE INDEX narrative_one_running ON narrative_draft_runs (framework_id) WHERE status = 'running';

  CREATE TABLE narrative_sections (
    tenant_id      uuid NOT NULL REFERENCES tenants,
    framework_id   uuid NOT NULL REFERENCES frameworks,
    section_id     text NOT NULL,
    version        int  NOT NULL CHECK (version >= 1),
    title          text NOT NULL,
    body_md        text NOT NULL,
    placeholders   jsonb NOT NULL DEFAULT '[]',
    evidence_ids   jsonb NOT NULL DEFAULT '[]',
    findings       jsonb NOT NULL DEFAULT '[]',
    status         text NOT NULL CHECK (status IN ('drafted','edited','needs_review')),
    source         text NOT NULL CHECK (source IN ('ai','human','seed')),
    run_id         uuid REFERENCES narrative_draft_runs,
    content_hash   text NOT NULL,
    created_by     text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (framework_id, section_id, version)
  );
  ```

  RLS: `ENABLE` + `FORCE` + `tenant_isolation` policy (`tenant_id = current_tenant()`) on
  both tables, and `GRANT SELECT, INSERT, UPDATE ON … TO hope_app, hope_system`. Sections are
  append-only: there are no updates or deletes; the current version is the max `version`.

## Owns

```text
services/drafting/**                                   (pyproject, src/hope_drafting/{ports,plan,grounding,checks,placeholders,store,runner,settings,models,testing,demo}.py, tests/**)
services/pillar/src/hope_pillar/api/narratives.py
services/pillar/tests/snapshots/openapi/narratives.json
services/pillar/tests/test_narratives_api.py
apps/web/src/features/proposal/**
apps/web/src/api/proposal/**
apps/web/src/app/frameworks/[frameworkId]/draft/**
db/migrations/0800_narratives.sql
docs/specs/README.md (M6 status row only)
```

`hope_drafting` may import `hope_profile.memory` (read-only search) and `hope_budget`
(nothing else). If `uv.lock` changes, take main's version and rerun `uv lock`.

## Demo seed (`hope_drafting/demo.py:seed()`)

The seed is idempotent and makes no LLM calls.
- For M0's demo framework (`hope_core.demo.DEMO_FRAMEWORK_ID`, see Requests to M0), it
  inserts version 1 of the six default-plan sections (or the demo RFP's own sections when
  they exist), with `source = "seed"`, `status = "drafted"` and `created_by = "seed"`. The
  text is written from the demo profile (Riverbend Youth Alliance, the
  `hope_core.testing.factories.agency_profile`) and the demo opportunity ("Youth STEM
  Mentoring Demonstration Grants").
  - Budget figures use only `{{budget.request_total}}`, `{{budget.category.personnel}}`,
    `{{budget.indirect_total}}` and `{{budget.periods}}`.
  - Every number traces, so the seed has zero findings.
- It also inserts one `succeeded` run (`requested_by = "seed"`, `tokens_used = 0`).
- It skips with a log line when the framework doesn't exist, and does nothing when sections
  already exist.
- The demo's "Draft with AI" button always creates new versions on top of the seeded ones.

## Acceptance criteria

- [ ] AC1 `section_plan` returns the RFP's sections in order with their limits, or the six defaults when there are none.
- [ ] AC2 The prompt context contains only evidence items; RFP and memory text is wrapped with `untrusted`; no evidence item contains a money amount.
- [ ] AC3 Placeholders resolve from the latest ledger for every key in the vocabulary, including `budget.category.*` (request lines only); missing ledger → `[budget pending]` and `budget_ready: false`.
- [ ] AC4 `untraced_numbers` flags `$` amounts as `literal_money`, flags numbers not in the allowed set as `untraced_number`, and ignores placeholders and list markers (property test with random allowed sets).
- [ ] AC5 A section with findings is retried exactly once with the offending tokens listed; if still failing, it is saved `needs_review` with its findings and the run ends `partial`.
- [ ] AC6 `RunBudget` is enforced: a MockProvider that reports large token counts stops the run with `budget_exceeded`, keeps the completed sections, and records `tokens_used` and `cost_usd`.
- [ ] AC7 `draft_sections` persists one new version per section, returns them in plan order with correct `content_hash`, and is idempotent for the same `framework.content_hash` (no model call the second time).
- [ ] AC8 `POST .../draft` returns 202, runs in the background, and `GET` then shows the completed sections and run; a second POST while running returns `409 draft_in_progress`; a stuck run older than 10 minutes is treated as failed.
- [ ] AC9 `POST .../draft` with `section_ids` redrafts only those sections; an unknown id returns `400 unknown_section`; no ledger returns `409 budget_missing`.
- [ ] AC10 `PUT` with the current `base_hash` creates a human version and returns the new `draft_hash`; a stale `base_hash` returns `409 stale_artifact` with `current_hash`; an unknown placeholder returns `422 unknown_placeholder`.
- [ ] AC11 Drafts and edits return `409 draft_locked` once the workflow state is `Packaging` or later.
- [ ] AC12 Roles: `finance_director`, `executive_director` and `aor` can `GET` but get `403 forbidden` on `POST`/`PUT`.
- [ ] AC13 RLS: rows written for one tenant are invisible to another (`tenant_tx`).
- [ ] AC14 Every run and save writes the audit actions in Behaviour 13.
- [ ] AC15 `demo.seed()` is idempotent, makes no model call, and its sections have zero findings.
- [ ] AC16 With `HOPE_OPENAI_API_KEY` unset, the whole flow works with `MockProvider` (`mock_responder`); all tests run offline.
- [ ] AC17 The OpenAPI snapshot `narratives.json` matches; SC19's acceptance criteria pass.
- [ ] AC18 All CI commands in `AGENTS.md` pass.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/drafting/tests/test_plan.py::test_plan_from_rfp_and_defaults` | unit |
| AC2 | `tests/test_grounding.py::test_context_is_untrusted_and_moneyless` | unit |
| AC3 | `tests/test_placeholders.py::test_resolve_all_keys`, `::test_missing_ledger` | unit |
| AC4 | `tests/test_checks.py::test_number_trace` + `::test_number_trace_property` (hypothesis) | property |
| AC5 | `tests/test_runner.py::test_retry_once_then_needs_review` | unit |
| AC6 | `tests/test_runner.py::test_budget_exceeded_keeps_completed` | unit |
| AC7 | `tests/test_ports.py::test_draft_sections_persists_and_is_idempotent` | db |
| AC8 | `services/pillar/tests/test_narratives_api.py::test_draft_background_and_conflict` | api |
| AC9 | `test_narratives_api.py::test_redraft_subset_and_errors` | api |
| AC10 | `test_narratives_api.py::test_edit_hash_and_placeholders` | api |
| AC11 | `test_narratives_api.py::test_locked_after_packaging` | api |
| AC12 | `test_narratives_api.py::test_roles` | api |
| AC13 | `tests/test_store.py::test_rls_isolation` | db |
| AC14 | `tests/test_store.py::test_audit_actions` | db |
| AC15 | `tests/test_demo.py::test_seed_idempotent_and_clean` | db |
| AC16 | `tests/test_runner.py::test_mock_flow_offline` | unit |
| AC17 | `services/pillar/tests/test_openapi.py::test_router_snapshots[narratives]`, SC19 tests | api / unit |
| AC18 | CI | ci |

Commands: the CI commands in `AGENTS.md`, plus `pnpm --filter @hope/web test` and `pnpm --filter @hope/web build`.

## Requests to M0

1. **Shared demo ids.** Add `DEMO_AGENCY_ID`, `DEMO_OPPORTUNITY_ID` and `DEMO_FRAMEWORK_ID`
   constants to `hope_core/demo.py`, and make the seed runner call `hope_budget.demo` before
   `hope_drafting.demo`, so the demo framework and ledger exist first.
   Workaround if not added: the M6 seed looks up the newest `frameworks` row.
2. **Cost in the gateway.** Optionally give `RunBudget` a `max_cost_usd` and have
   `OpenAIProvider` report the real cost per call.
   Workaround: M6 estimates cost from tokens with `HOPE_DRAFTING_USD_PER_1K_TOKENS`.
3. **UI primitives.** `Toast` and `Drawer` (already in M0) are used by SC19. Also requested is
   a `MarkdownView` primitive (safe markdown rendering, no raw HTML) in `components/ui`.
   Workaround: a local renderer in `features/proposal/` using `react-markdown` with
   `skipHtml`. That adds a web dependency, so `pnpm-lock.yaml` changes.
4. **Nav.** M0's nav has no entry for `/frameworks/[id]/draft`. Users reach it from the
   workflow timeline (M4) and the budget screen (M5). Please make sure M4 and M5 link to
   `/frameworks/{framework_id}/draft`.
5. **Workflow (M4).** Pass the ledger to `draft_sections`, use the returned draft hash
   (`hope_drafting.ports.draft_hash(sections)`, also added in this spec) as the HITL-4
   artifact hash, and don't open HITL-4 while `ready` is false. Default if M4 can't: HITL-4
   opens anyway, and SC19 shows the findings.

## Out of scope

Collaborative or real-time editing, comments and track changes, rich-text (WYSIWYG) editing,
the claim and citation verifier (S18), style fine-tuning, multiple languages, PDF rendering
(M7), and section reordering.

## Decisions needed

- **Model.** Recommended default: `HOPE_OPENAI_MODEL=gpt-4o-mini` (M0's default) for speed
  and cost. `gpt-4o` can be set for the final demo run if the quality is worth about 15× the
  cost.
- **Per-draft cap.** Recommended default: $0.50 and 60k tokens. That covers about 3 full
  drafts' worth of headroom at gpt-4o-mini prices, and stops runaway retries.
- **Untraced numbers block HITL-4?** Recommended default: no for the MVP. They are shown as
  `needs_review` in SC19, and `ready: false` is exposed for M4.
- **Synchronous vs background drafting.** Recommended default: a background task plus polling,
  so a 30-60 s OpenAI run never hits an HTTP timeout. The run is lost if the API process
  restarts mid-run, but the 10-minute stale rule recovers it.

## References

- `packages/core/src/hope_core/model_gateway.py` (`ModelGateway.structured`, `RunBudget`, `untrusted`)
- `packages/core/src/hope_core/schemas/proposal_framework.py` (`BudgetLedger`, `Totals`, `LineItem`, `BudgetCategory`)
- `packages/core/src/hope_core/schemas/grant_opportunity.py` (`Requirements`, `RequirementSection`)
- `services/profile/src/hope_profile/memory.py` (`NarrativeMemory.search`)
- `services/workflow/src/hope_workflow/workflow.py` (`_draft_gate`, HITL-4 hash)
- `docs/specs/features/M0-mvp-scaffolding.md`
- OpenAI structured outputs: https://platform.openai.com/docs/guides/structured-outputs
