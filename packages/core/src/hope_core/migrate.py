"""Minimal ordered SQL migration runner.

Files in db/migrations are applied in lexical order and recorded in `schema_migrations`.
Number ranges are reserved per owner (see AGENTS.md) so parallel PRs never collide.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import psycopg

from hope_core.settings import get_settings

DEFAULT_DIR = Path(__file__).resolve().parents[4] / "db" / "migrations"


def apply_migrations(url: str, directory: Path = DEFAULT_DIR) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " name text PRIMARY KEY, checksum text NOT NULL,"
            " applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {
            row[0]: row[1]
            for row in conn.execute("SELECT name, checksum FROM schema_migrations").fetchall()
        }
        for path in sorted(directory.glob("*.sql")):
            sql = path.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            if path.name in done:
                if done[path.name] != checksum:
                    raise RuntimeError(f"{path.name} changed after it was applied; add a new file")
                continue
            with conn.transaction():
                conn.execute(sql.encode())
                conn.execute(
                    "INSERT INTO schema_migrations (name, checksum) VALUES (%s, %s)",
                    (path.name, checksum),
                )
            applied.append(path.name)
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Hope SQL migrations")
    parser.add_argument("--url", default=get_settings().database_admin_url)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    for name in apply_migrations(args.url, args.dir):
        print(f"applied {name}")


if __name__ == "__main__":
    main()
