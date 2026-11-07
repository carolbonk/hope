"""Persist sealed ledgers through `hope_core.db.tenant_tx` (RLS enforced)."""

from __future__ import annotations

from uuid import UUID

import psycopg
from hope_core.hashing import canonical_json
from hope_core.schemas.proposal_framework import BudgetLedger

from hope_budget.engine import is_sealed

Cursor = psycopg.Cursor[dict[str, object]]


class LedgerIntegrityError(ValueError):
    pass


def save_ledger(
    cur: Cursor, tenant_id: UUID, ledger: BudgetLedger, framework_id: UUID | None = None
) -> None:
    if not is_sealed(ledger):
        raise LedgerIntegrityError(f"ledger {ledger.ledger_id} is not sealed by the engine")
    cur.execute(
        "INSERT INTO budget_ledgers"
        " (ledger_id, tenant_id, framework_id, engine_version, ledger, content_hash)"
        " VALUES (%s, %s, %s, %s, %s::jsonb, %s) ON CONFLICT (ledger_id) DO NOTHING",
        (
            ledger.ledger_id,
            tenant_id,
            framework_id,
            ledger.engine_version,
            canonical_json(ledger),
            ledger.ledger_id,
        ),
    )


def load_ledger(cur: Cursor, ledger_id: str) -> BudgetLedger | None:
    cur.execute("SELECT ledger FROM budget_ledgers WHERE ledger_id = %s", (ledger_id,))
    row = cur.fetchone()
    if row is None:
        return None
    ledger = BudgetLedger.model_validate(row["ledger"])
    if not is_sealed(ledger):
        raise LedgerIntegrityError(f"stored ledger {ledger_id} fails its content hash")
    return ledger
