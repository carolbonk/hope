# M5: Budget (hackathon MVP)

| | |
|---|---|
| Wave | MVP (runs in parallel with M1-M4, M6, M7 after M0) |
| Depends on | M0 |
| Screens | SC13 |
| Migrations | `db/migrations/0510_budget_mvp.sql` (range 0510-0519) |
| Blueprint | 2.2 A7, 4.4 (HITL-2), 5.4, 8.1 |
| Replaces for the MVP | S06 (the full version stays on `specs/budget` for later) |
| Status | Draft |

## Goal

After the GO decision, Hope drafts a budget for the pursuit. The demo shows that every
dollar comes from a named source: a salary band, a quote, or the agency's NICRA.

The Finance director then uses SC13 to:
- see that the budget fits the funder's limits;
- adjust quantities or effort inline (never amounts);
- approve and lock it at HITL-2.

All money is computed by the existing deterministic Budget Engine (`hope_budget`). The LLM
only proposes structure, and a deterministic template guarantees a budget even without an
OpenAI key.

## Current state

On `main` after M0:

- **Engine and helpers.** `services/budget/src/hope_budget/`:
  - `engine.py`: `BudgetEngine(ctx).compute(lines) -> BudgetLedger`, `validate()`, `ProposedLine`, `BudgetContext`, `BudgetInputError`, `seal()`, `is_sealed()`.
  - `solver.py`: `fit_budget(lines, ctx, policy) -> BudgetSolution` (OR-Tools).
  - `framework.py`: `FrameworkGenerator.draft()`, which raises `MissingCeilingError` and `FrameworkNeedsReviewError`.
  - `store.py`: `save_ledger` / `load_ledger`.
  - `resolver.py`: `CostBasisResolver` and `InMemoryCostBasisResolver`.
  - `rules.py`: `AgencyRates`, `BudgetRules`.
  - `numeric.py`: the reconciler, used by M6.
  - `testing.py`: sample records.
- **Tests.** 93 offline tests (golden, Hypothesis, solver, A7 with `MockProvider`).
- **Port.** M0 adds `hope_budget/ports.py` with
  `compute_for_framework(framework_id: UUID) -> BudgetLedger`, which raises `NotImplementedError`.
- **Contracts.** M0 adds `ProposalFramework.drafted_by: str` and `BudgetLedger.content_hash: str`.
- **Tables.**
  - `frameworks` and `budget_ledgers` (in `0001_core.sql`, RLS) exist, but nothing writes `frameworks`.
  - `0500_budget_ledgers_immutable.sql` makes ledgers append-only.
  - There is no cost-basis table, so the engine only runs in tests.
- **Pillar.** M0 moves the framework routes into `services/pillar/src/hope_pillar/api/frameworks.py`:
  - `GET /v1/frameworks/{framework_id}`, which returns `FrameworkView` from `hope_pillar.api.models`;
  - `POST /v1/frameworks/{framework_id}/recompute`, which is a 501 stub.
- **Workflow.**
  - `hope_workflow.workflow.LifecycleWorkflow._budget_signoff` opens HITL-2 with `artifact_hash = framework.content_hash`.
  - It forbids `drafted_by` as the approver unless `small_org_ack` is set.
  - If a decision's hash differs from the open request, it re-opens the request with the same hash.
  - On `approve` it sets its in-memory copy to `approved_locked`. Any other decision returns to `Planning`.
- **Web.** `apps/web/src/app/frameworks/[frameworkId]/budget/page.tsx` is a `ComingSoon`
  placeholder, and `apps/web/src/api/budget/` is an empty client from M0.

## Behaviour

### Demo data

1. **`hope_budget/demo.py:seed()`** is idempotent (upserts by key). It writes the cost
   basis and agency rates in the "Demo seed data" table below, for `HOPE_TENANT_ID` and
   `HOPE_AGENCY_ID`. It creates no framework.

### Rates and cost basis

2. **`hope_budget/cost_basis.py`.**
   - `PostgresCostBasisResolver(cur)` implements `CostBasisResolver`:
     - `resolve(ref)` returns the `CostBasisRecord` stored under `ref`, or `None`.
     - `catalog()` returns all records, sorted by `ref`.
   - `upsert_cost_basis(cur, record)` updates the record in place. A record without
     provenance raises `BudgetInputError`. The ledger keeps the rate actually used
     (`LineItem.basis.unit_rate_minor`), so the MVP does not need cost-basis history.
3. **Agency rates.**
   - `load_agency_rates(cur, agency_id) -> AgencyRates` reads `budget_agency_rates` (seeded by M5).
   - If there is no row, it falls back to `AgencyRates.from_profile(<latest profile>)`.
   - Rates without provenance still fail in the engine (existing check).

