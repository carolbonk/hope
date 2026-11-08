"""Create or update the `hope_app` (RLS) and `hope_system` (BYPASSRLS) login roles.

Prints `export` lines for HOPE_DATABASE_URL / HOPE_DATABASE_SYSTEM_URL when they are unset,
built from HOPE_DATABASE_ADMIN_URL and HOPE_APP_DB_PASSWORD / HOPE_SYSTEM_DB_PASSWORD.
"""

import os
import shlex
import sys
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg import sql

ROLES = {
    "hope_app": ("HOPE_APP_DB_PASSWORD", "HOPE_DATABASE_URL", sql.SQL("NOBYPASSRLS")),
    "hope_system": ("HOPE_SYSTEM_DB_PASSWORD", "HOPE_DATABASE_SYSTEM_URL", sql.SQL("BYPASSRLS")),
}


def with_user(url: str, user: str, password: str) -> str:
    u = urlsplit(url)
    host = u.hostname or ""
    netloc = f"{user}:{quote(password, safe='')}@{host}" + (f":{u.port}" if u.port else "")
    return urlunsplit((u.scheme, netloc, u.path, u.query, u.fragment))


def main() -> None:
    admin = os.environ["HOPE_DATABASE_ADMIN_URL"]
    with psycopg.connect(admin, autocommit=True) as conn:
        for role, (pw_env, url_env, rls) in ROLES.items():
            if os.environ.get(url_env):
                continue
            password = os.environ.get(pw_env)
            if not password:
                sys.exit(f"set {url_env} or {pw_env}")
            exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
            verb = sql.SQL("ALTER" if exists else "CREATE")
            conn.execute(
                sql.SQL("{} ROLE {} LOGIN {} PASSWORD {}").format(
                    verb, sql.Identifier(role), rls, sql.Literal(password)
                )
            )
            print(f"export {url_env}={shlex.quote(with_user(admin, role, password))}")


if __name__ == "__main__":
    main()
