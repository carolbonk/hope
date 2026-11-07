# Folder map

The target layout once `S00` has merged. Each path has exactly one owner. A spec may change
only the paths in its `Owns` list; everything else goes through the wave's contracts spec
(`S00`, `C2`, `C3`, `C4`).

```text
hope/
├── AGENTS.md                         orchestrator: repo rules and commands
├── docs/
│   ├── architecture/blueprint.md     orchestrator
│   └── specs/                        orchestrator (each spec PR updates only its own status row)
├── packages/
│   ├── core/src/hope_core/           contracts specs only (S00, C2-C4)
│   │   ├── schemas/                  every shared contract (Pydantic) -> JSON Schema -> TS
│   │   ├── auth.py                   Principal + get_principal dependency (S00); OIDC verifier (S01)
│   │   ├── outbox.py                 transactional outbox helper (S00)
│   │   ├── claimcheck.py             payload_ref put/get helper (S00)
│   │   ├── errors.py                 problem+json error model, StaleArtifactError (S00)
│   │   ├── providers/                real LLM + embedding providers (S16)
│   │   └── telemetry/                OpenTelemetry setup, cost metering hooks (S29)
│   └── schemas/                      generated, never hand-edited
├── db/migrations/                    one file per spec, number reserved in docs/specs/README.md
├── services/
│   ├── pillar/src/hope_pillar/
│   │   ├── api/__init__.py           app factory; mounts every router below (S00)
│   │   ├── api/me.py, users.py       S01
│   │   ├── api/approvals.py          S02
│   │   ├── api/opportunities.py      S03 (ingest routes stay in api/ingest.py, pillar)
│   │   ├── api/workflows.py          S04
│   │   ├── api/matrix.py             S05
│   │   ├── api/frameworks.py         S06
│   │   ├── api/rules.py              S08
│   │   ├── api/agencies.py           mounts hope_profile.api (S00); S09 extends via hope_profile
│   │   ├── api/parse_reviews.py      S10
│   │   ├── api/notifications.py      S12
│   │   ├── api/audit.py              S13
│   │   ├── api/narratives.py         S17
│   │   ├── api/verification.py       S18
│   │   ├── api/compliance.py         S19
│   │   ├── api/integrations.py       S24
│   │   ├── api/packages.py           S21, then S22
│   │   └── api/awards.py             S23
│   │   (tests/snapshots/openapi/<router>.json: one OpenAPI snapshot per router, S00)
│   ├── ingestion/                    S10, S11, then S14 (connectors/usaspending.py), S27 (connectors/portals/)
│   ├── profile/                      S09, then S15 (sources/irs.py)
│   ├── matching/                     S05, then S08, S14 (features/past_awards.py)
│   ├── budget/                       S06, then S25 (resolver adapter only)
│   ├── workflow/                     S04 (projection), S07 (adapters/), S23 (postaward/)
│   ├── notifications/                S12, then S26 (calendar/)              [skeleton by S00]
│   ├── drafting/                     S17                                    [skeleton by S00]
│   ├── verification/                 S18                                    [skeleton by S00]
│   ├── compliance/                   S19                                    [skeleton by S00]
│   ├── packaging/                    S21                                    [skeleton by S00]
│   ├── submission/                   S22                                    [skeleton by S00]
│   ├── integrations/                 S24 (framework, crm/), S25 (erp/)      [skeleton by S00]
│   └── awards/                       S23                                    [skeleton by S00]
├── apps/web/src/
│   ├── app/<route>/page.tsx          thin route file; renders features/<feature>/<Screen>
│   ├── features/<feature>/           one folder per screen group (see SCREENS.md)
│   ├── api/client.ts                 composes the per-feature clients (S00)
│   ├── api/<feature>/                types.ts, http.ts, fixture.ts, *.test.ts per feature (S00 splits today's api/)
│   ├── components/ui/                shared liquid-glass primitives (contracts specs only)
│   ├── nav.ts                        every nav entry, pre-filled by S00; features don't edit it
│   └── lib/                          shared helpers (contracts specs only)
└── infra/
    ├── docker-compose.yml            orchestrator
    ├── terraform/                    S28
    ├── observability/                S29
    └── security/                     S30
```

## Web feature folders

| Folder | Screens | Spec |
|---|---|---|
| `features/session` | SC01, SC17 | S01 |
| `features/dashboard` | SC02 | S31 |
| `features/matrix` | SC03 | S05 |
| `features/opportunities` | SC04 | S03 |
| `features/approvals` | SC05, SC06 | S02 |
| `features/workflow` | SC07, SC08 | S04 |
| `features/profile` | SC09, SC10 | S09 |
| `features/onboarding` | SC11 | S09 |
| `features/parse-review` | SC12 | S10 |
| `features/budget` | SC13 | S06 |
| `features/rules` | SC14 | S08 |
| `features/audit` | SC15 | S13 |
| `features/notifications` | SC16 | S12 |
| `features/integrations` | SC18 | S24 |
| `features/proposal` | SC19, SC21 | S20 |
| `features/compliance` | SC20 | S19 |
| `features/packages` | SC22 | S21 (S22 adds its submission panel later) |
| `features/awards` | SC23 | S23 |