### Drafting a framework (called by M4 after GO)

4. **`hope_budget/service.py:draft_framework(opportunity_id, agency_id, workflow_id, drafted_by) -> ProposalFramework`**
   (also exposed as a port, see Requests to M0):
   1. If a framework already exists for `(opportunity_id, agency_id)`, return it unchanged.
      This makes workflow retries and double clicks safe.
   2. Load the current opportunity version (`opportunity_versions` via `opportunities.current_version`)
      and the latest `agency_profile_versions` row.
   3. Build the context:
      - `BudgetContext(resolver=PostgresCostBasisResolver, agency=load_agency_rates(...), rules=BudgetRules.from_funding(opportunity.funding))`;
      - `periods = ceil(project_period_months / 12)`, or 1 if that is unknown.
   4. **Structure source.**
      - With `HOPE_OPENAI_API_KEY` set, call `FrameworkGenerator(default_gateway(), resolver).draft(...)`.
        If it raises `FrameworkNeedsReviewError`, a provider error, or a timeout (20 s), fall
        back to the template.
      - Without a key, use the template directly.

      The template is `demo_structure(opportunity, profile, catalog) -> FrameworkStructure`:
      - the 7 standard lines in "Golden demo budget";
      - one goal and one objective, from the profile's first active program;
      - KPI `baseline_ref` set to that program's first outcome `metric_id`, or `None`;
      - `project_title` = `"{program.name}: {opportunity.title}"`, truncated to 120 characters.

      Template lines are run through the same `validate()` and `fit_budget()` as LLM lines.
      `framework.extra.structure_source` is `"llm"` or `"template"`, plus
      `structure_fallback_reason` when the template was a fallback.
   5. **Missing ceiling.** If `funding.award_ceiling` is null, run without a ceiling check
      (`FrameworkGenerator.draft(..., require_ceiling=False)`, a new keyword in M5's own
      `framework.py`) and set `extra.warnings = ["no_award_ceiling"]`.
   6. **Persist** in one `tenant_tx`:
      - `save_ledger`;
      - insert the `frameworks` row: `version=1`, `status='draft'`, framework JSON with
        `drafted_by` and `extra.proposed_lines` (the `ProposedLine` list), and `content_hash = framework_hash(...)`;
      - an `audit_log` row: `action="budget.drafted"`, `subject="framework:{id}"`,
        `detail={structure_source, request_minor}`.

### Port

5. **`hope_budget/ports.py:compute_for_framework(framework_id) -> BudgetLedger`**:
   1. Load the framework and its `proposed_lines`.
   2. Recompute with the current rates, profile and opportunity (`BudgetEngine.compute`, no solver).
   3. If the new `ledger_id` equals the stored one, return the stored ledger.
   4. Otherwise save the new ledger and update the framework in place: `version+1`, new
      `budget`, new `content_hash`, `updated_at`. `drafted_by` is unchanged. Return the new ledger.

   Errors: `FrameworkNotFoundError(LookupError)`; `BudgetInputError` (for example, a
   deleted cost-basis ref); `FrameworkLockedError` (the framework is approved and locked).

### Lock (derived, no consumer)

6. A framework is **locked** when `approvals` has a row with `gate='HITL-2'`,
   `decision='approve'` and `artifact_hash = frameworks.content_hash`. The pillar's
   existing `_decide` writes this row.
   - `load_framework` checks this and, on first sight, sets `frameworks.status='approved_locked'`
     in the same transaction.
   - Edits and recompute on a locked framework raise `FrameworkLockedError` (HTTP 409 `framework_locked`).

### Reading

7. `GET /v1/frameworks/{framework_id}/budget` returns `BudgetView`:
   - the framework header: id, version, status, `content_hash`, `drafted_by`, `updated_at`,
     project title, structure source and warnings;
   - an opportunity summary;
   - the workflow (`workflow_id` and `state` from `tenant_opportunity` for the same
     opportunity and agency, or `null`);
   - the open HITL-2 gate (`pillar_gate_requests` with `workflow_id`, gate `HITL-2`,
     `status='open'`), or `null`;
   - the latest HITL-2 approval (`approvals`) if any;
   - the ledger;
   - `proposed_lines`;
   - `sources`: the record behind every ref used, plus the agency rates as
     `profile:financials.*` pseudo-sources with their provenance;
   - `catalog`: all cost-basis records, used by "Add line";
   - `rates_changed`: lines whose `unit_rate_minor` differs from the current record;
   - `missing_refs`;
   - `solver` (from `extra.solver`);
   - `permissions` (step 10).

### Editing

