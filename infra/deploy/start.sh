#!/bin/sh
# Container entrypoint: database roles, migrations, optional demo login, then the API.
set -eu
: "${HOPE_DATABASE_ADMIN_URL:=${DATABASE_URL:?set DATABASE_URL or HOPE_DATABASE_ADMIN_URL}}"
export HOPE_DATABASE_ADMIN_URL
eval "$(python infra/deploy/roles.py)"
hope-migrate
if [ "${HOPE_SEED_DEMO:-}" = "1" ]; then hope-demo-seed; fi
exec uvicorn hope_pillar.api:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips '*'
