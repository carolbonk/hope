"""OpenAI provider for `ModelGateway` (H0 section 7, M1), over plain httpx."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from hope_core.model_gateway import Message, ModelTier
from hope_core.settings import HopeSettings

log = logging.getLogger("hope_core.model_calls")

OPENAI_BASE_URL = "https://api.openai.com/v1"
# USD per 1M tokens (input, output), for the log line's estimate only.
_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "text-embedding-3-small": (0.02, 0.0),
}


class ProviderError(RuntimeError):
    pass


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price_in, price_out = _PRICES.get(model, _PRICES["gpt-4o-mini"])
    return (prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000


class OpenAIClient:
    """POSTs JSON to OpenAI; retries 429 and 5xx twice with backoff, nothing else."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = OPENAI_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        backoff: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=60.0,
        )
        self._backoff = backoff
        self._sleep = sleep

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(3):
            response = self._client.post(path, json=body)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    self._sleep(self._backoff * 2**attempt)
                    continue
                raise ProviderError(f"openai {path} returned {response.status_code}")
            if response.is_error:
                raise ProviderError(f"openai {path} returned {response.status_code}")
            data: dict[str, Any] = response.json()
            return data
        raise ProviderError(f"openai {path} failed")  # pragma: no cover


class OpenAIProvider:
    name = "openai"

    def __init__(
        self, client: OpenAIClient, *, model: str, embed_model: str = "text-embedding-3-small"
    ) -> None:
        self.client = client
        self.model = model
        self.embed_model = embed_model

    @classmethod
    def from_settings(
        cls,
        settings: HopeSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        backoff: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> OpenAIProvider:
        if not settings.openai_api_key:
            raise ValueError("HOPE_OPENAI_API_KEY is not set")
        client = OpenAIClient(
            settings.openai_api_key, transport=transport, backoff=backoff, sleep=sleep
        )
        return cls(client, model=settings.openai_model, embed_model=settings.openai_embed_model)

    def model_for(self, tier: ModelTier) -> str:
        return self.model  # FRONTIER, MID and SMALL all map to `openai_model`

    def complete_json(
        self, tier: ModelTier, messages: list[Message], schema: dict[str, Any]
    ) -> tuple[dict[str, Any], int]:
        model = self.model_for(tier)
        title = str(schema.get("title", "Response"))
        raw = self.client.post(
            "/chat/completions",
            {
                "model": model,
                "temperature": 0,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": title, "schema": schema},
                },
            },
        )
        usage = raw.get("usage") or {}
        tokens = int(usage.get("total_tokens", 0))
        cost = estimate_cost(
            model, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        )
        log.info(
            "model_call schema=%s model=%s tokens=%d cost_usd=%.6f", title, model, tokens, cost
        )
        content = raw["choices"][0]["message"].get("content") or ""
        data = json.loads(content)
        if not isinstance(data, dict):
            raise json.JSONDecodeError("expected a JSON object", content, 0)
        return data, tokens

    def embed(self, texts: list[str]) -> list[list[float]]:
        raw = self.client.post("/embeddings", {"model": self.embed_model, "input": texts})
        return [list(map(float, item["embedding"])) for item in raw["data"]]