8. `PUT /v1/frameworks/{framework_id}/budget/lines` runs these checks in order:
   1. 404 `not_found`.
   2. 403 `forbidden` unless the caller has `Role.finance_director` or `Role.admin`.
   3. 409 `framework_locked`.
   4. 409 `stale_artifact` (with `current_hash`) if `base_hash != content_hash`.
   5. 409 `invalid_state` (with `state`) if a workflow exists and its state is not
      `Planning` or `AwaitingBudgetSignoff`.
   6. 422 `validation_error` from the body model. `BudgetLineEdit` has no amount or rate
      fields and uses `extra="forbid"`.
   7. Engine `validate()`: on errors, 422 `budget_input_invalid` with
      `errors[{line_id|null, message}]`. A message belongs to a `line_id` when it starts
      with `line <id>:`.
   8. Compute:
      - `fit=false`: `BudgetEngine.compute`.
      - `fit=true`: `fit_budget`, with every line that differs from the stored line forced
        to `locked=True`, so the solver never undoes the user's edit.
   9. If the `ledger_id` and lines are identical to the stored ones, return 200 with
      `changed: false` and write nothing.
   10. Otherwise update in place (`version+1`, new `content_hash`,
       `drafted_by = caller.user_id`, `extra.solver` from the fit or reset to no
       adjustments), save the ledger, and write an `audit_log` row
       `budget.lines_edited {previous_hash, new_hash, changed_line_ids, comment}`.
       Return 200 with `changed: true`.

   The open HITL-2 gate still holds the old hash. SC13 therefore sends `request_changes`
   with the old hash right after saving ("Save and send for re-approval"). The workflow
   goes back to `Planning`, and M4 re-opens HITL-2 with the new hash (Requests to M0, item 3).

### Recompute

9. `POST /v1/frameworks/{framework_id}/recompute` is synchronous. It calls
   `compute_for_framework` and returns 200 `BudgetView` with `changed`.
   - Roles: `finance_director`, `admin`.
   - Errors: 409 `framework_locked`; 422 `budget_input_invalid`.
   - It does not emit an event (this replaces S00 step 11 for the MVP).

### Permissions

10. `BudgetView.permissions`:
    - `can_edit`: the role check, not locked, and the state check pass.
    - `can_decide`: there is an open gate; the caller has a role in `gate.approver_roles`;
      and `caller.user_id != drafted_by`.
    - `decide_blocked_reason`: `"no_open_gate" | "not_an_approver" | "you_drafted_this" | "locked" | null`.
    - `requires_step_up: true`.

    The workflow still enforces separation of duties itself. This field only drives the UI.

### Other rules

11. **No LLM in any endpoint.** The only model call is in step 4, and only with a key.
    Tests always use `MockProvider` or the template.
12. **Single tenant.** Every query runs in `tenant_tx(HOPE_TENANT_ID)`, and there are no
    tenant parameters anywhere.

## Contracts

- **Shared models used:**
  - `hope_core.schemas.proposal_framework`: `ProposalFramework`, `BudgetLedger`,
    `LineItem`, `LineItemBasis`, `CapCheck`, `Totals`, `Scope`.
  - `hope_core.schemas.hitl`: `Gate`, `HitlDecision`.
  - `hope_core.auth`: `Role`, `Principal`, `require_roles`.
  - `hope_core.schemas.common.Provenance`, `hope_core.money.Money`,
    `hope_core.model_gateway.default_gateway`.
- **Service-local** (in `hope_budget`, imported by the pillar router):
  - `api_models.py`: `BudgetView`, `BudgetLinesEdit`, `BudgetLineEdit`, `CostBasisView`,
    `GateSummary`, `Permissions`.
  - `contracts.py`: `CostBasisRecord`, kept where it is (M0 does not promote it).
- **Events:** none in the MVP.

### Endpoints

All of these are in `services/pillar/src/hope_pillar/api/frameworks.py` under `/v1`.
Errors are `application/problem+json` with `code`. Roles come from M0's `Role` enum, and
the dev principal comes from `X-Hope-User` / `X-Hope-Roles`.

**`GET /v1/frameworks/{framework_id}`** (unchanged from today: `FrameworkView`). Any role.
Codes: 404 `not_found`.

**`GET /v1/frameworks/{framework_id}/budget`.** Any role. Codes: 200; 404 `not_found`.

