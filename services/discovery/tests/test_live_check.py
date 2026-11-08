from __future__ import annotations

from typing import Any

import pytest
from hope_core.model_gateway import MockProvider, ModelGateway
from hope_core.web import FetchError, Page
from hope_discovery import live_check, mock
from hope_discovery.mock import ScriptedWeb


class _Blocked(ScriptedWeb):
    def fetch(self, url: str) -> Page:
        if "ncwmedicalfund" in url:
            raise FetchError("http_403", url)
        return super().fetch(url)


def test_run_reports_grants_and_fetch_failures() -> None:
    out = live_check.run(ModelGateway([mock.register(MockProvider())]), _Blocked())
    titles = {g["title"] for g in out["grants"]}
    assert "Rural Oral Health Access Grant 2027" in titles
    assert "Mobile Health Equipment Fund" not in titles
    assert {"url": mock.MOBILE, "code": "http_403"} in out["failures"]
    text = live_check.report(out)
    assert "http_403: " in text and "ncwmedicalfund.example.org (http_403)" in text
    assert f"{out['complete']} complete cards" in text


def test_main_needs_a_key(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setattr(
        live_check, "default_gateway", lambda: ModelGateway([mock.register(MockProvider())])
    )
    assert live_check.main([]) == 2
    assert "HOPE_OPENAI_API_KEY" in capsys.readouterr().err
