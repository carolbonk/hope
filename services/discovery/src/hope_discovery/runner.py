"""Starting a discovery job and running it (H2 section A step 5)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from hope_core.model_gateway import MockProvider, ModelGateway, default_gateway
from hope_core.web import RealWebTools, WebTools

from hope_discovery import mock
from hope_discovery.agent import DiscoveryAgent
from hope_discovery.grantsgov import GrantsGovWeb
from hope_discovery.repo import DbRepo


def offline_tools() -> tuple[ModelGateway, WebTools]:
    return ModelGateway([mock.register(MockProvider())]), mock.recorded_web()


def default_tools() -> tuple[ModelGateway, WebTools]:
    """OpenAI + live web when a key is set; otherwise the recorded demo fixtures."""
    gateway = default_gateway()
    if any(isinstance(p, MockProvider) for p in gateway.providers):
        return offline_tools()
    return gateway, GrantsGovWeb(RealWebTools())


def run_discovery(job_id: UUID) -> dict[str, Any]:
    gateway, web = default_tools()
    return DiscoveryAgent(DbRepo(), gateway, web).run(job_id)