```json
{
  "framework_id": "6f1c2b9e-1d1a-4c55-9a51-2f0c8f1e7a10",
  "version": 1,
  "status": "draft",
  "content_hash": "sha256:4b1e9c0d…",
  "drafted_by": "demo-development",
  "updated_at": "2026-11-08T14:02:11Z",
  "project_title": "Mentor Futures: Youth Mentoring Expansion",
  "structure_source": "template",
  "structure_fallback_reason": null,
  "warnings": [],
  "opportunity": {
    "opportunity_id": "0d0b7c8e-5f8a-4a3e-9d43-1b2c3d4e5f60",
    "title": "Youth Mentoring Expansion",
    "funder_name": "DOJ OJJDP",
    "award_ceiling": {"amount_minor": 25000000, "currency": "USD"},
    "award_floor": {"amount_minor": 5000000, "currency": "USD"},
    "application_due": "2026-12-03T23:59:00-05:00"
  },
  "workflow": {"workflow_id": "wf-0d0b7c8e", "state": "AwaitingBudgetSignoff"},
  "gate": {
    "request_id": "9a7e4c1b-2222-4c55-8a51-0f0c8f1e7a11",
    "status": "open",
    "artifact_hash": "sha256:4b1e9c0d…",
    "approver_roles": ["finance_director"],
    "due_at": "2026-11-11T14:02:11Z",
    "requested_at": "2026-11-08T14:02:15Z"
  },
  "approval": null,
  "ledger": {
    "ledger_id": "sha256:91ab…", "computed_by": "budget-engine", "engine_version": "hope-budget-engine/0.1.0",
    "currency": "USD", "periods": 1,
    "line_items": [
      {"line_id": "L1", "category": "personnel", "description": "Program Director", "period": 1,
       "basis": {"cost_basis_ref": "hris:position:PD-01", "quantity": "1", "unit": "year",
                 "unit_rate_minor": 7800000, "effort_pct_bps": 2000},
       "amount_minor": 1560000, "funding_source": "request",
       "justification": "Oversees the expansion and partner relations", "allowability": "allowable"},
      {"line_id": "L1-fringe", "category": "fringe", "description": "Fringe benefits on L1", "period": 1,
       "basis": {"cost_basis_ref": "profile:financials.fringe_rate_bps", "quantity": "0.28", "unit": "rate",
                 "unit_rate_minor": 1560000, "effort_pct_bps": null},
       "amount_minor": 436800, "funding_source": "request", "justification": null, "allowability": "allowable"},
      {"line_id": "indirect-p1", "category": "indirect", "description": "Indirect costs, period 1", "period": 1,
       "basis": {"cost_basis_ref": "profile:financials.indirect_rate", "quantity": "0.2", "unit": "rate",
                 "unit_rate_minor": 18831300, "effort_pct_bps": null},
       "amount_minor": 3766260, "funding_source": "request", "justification": null, "allowability": "allowable"}
    ],
    "totals": {"direct_minor": 21231300, "mtdc_base_minor": 18831300, "indirect_minor": 3766260,
               "request_minor": 24997560, "cost_share_minor": 0, "project_total_minor": 24997560},
    "cap_checks": [
      {"rule": "award_ceiling", "limit_minor": 25000000, "actual_minor": 24997560, "status": "adjusted",
       "adjustment_note": "L5 quantity 60 -> 41 (fit under limits)"},
      {"rule": "award_floor", "limit_minor": 5000000, "actual_minor": 24997560, "status": "pass", "adjustment_note": null},
      {"rule": "indirect_cap", "limit_minor": 3766260, "actual_minor": 3766260, "status": "pass", "adjustment_note": null},
      {"rule": "unallowable_cost", "limit_minor": 0, "actual_minor": 0, "status": "pass", "adjustment_note": null}
    ],
    "sf424a_mapping": {"5e_federal": 24997560, "5f_non_federal": 0, "5g_total": 24997560,
      "6a_personnel": 12260000, "6b_fringe_benefits": 3432800, "6c_travel": 290000, "6d_equipment": 0,
      "6e_supplies": 348500, "6f_contractual": 4000000, "6g_construction": 0, "6h_other": 900000,
      "6i_total_direct_charges": 21231300, "6j_indirect_charges": 3766260, "6k_totals": 24997560},
    "content_hash": "sha256:91ab…"
  },
  "proposed_lines": [
    {"line_id": "L5", "category": "supplies", "description": "Mentoring curriculum kits", "period": 1,
     "basis": {"cost_basis_ref": "catalog:supplies:curriculum-kit", "quantity": "41"},
     "funding_source": "request", "justification": "One kit per mentee", "locked": false,
     "min_effort_bps": null, "min_quantity": "20", "quantity_step": "1"}
  ],
  "sources": [
    {"ref": "hris:position:PD-01", "kind": "salary", "description": "Program Director", "unit": "year",
     "unit_rate": {"amount_minor": 7800000, "currency": "USD"}, "fringe_rate_bps": null,
     "provenance": {"source": "user_input", "source_ref": "2026 salary bands (HR)",
                    "captured_at": "2026-10-01T00:00:00Z", "verified_by": "demo-finance", "confidence": null}},
    {"ref": "profile:financials.indirect_rate", "kind": "rate", "description": "NICRA 20% of MTDC (HHS CAS)",
     "unit": "rate", "unit_rate": null, "rate_bps": 2000,
     "provenance": {"source": "document_extraction", "source_ref": "NICRA letter, HHS CAS, 2025-07-01 to 2027-06-30",
                    "captured_at": "2026-10-01T00:00:00Z", "verified_by": "demo-finance", "confidence": 1.0}}
  ],
  "catalog": ["…every CostBasisView, same shape as sources"],
  "rates_changed": [],
  "missing_refs": [],
  "solver": {"feasible": true, "unresolved": [],
             "adjustments": [{"line_id": "L5", "change": "quantity", "before": "60", "after": "41", "reason": "fit under limits"}]},
  "permissions": {"can_edit": true, "can_decide": true, "decide_blocked_reason": null, "requires_step_up": true},
  "changed": null
}
```

