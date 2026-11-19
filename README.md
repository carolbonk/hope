<p align="center">
  <img src="docs/assets/hope-banner.png" alt="hope — Your AI grant team. From discovery to submission, built for nonprofits." width="100%">
</p>

<p align="center">
  <a href="https://hope-carolbonk.vercel.app/"><img alt="Try Hope" src="https://img.shields.io/badge/Try_Hope-live_app-2f6b4f?style=for-the-badge"></a>
  <a href="https://www.youtube.com/watch?v=O9q-CR2DaNc"><img alt="Watch the walkthrough on YouTube" src="https://img.shields.io/badge/Watch-the_walkthrough-ff0000?style=for-the-badge&logo=youtube&logoColor=white"></a>
</p>

# Hope

Multi-agent grant automation platform for non-profits. Specialist agents discover and parse
grant opportunities, score them against an agency's mission and capacity, build compliant
budgets, and draft applications. Humans approve every commitment through explicit
approval gates.

- Architecture: [`docs/architecture/blueprint.md`](docs/architecture/blueprint.md)
- Working rules and folder ownership: [`AGENTS.md`](AGENTS.md)

## Watch the walkthrough

<p align="center">
  <a href="https://www.youtube.com/watch?v=O9q-CR2DaNc">
    <img src="https://img.youtube.com/vi/O9q-CR2DaNc/maxresdefault.jpg" alt="Watch the Hope walkthrough on YouTube" width="720">
  </a>
  <br>
  <sub>Click to watch on YouTube</sub>
</p>

## Quick start

```bash
pip install uv            # or see https://docs.astral.sh/uv/
uv sync --all-packages
pnpm install
docker compose -f infra/docker-compose.yml up -d   # Postgres+pgvector, Redpanda, Redis, Temporal, MinIO
uv run hope-migrate
uv run pytest -q
```

## Stack

Python 3.12 (Pydantic, FastAPI, Temporal, LangGraph-style agents behind `ModelGateway`),
Postgres 16 with RLS and pgvector, Kafka API (Redpanda locally), Redis, S3 (MinIO locally),
Next.js for the web app. Pydantic models in `hope_core.schemas` are the single source of truth
for contracts; JSON Schema and TypeScript types are generated from them.

## License

Proprietary. Copyright (c) 2026 Carolaine Bonk. All rights reserved. See [LICENSE](LICENSE).
