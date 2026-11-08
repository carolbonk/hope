# `make demo`: Postgres only, migrations, demo seed, then the API (:8000) and the web app (:3000).
# Runs offline on MockProvider and recorded web fixtures unless OPENAI_API_KEY or HOPE_OPENAI_API_KEY is set.
# The API reads HOPE_OPENAI_API_KEY and the web draft route reads OPENAI_API_KEY; each falls back to the other.
SHELL := /bin/bash

.PHONY: demo
demo:
	docker compose -f infra/docker-compose.yml up -d --wait postgres
	uv run hope-migrate
	uv run hope-demo-seed
	@set -a; source .env; set +a; \
	export HOPE_COOKIE_SECURE=false; \
	export HOPE_OPENAI_API_KEY="$${HOPE_OPENAI_API_KEY:-$${OPENAI_API_KEY:-}}"; \
	export OPENAI_API_KEY="$${OPENAI_API_KEY:-$${HOPE_OPENAI_API_KEY}}"; \
	trap 'kill 0' EXIT; \
	uv run uvicorn hope_pillar.api:app --port 8000 & \
	NEXT_PUBLIC_HOPE_API_URL=http://localhost:8000 pnpm --filter @hope/web dev & \
	echo "Hope: http://localhost:3000  (demo@hope.org / hope-demo)"; \
	wait