(Line items are abridged here. The real response lists all 11 lines; see "Golden demo budget".)

`sources[]` entries with `kind: "rate"` are the agency rates (`profile:financials.fringe_rate_bps`,
`profile:financials.indirect_rate`). They have `rate_bps` instead of `unit_rate`.

**`PUT /v1/frameworks/{framework_id}/budget/lines`.** Roles: `finance_director`, `admin`.

```json
{
  "base_hash": "sha256:4b1e9c0d…",
  "fit": false,
  "comment": "Cut PD effort to 15%, restore all 60 kits",
  "lines": [
    {"line_id": "L1", "category": "personnel", "description": "Program Director", "period": 1,
     "cost_basis_ref": "hris:position:PD-01", "quantity": "1", "effort_pct_bps": 1500,
     "funding_source": "request", "justification": "Oversees the expansion and partner relations", "locked": true},
    {"line_id": "L5", "category": "supplies", "description": "Mentoring curriculum kits", "period": 1,
     "cost_basis_ref": "catalog:supplies:curriculum-kit", "quantity": "60",
     "funding_source": "request", "justification": "One kit per mentee", "locked": false}
  ]
}
```

- `lines` is the full desired set of direct lines (1 to 50). Fringe and indirect are always derived.
- `BudgetLineEdit` fields: `line_id` (`^[A-Za-z0-9_-]{1,32}$`, unique); `category`
  (`personnel|travel|equipment|supplies|contractual|construction|other`); `description?`
  (<= 200); `period` (>= 1); `cost_basis_ref`; `quantity` (decimal string >= 0);
  `effort_pct_bps?` (0-10000, personnel only); `funding_source`
  (`request|cost_share_cash|cost_share_in_kind`); `justification?` (<= 2000); `locked`
  (default false); `min_effort_bps?`; `min_quantity?`; `quantity_step?`.
- `comment` is <= 2000 characters.

Responses:
- 200 `BudgetView` with `changed: true|false`.
- 403 `forbidden`.
- 404 `not_found`.
- 409 `stale_artifact`: `{"code":"stale_artifact","current_hash":"sha256:…"}`.
- 409 `framework_locked`.
- 409 `invalid_state`: `{"code":"invalid_state","state":"Drafting"}`.
- 422 `validation_error`, for example an `amount_minor` field.
- 422 `budget_input_invalid`:

```json
{"type": "about:blank", "title": "Budget input invalid", "status": 422, "code": "budget_input_invalid",
 "errors": [{"line_id": "L8", "message": "line L8: cost_basis_ref quote:Q-9 does not resolve"},
            {"line_id": "L1", "message": "line L1: personnel needs effort_pct_bps between 0 and 10000"}]}
```

**`POST /v1/frameworks/{framework_id}/recompute`.** Roles: `finance_director`, `admin`. No body.
- 200 `BudgetView` (`changed: true|false`).
- 404 `not_found`; 409 `framework_locked`; 422 `budget_input_invalid`; 403 `forbidden`.

**Cost-basis endpoints:** not built for the MVP. Rates come from the seed, and SC13 reads
them from `BudgetView.sources` and `catalog` (see Decisions).

### Database: `db/migrations/0510_budget_mvp.sql`

```sql
CREATE TABLE cost_basis_records (
  tenant_id     uuid NOT NULL REFERENCES tenants,
  ref           text NOT NULL CHECK (ref ~ '^[a-z]+:[A-Za-z0-9:._-]{1,120}$'),
  record        jsonb NOT NULL,                 -- CostBasisRecord
  content_hash  text NOT NULL,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, ref),
  CHECK (jsonb_typeof(record->'provenance') = 'object')
);

CREATE TABLE budget_agency_rates (
  tenant_id   uuid NOT NULL REFERENCES tenants,
  agency_id   uuid NOT NULL REFERENCES agencies,
  rates       jsonb NOT NULL,                   -- AgencyRates, provenance required
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, agency_id),
  CHECK (jsonb_typeof(rates->'provenance') = 'object')
);

ALTER TABLE frameworks ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE frameworks DROP CONSTRAINT frameworks_opportunity_id_agency_id_version_key;
CREATE UNIQUE INDEX frameworks_one_per_pursuit ON frameworks (tenant_id, opportunity_id, agency_id);
```

