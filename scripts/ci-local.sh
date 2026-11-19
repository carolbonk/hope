#!/usr/bin/env bash
# Runs the same checks as .github/workflows/ci.yml on this machine, for when
# GitHub Actions is unavailable. Paste the summary into the PR as check evidence.
# Usage:
#   pnpm ci:local                # check the current checkout
#   pnpm ci:local --pr 92        # check PR #92; check out its head first
#                                # (gh pr checkout 92) or the script refuses
#   pnpm ci:local --skip-python  # typescript job only (no Docker needed)
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

pr=''
skip_python=0
while [ $# -gt 0 ]; do
  case "$1" in
    --pr) pr="$2"; shift 2 ;;
    --skip-python) skip_python=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ -n "$pr" ]; then
  head_sha=$(gh pr view "$pr" --json headRefOid --jq .headRefOid) || { echo "Could not read PR $pr via gh" >&2; exit 2; }
  if [ "$(git rev-parse HEAD)" != "$head_sha" ]; then
    echo "HEAD is not PR $pr's head ($head_sha). Check out PR $pr's head first (gh pr checkout $pr)." >&2
    exit 2
  fi
fi

logs="${TMPDIR:-/tmp}/hope-ci-local"
rm -rf "$logs" && mkdir -p "$logs"
results=()
failed=0

step() {
  local name="$1"; shift
  printf '%-22s ' "$name"
  if "$@" >"$logs/$name.log" 2>&1; then
    echo pass; results+=("pass  $name")
  else
    echo "FAIL (log: $logs/$name.log)"; results+=("FAIL  $name"); failed=1
    tail -n 20 "$logs/$name.log" | sed 's/^/    /'
  fi
}
skip() { printf '%-22s skipped (%s)\n' "$1" "$2"; results+=("skip  $1"); }

containers=()
cleanup() { [ ${#containers[@]} -gt 0 ] && docker rm -f "${containers[@]}" >/dev/null 2>&1; }
trap cleanup EXIT INT TERM
suffix=$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')

# Throwaway pgvector Postgres on :5432, as in CI (some tests hard-code that port).
# It refuses to run over a local dev database instead of touching it.
postgres() {
  local name="hope-ci-pg-$suffix" port=5432
  if (exec 3<>/dev/tcp/127.0.0.1/$port) 2>/dev/null; then
    echo "Port $port is in use. Stop the dev database first: docker compose -f infra/docker-compose.yml stop postgres"
    return 1
  fi
  docker run -d --rm --name "$name" -p 127.0.0.1:$port:5432 \
    -e POSTGRES_USER=hope -e POSTGRES_PASSWORD=hope -e POSTGRES_DB=hope \
    pgvector/pgvector:pg16 >/dev/null || return 1
  containers+=("$name")
  for _ in $(seq 1 60); do
    docker exec "$name" pg_isready -U hope -d hope -h 127.0.0.1 >/dev/null 2>&1 && break
    sleep 1
  done
  docker exec -i "$name" psql -v ON_ERROR_STOP=1 -U hope -d hope <infra/postgres/init-roles.sql || return 1
  export HOPE_DATABASE_URL="postgresql://hope_app:hope_app@127.0.0.1:$port/hope"
  export HOPE_DATABASE_SYSTEM_URL="postgresql://hope_system:hope_system@127.0.0.1:$port/hope"
  export HOPE_DATABASE_ADMIN_URL="postgresql://hope:hope@127.0.0.1:$port/hope"
}

# Tests expect Kafka on localhost:19092; reuse a running broker there, else start one.
redpanda() {
  if (exec 3<>/dev/tcp/127.0.0.1/19092) 2>/dev/null; then echo "reusing broker on :19092"; return 0; fi
  local name="hope-ci-redpanda-$suffix"
  docker run -d --rm --name "$name" -p 19092:19092 redpandadata/redpanda:v24.2.7 \
    redpanda start --mode=dev-container --smp=1 \
    --kafka-addr=internal://0.0.0.0:9092,external://0.0.0.0:19092 \
    --advertise-kafka-addr=internal://localhost:9092,external://localhost:19092 >/dev/null || return 1
  containers+=("$name")
  for _ in $(seq 1 30); do
    docker exec "$name" rpk cluster health | grep -q 'Healthy:.*true' && return 0
    sleep 2
  done
  return 1
}

schemas_fresh() { uv run hope-export-schemas && git diff --exit-code packages/schemas/json; }
ts_types_fresh() { pnpm --filter @hope/schemas run gen && git diff --exit-code packages/schemas/ts; }

# python job
if [ "$skip_python" = 1 ]; then
  for s in python:services python:sync python:ruff-format python:ruff-check python:mypy python:migrate python:pytest python:schemas-fresh; do
    skip "$s" '--skip-python'
  done
else
  # postgres exports the DB URLs, so it runs in this shell rather than through step's redirect subshell.
  printf '%-22s ' python:services
  if postgres >"$logs/python-services.log" 2>&1 && redpanda >>"$logs/python-services.log" 2>&1; then
    echo pass; results+=("pass  python:services")
    if step python:sync uv sync --all-packages --frozen; then
      step python:ruff-format uv run ruff format --check .
      step python:ruff-check uv run ruff check .
      step python:mypy uv run mypy packages/core/src services
      if step python:migrate uv run hope-migrate; then
        step python:pytest uv run pytest -q
      else
        skip python:pytest 'migrate failed'
      fi
      step python:schemas-fresh schemas_fresh
    else
      for s in python:ruff-format python:ruff-check python:mypy python:migrate python:pytest python:schemas-fresh; do skip "$s" 'sync failed'; done
    fi
  else
    echo "FAIL (log: $logs/python-services.log)"; results+=("FAIL  python:services"); failed=1
    tail -n 20 "$logs/python-services.log" | sed 's/^/    /'
  fi
fi

# typescript job
if step ts:install pnpm install --frozen-lockfile; then
  step ts:typecheck pnpm -r --if-present run typecheck
  step ts:lint pnpm -r --if-present run lint
  step ts:test pnpm -r --if-present run test
  step ts:types-fresh ts_types_fresh
else
  for s in ts:typecheck ts:lint ts:test ts:types-fresh; do skip "$s" 'install failed'; done
fi

echo; echo "ci-local @ $(git rev-parse --short HEAD)${pr:+ (PR #$pr)}"
printf '%s\n' "${results[@]}"
exit "$failed"
