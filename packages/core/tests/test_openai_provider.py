from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
from hope_core.model_gateway import (
    BudgetExceededError,
    Message,
    MockProvider,
    ModelGateway,
    ModelOutputError,
    ModelTier,
    RunBudget,
    default_gateway,
)
from hope_core.openai_provider import OpenAIProvider
from hope_core.settings import HopeSettings
from pydantic import BaseModel

FIXTURES = Path(__file__).parent / "fixtures" / "openai"
SECRET = "Riverbend private mission text"


class NteeSuggestionOut(BaseModel):
    codes: list[str]
    rationale: str


def fixture(name: str) -> httpx.Response:
    data = json.loads((FIXTURES / f"{name}.json").read_text())
    return httpx.Response(data["status"], json=data["body"])


def replay(*names: str) -> tuple[httpx.MockTransport, list[dict[str, Any]]]:
    queue = list(names)
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return fixture(queue.pop(0) if len(queue) > 1 else queue[0])

    return httpx.MockTransport(handler), seen


def gateway(transport: httpx.MockTransport) -> ModelGateway:
    settings = HopeSettings(openai_api_key="sk-test")
    provider = OpenAIProvider.from_settings(settings, transport=transport, sleep=lambda _s: None)
    return ModelGateway([provider])


def messages() -> list[Message]:
    return [Message("system", "Suggest NTEE codes."), Message("user", SECRET)]


def test_default_gateway_without_key() -> None:
    gw = default_gateway(HopeSettings(openai_api_key=None))
    assert [type(p) for p in gw.providers] == [MockProvider]
    with_key = default_gateway(HopeSettings(openai_api_key="sk-test"))
    assert [type(p) for p in with_key.providers] == [OpenAIProvider]


def test_structured_validates() -> None:
    transport, seen = replay("chat_ok")
    out = gateway(transport).structured(ModelTier.MID, messages(), NteeSuggestionOut)
    assert out == NteeSuggestionOut(
        codes=["E32", "F30"], rationale="Community clinic with behavioral health programs."
    )
    body = seen[0]
    assert body["model"] == "gpt-4o-mini" and body["temperature"] == 0
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "NteeSuggestionOut"
    assert body["response_format"]["json_schema"]["schema"] == NteeSuggestionOut.model_json_schema()


def test_invalid_output_retries_then_raises() -> None:
    transport, seen = replay("chat_invalid")
    with pytest.raises(ModelOutputError) as err:
        gateway(transport).structured(ModelTier.SMALL, messages(), NteeSuggestionOut)
    assert err.value.schema_title == "NteeSuggestionOut"
    assert len(seen) == 2

    transport, seen = replay("chat_invalid", "chat_ok")
    assert gateway(transport).structured(ModelTier.SMALL, messages(), NteeSuggestionOut).codes
    assert len(seen) == 2


def test_schema_mismatch_retries_then_raises() -> None:
    class Other(BaseModel):
        required_field: int

    transport, seen = replay("chat_ok")
    with pytest.raises(ModelOutputError):
        gateway(transport).structured(ModelTier.SMALL, messages(), Other)
    assert len(seen) == 2


def test_invalid_output_counts_toward_the_budget() -> None:
    transport, seen = replay("chat_invalid", "chat_ok")
    budget = RunBudget(max_calls=1)
    with pytest.raises(BudgetExceededError):
        gateway(transport).structured(ModelTier.SMALL, messages(), NteeSuggestionOut, budget)
    assert len(seen) == 2 and budget.calls == 2 and budget.tokens == 300


def test_429_retries() -> None:
    transport, seen = replay("chat_429", "chat_429", "chat_ok")
    assert gateway(transport).structured(ModelTier.MID, messages(), NteeSuggestionOut).codes
    assert len(seen) == 3

    transport, seen = replay("chat_429")
    with pytest.raises(RuntimeError, match="all model providers failed"):
        gateway(transport).structured(ModelTier.MID, messages(), NteeSuggestionOut)
    assert len(seen) == 3


def test_400_is_not_retried() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "bad"}})

    calls: list[int] = []
    with pytest.raises(RuntimeError):
        gateway(httpx.MockTransport(handler)).structured(
            ModelTier.MID, messages(), NteeSuggestionOut
        )
    assert len(calls) == 1


def test_no_mock_fallback() -> None:
    gw = default_gateway(HopeSettings(openai_api_key="sk-test"), transport=replay("chat_429")[0])
    assert not any(isinstance(p, MockProvider) for p in gw.providers)
    gw.providers[0].client._sleep = lambda _s: None  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError):
        gw.structured(ModelTier.MID, messages(), NteeSuggestionOut)


def test_log_has_no_message_text(caplog: pytest.LogCaptureFixture) -> None:
    transport, _ = replay("chat_ok")
    with caplog.at_level(logging.DEBUG):
        gateway(transport).structured(ModelTier.MID, messages(), NteeSuggestionOut)
    lines = [r.getMessage() for r in caplog.records if r.name == "hope_core.model_calls"]
    assert len(lines) == 1
    assert "schema=NteeSuggestionOut" in lines[0] and "model=gpt-4o-mini" in lines[0]
    assert "tokens=150" in lines[0] and "cost_usd=" in lines[0]
    all_text = " ".join(r.getMessage() for r in caplog.records)
    assert SECRET not in all_text and "Suggest NTEE" not in all_text and "E32" not in all_text


def test_embed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["model"] == "text-embedding-3-small"
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]})

    gw = gateway(httpx.MockTransport(handler))
    assert gw.embed(["hello"]) == [[0.1, 0.2]]