- RLS: enable and force a `tenant_isolation` policy (`tenant_id = current_tenant()`) on both
  new tables, using the `DO $$` loop pattern from `0300_profile.sql`.
- Grants: `SELECT, INSERT, UPDATE` to `hope_app` and `hope_system`.
- The constraint name in the `DROP` line must be checked against the live schema. If it
  differs, use `ALTER TABLE … DROP CONSTRAINT IF EXISTS` on the real name.

### Demo seed data (`hope_budget/demo.py:seed()`)

All entries have `provenance.captured_at = 2026-10-01T00:00:00Z` and `verified_by = "demo-finance"`.

| ref | kind | description | unit | rate | provenance (`source`, `source_ref`) |
|---|---|---|---|---|---|
| `hris:position:PD-01` | salary | Program Director | year | $78,000.00 | `user_input`, "2026 salary bands (HR)" |
| `hris:position:PM-02` | salary | Program Manager | year | $65,000.00 | `user_input`, "2026 salary bands (HR)" |
| `hris:position:YM-03` | salary | Youth Mentor | year | $42,000.00 | `user_input`, "2026 salary bands (HR)" |
| `quote:travel:conf-trip` | unit_cost | Conference trip (airfare, 2 nights, per diem) | trip | $1,450.00 | `user_input`, "GSA per diem FY26 + fare quote" |
| `catalog:supplies:curriculum-kit` | unit_cost | Mentoring curriculum kit | kit | $85.00 | `user_input`, "Vendor quote MK-2291" |
| `unit:participant:stipend` | participant_support | Participant stipend | participant | $150.00 | `user_input`, "Board stipend policy 2026" |
| `subaward:evaluation:UCLA-EVAL` | subaward | External evaluation (university partner) | award | $40,000.00 | `user_input`, "Signed letter of intent" |

Agency rates (`budget_agency_rates`):
- `fringe_rate_bps = 2800`, with provenance `user_input`, "2026 benefits summary".
- `indirect_type = "negotiated_nicra"`, `indirect_rate_bps = 2000`, `indirect_base = "MTDC"`,
  with provenance `document_extraction`, "NICRA letter, HHS CAS, 2025-07-01 to 2027-06-30",
  `confidence = 1.0`.

### Golden demo budget (template structure, hand-computed)

Rules: $250,000 ceiling, $50,000 floor, NICRA 20% on MTDC, fringe 28%, 1 period.

| Line | Basis | Amount |
|---|---|---|
| L1 personnel PD-01 | $78,000 × 1 × 20% | $15,600.00 |
| L1-fringe | 28% of $15,600 | $4,368.00 |
| L2 personnel PM-02 | $65,000 × 1 × 100% | $65,000.00 |
| L2-fringe | 28% | $18,200.00 |
| L3 personnel YM-03 | $42,000 × 2 × 50% | $42,000.00 |
| L3-fringe | 28% | $11,760.00 |
| L4 travel | $1,450 × 2 | $2,900.00 |
| L5 supplies | $85 × 60 | $5,100.00 |
| L6 other (participant support) | $150 × 60 | $9,000.00 (excluded from MTDC) |
| L7 contractual subaward | $40,000 × 1 | $40,000.00 (only $25,000 counts toward MTDC) |
| **Direct** | | **$213,928.00** |
| MTDC | 156,928 + 2,900 + 5,100 + 25,000 | $189,928.00 |
| indirect-p1 | 20% of MTDC | $37,985.60 |
| **Request (engine only)** | | **$251,913.60**: over the ceiling by $1,913.60, so `award_ceiling` fails |

`fit_budget` then cuts non-personnel quantities first. Against today's engine it picks L5 60 -> 41 kits (checked locally)
(-$1,615 direct, -$323 indirect), which gives a request of **$249,975.60** and marks
`award_ceiling` `adjusted`. The test asserts the invariants (request <= ceiling, no
personnel line changed, every adjustment recomputed through the engine), not the exact
solver choice. The engine-only figures above are asserted exactly.

## Owns

```text
services/budget/** (except the signatures in services/budget/src/hope_budget/ports.py; M5 implements their bodies)
  incl. src/hope_budget/{cost_basis,service,api_models,demo}.py, ports.py bodies, framework.py (require_ceiling), tests/**
services/pillar/src/hope_pillar/api/frameworks.py
services/pillar/tests/test_frameworks_api.py
services/pillar/tests/snapshots/openapi/frameworks.json
apps/web/src/features/budget/**
apps/web/src/api/budget/**
apps/web/src/app/frameworks/[frameworkId]/budget/**
db/migrations/0510_budget_mvp.sql
```

