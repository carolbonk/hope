# Hope API (FastAPI + in-process job workers). The web app deploys separately (docs/deploy.md).
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.7.9 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services ./services
COPY db ./db
COPY contracts/mocks/w2/profile.put ./contracts/mocks/w2/profile.put
COPY infra/deploy ./infra/deploy
RUN uv sync --frozen --no-dev --package hope-pillar
ENV PATH=/app/.venv/bin:$PATH
EXPOSE 8000
CMD ["sh", "infra/deploy/start.sh"]
