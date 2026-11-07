"""Postgres helpers. Tenant isolation is enforced by RLS on `app.tenant_id` (db/migrations)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from hope_core.settings import get_settings


def connect(url: str | None = None) -> psycopg.Connection[dict[str, object]]:
    return psycopg.connect(url or get_settings().database_url, row_factory=dict_row)


@contextmanager
def tenant_tx(
    conn: psycopg.Connection[dict[str, object]], tenant_id: UUID | str
) -> Iterator[psycopg.Cursor[dict[str, object]]]:
    """Open a transaction scoped to one tenant. RLS policies read `app.tenant_id`."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        yield cur