## Acceptance criteria

- [ ] AC1 `seed()` writes the 7 records and the agency rates; running it twice changes nothing; every record has provenance.
- [ ] AC2 `PostgresCostBasisResolver` resolves seeded refs, returns `None` for unknown refs, and rejects writes without provenance (code and table `CHECK`).
- [ ] AC3 RLS hides cost-basis records and agency rates of another tenant.
- [ ] AC4 `draft_framework` without an OpenAI key builds the template budget, fits it under the ceiling, and persists the framework (version 1, `drafted_by`, `proposed_lines`, `structure_source="template"`) plus its ledger.
- [ ] AC5 `draft_framework` is idempotent: a second call returns the same framework and writes nothing.
- [ ] AC6 With a mocked LLM that keeps returning invalid refs, `draft_framework` falls back to the template and records `structure_fallback_reason`; with a valid mocked LLM response it uses `structure_source="llm"`.
- [ ] AC7 With no award ceiling, the draft succeeds without an `award_ceiling` check and has `warnings=["no_award_ceiling"]`.
- [ ] AC8 Golden: the engine-only template ledger equals the hand-computed table exactly (direct $213,928.00, MTDC $189,928.00, indirect $37,985.60, request $251,913.60, SF-424A lines); the fitted ledger has a request <= $250,000 with `award_ceiling` `adjusted` and no personnel line changed.
- [ ] AC9 `compute_for_framework` returns the stored ledger when nothing changed, and bumps the version with a new hash after a seeded rate changes.
- [ ] AC10 `GET …/budget` returns every field in the example, including `sources` with provenance, `catalog`, the open gate and `permissions`.
- [ ] AC11 `PUT …/budget/lines` recomputes through the engine, increments the version, changes `content_hash`, and sets `drafted_by` to the editor; an identical body returns `changed: false` and writes nothing.
- [ ] AC12 A line with `amount_minor` or `unit_rate_minor` is rejected with 422 and nothing is written.
- [ ] AC13 Conflicts: a stale `base_hash` returns 409 `stale_artifact` with `current_hash`; locked returns 409 `framework_locked`; state `Drafting` returns 409 `invalid_state`; a caller without `finance_director` or `admin` gets 403.
- [ ] AC14 Engine validation errors return 422 `budget_input_invalid` with each error attributed to its `line_id`.
- [ ] AC15 `fit: true` never changes a line the user edited in the same request.
- [ ] AC16 After an approved HITL-2 `approvals` row with the current hash exists, the budget reads as `approved_locked`, and edit and recompute return 409 `framework_locked`.
- [ ] AC17 `permissions` is correct for each case: approver who isn't the drafter; the drafter; a non-approver; no open gate; locked.
- [ ] AC18 `POST …/recompute` is synchronous and returns `changed` correctly.
- [ ] AC19 Every SC13 acceptance criterion passes.
- [ ] AC20 All CI commands in `AGENTS.md` pass, and the `frameworks.json` snapshot is updated.

## Test plan

| AC | Test (file::name) | Type |
|---|---|---|
| AC1 | `services/budget/tests/test_demo_seed.py::test_seed_idempotent_with_provenance` | db |
| AC2 | `services/budget/tests/test_cost_basis_store.py::test_resolver_and_provenance` | db |
| AC3 | `test_cost_basis_store.py::test_rls_isolation` | db |
| AC4 | `services/budget/tests/test_service.py::test_draft_template_without_key` | db |
| AC5 | `test_service.py::test_draft_idempotent` | db |
| AC6 | `test_service.py::test_llm_fallback_to_template`, `::test_llm_structure_used` (MockProvider) | db |
| AC7 | `test_service.py::test_draft_without_ceiling_warns` | db |
| AC8 | `services/budget/tests/test_demo_golden.py::test_template_engine_golden`, `::test_template_fitted_invariants` | unit |
| AC9 | `services/budget/tests/test_ports.py::test_compute_for_framework_unchanged_and_bumped` | db |
| AC10 | `services/pillar/tests/test_frameworks_api.py::test_get_budget_view` | api |
| AC11 | `test_frameworks_api.py::test_put_lines_new_version`, `::test_put_lines_identical_unchanged` | api |
| AC12 | `test_frameworks_api.py::test_amount_fields_rejected` | api |
| AC13 | `test_frameworks_api.py::test_edit_conflicts` (parametrized: stale, locked, state, role) | api |
| AC14 | `test_frameworks_api.py::test_budget_input_invalid` | api |
| AC15 | `services/budget/tests/test_edit.py::test_fit_keeps_edited_lines` | unit |
| AC16 | `test_frameworks_api.py::test_lock_derived_from_approval` | api |
| AC17 | `test_frameworks_api.py::test_permissions_matrix` | api |
| AC18 | `test_frameworks_api.py::test_recompute_sync` | api |
| AC19 | see `screens/SC13-budget-review.md` | unit |
| AC20 | CI | ci |

