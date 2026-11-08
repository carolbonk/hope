"""ModelGateway: logical model tiers mapped to providers (blueprint 2.3).

Agents call `gateway.structured(...)` with a Pydantic response model and never parse free
text. `MockProvider` makes every agent runnable and testable without an API key.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    import httpx

    from hope_core.settings import HopeSettings


class ModelTier(StrEnum):
    FRONTIER = "frontier"
    MID = "mid"
    SMALL = "small"
    EMBED = "embed"
    RERANK = "rerank"


class BudgetExceededError(RuntimeError):
    pass


class NoResponderError(LookupError):
    """MockProvider has no responder for the schema: a test bug, so it never fails over."""


class InvalidOutputError(ValueError):
    """A provider call succeeded (and cost `tokens`) but its content wasn't a JSON object."""

    def __init__(self, tokens: int = 0) -> None:
        super().__init__("model output is not a JSON object")
        self.tokens = tokens


class ModelOutputError(ValueError):
    """The model returned invalid structured output twice in a row."""

    def __init__(self, schema_title: str) -> None:
        super().__init__(f"invalid model output for {schema_title}")
        self.schema_title = schema_title


@dataclass
class RunBudget:
    """Per-run ceilings (blueprint 8.5). Exceeding one stops the run for human review."""

    max_calls: int = 50
    max_tokens: int = 200_000
    calls: int = 0
    tokens: int = 0

    def charge(self, tokens: int) -> None:
        self.calls += 1
        self.tokens += tokens
        if self.calls > self.max_calls or self.tokens > self.max_tokens:
            raise BudgetExceededError(f"calls={self.calls} tokens={self.tokens}")


@dataclass
class Message:
    role: str
    content: str


class Provider(Protocol):
    name: str

    def complete_json(
        self, tier: ModelTier, messages: list[Message], schema: dict[str, Any]
    ) -> tuple[dict[str, Any], int]: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


T = TypeVar("T", bound=BaseModel)
Responder = Callable[[list[Message], dict[str, Any]], dict[str, Any]]


@dataclass
class MockProvider:
    """Deterministic provider. Register a responder per response schema title."""

    name: str = "mock"
    dim: int = 64
    responders: dict[str, Responder] = field(default_factory=dict)

    def register(self, model: type[BaseModel], responder: Responder) -> None:
        self.responders[model.__name__] = responder

    def complete_json(
        self, tier: ModelTier, messages: list[Message], schema: dict[str, Any]
    ) -> tuple[dict[str, Any], int]:
        title = str(schema.get("title", ""))
        if title not in self.responders:
            raise NoResponderError(f"MockProvider has no responder for {title!r}")
        tokens = sum(len(m.content) for m in messages) // 4 + 1
        return self.responders[title](messages, schema), tokens

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.lower().encode()).digest()
            raw = [(digest[i % len(digest)] / 255.0) - 0.5 for i in range(self.dim)]
            norm = sum(x * x for x in raw) ** 0.5 or 1.0
            vectors.append([x / norm for x in raw])
        return vectors


class ModelGateway:
    def __init__(self, providers: list[Provider]) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self.providers = providers

    def structured(
        self,
        tier: ModelTier,
        messages: list[Message],
        response_model: type[T],
        budget: RunBudget | None = None,
    ) -> T:
        schema = response_model.model_json_schema()
        last_error: Exception | None = None
        for provider in self.providers:
            for _attempt in range(2):
                try:
                    data, tokens = provider.complete_json(tier, messages, schema)
                except (NoResponderError, BudgetExceededError):
                    raise
                except (InvalidOutputError, json.JSONDecodeError) as exc:
                    if budget is not None:  # the call happened, so it counts
                        budget.charge(getattr(exc, "tokens", 0))
                    continue  # invalid JSON from the model: retry once
                except Exception as exc:  # provider down: fail over to the next provider
                    last_error = exc
                    break
                if budget is not None:
                    budget.charge(tokens)
                try:
                    return response_model.model_validate(data)
                except ValidationError:
                    continue
            else:
                raise ModelOutputError(str(schema.get("title", response_model.__name__)))
        raise RuntimeError("all model providers failed") from last_error

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.providers[0].embed(texts)


def default_gateway(
    settings: HopeSettings | None = None, transport: httpx.BaseTransport | None = None
) -> ModelGateway:
    """OpenAI when `HOPE_OPENAI_API_KEY` is set, otherwise the mock. Never both."""
    from hope_core.settings import get_settings

    settings = settings or get_settings()
    if settings.openai_api_key:
        from hope_core.openai_provider import OpenAIProvider

        return ModelGateway([OpenAIProvider.from_settings(settings, transport=transport)])
    return ModelGateway([MockProvider()])


def untrusted(text: str, label: str = "document") -> str:
    """Wrap ingested content as data, never instructions (blueprint 8.3)."""
    safe = text.replace("</untrusted", "&lt;/untrusted")
    return f'<untrusted kind="{label}">\n{safe}\n</untrusted>'


def as_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)