Commands: the CI commands in `AGENTS.md`, plus `UPDATE_SNAPSHOTS=1 uv run pytest services/pillar/tests/test_openapi.py`
after a route change. Web: `pnpm --filter @hope/web test`.

## Requests to M0

1. **Add a port for drafting.** Add
   `hope_budget.ports.draft_framework(opportunity_id: UUID, agency_id: UUID, workflow_id: str, drafted_by: str) -> ProposalFramework`
   next to `compute_for_framework`. M4 calls it after GO. Fallback if this isn't done: M4
   imports `hope_budget.service.draft_framework` (same signature).
2. **`HitlRequest.framework_id: UUID | None = None`.** This lets the approval inbox (M3)
   link a HITL-2 request to `/frameworks/{id}/budget`. M4 sets it when it opens HITL-2.
   Fallback: SC06 links through the workflow, and the workflow screen links to the budget.
3. **For M4 (workflow wiring):**
   - In `Planning`, if a framework already exists, call `compute_for_framework(framework_id)`
     instead of re-drafting. Then open HITL-2 with the current `frameworks.content_hash`.
     This is how an inline edit, followed by `request_changes`, gets a fresh gate.
   - After HITL-2 `approve`, pass the current stored framework to the narrative step, not
     the workflow's in-memory copy.
4. **Persona switcher.** HITL-2 forbids the drafter as the approver. The demo user acts as
   both the GO decider (`drafted_by`) and the Finance director, so the role switcher must
   also switch `X-Hope-User` (for example `demo-development`, `demo-finance`, `demo-exec`,
   `demo-aor`). Fallback: M4 starts demo workflows with `small_org_ack=true`.
5. `hope_pillar` needs to depend on `hope-budget` (`services/pillar/pyproject.toml`, `uv.lock`).
6. Add the problem codes `framework_locked`, `budget_input_invalid` and `invalid_state` to `apps/web/src/lib/problem.ts`.
7. Recompute is synchronous in M5 (200 `BudgetView`), so M0 should not build the S00
   step-11 event or 202 response for `POST /v1/frameworks/{id}/recompute`.
8. Move `StepUpDialog` from `features/approvals` to `components/ui` so SC13 and SC06 share
   one. Fallback: SC13 imports it from `@/features/approvals/StepUpDialog` without editing it.

## Out of scope

- Cost-basis editing UI and endpoints, ERP/HRIS sync, cost-basis history.
- Multi-period editing UI (the engine supports it; the template uses 1 period).
- Cost-share-required funders beyond showing the check.
- Category and period caps.
- Scope (goals/KPIs) editing.
- Events and consumers (`framework.drafted`, `framework.locked`).
- CFO threshold routing.

## Decisions needed

1. **Cost-basis endpoints.** Default: skip for the MVP (seed only). Add
   `GET/PUT /v1/cost-basis` later from S06.
2. **Framework versioning.** Default: update one `frameworks` row in place (stable
   `framework_id` for M3/M6/M7 links). History lives in the append-only `budget_ledgers`
   and `audit_log`.
3. **Agency rates source.** Default: M5's `budget_agency_rates` (seeded) wins over the
   profile's `financials`, so the demo is deterministic. The profile is the fallback.
4. **Missing ceiling.** Default: draft without the ceiling check and show a warning, rather
   than blocking (blueprint 8.5 says block). This keeps the live Grants.gov demo from dead-ending.
5. **Who can edit.** Default: `finance_director` and `admin`.
6. **Seed a demo framework?** Default: no. The framework is created by the real flow
   (Pursue -> GO -> M4 -> `draft_framework`).

## References

- `services/budget/src/hope_budget/{engine,solver,framework,store,rules,testing}.py`, `tests/test_engine_golden.py`
- `services/workflow/src/hope_workflow/workflow.py` (`_plan_budget`, `_budget_signoff`, `_gate`)
- `services/pillar/src/hope_pillar/api/routes.py` (`_decide`, `get_framework`, `recompute_framework`), split by M0
- `db/migrations/0001_core.sql`, `0100_pillar.sql`, `0500_budget_ledgers_immutable.sql`
- Full roadmap version: `docs/specs/features/S06-budget-api-and-hitl2-review.md` on `specs/budget`
- Blueprint 2.2 A7, 4.4, 5.4, 8.1; 2 CFR 200.1 (MTDC), 200.414 (indirect)
