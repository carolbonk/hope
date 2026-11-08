"""Export contracts to packages/schemas/json (one file per model + a bundle for TS codegen)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from hope_core.envelope import PillarEnvelope
from hope_core.schemas import (
    AgencyProfile,
    Citation,
    DiscoveryJob,
    DiscoveryProgress,
    GrantCandidate,
    GrantOpportunity,
    HitlDecision,
    HitlRequest,
    MeView,
    OpportunityMatrix,
    ProposalFramework,
    UserView,
)

SCHEMA_BASE = "https://schemas.hope.dev"
OUT_DIR = Path(__file__).resolve().parents[5] / "packages" / "schemas" / "json"

CONTRACTS: dict[str, type[BaseModel]] = {
    "agency-profile": AgencyProfile,
    "grant-opportunity": GrantOpportunity,
    "opportunity-matrix": OpportunityMatrix,
    "proposal-framework": ProposalFramework,
    "pillar-envelope": PillarEnvelope,
    "hitl-request": HitlRequest,
    "hitl-decision": HitlDecision,
    "citation": Citation,
    "discovery-progress": DiscoveryProgress,
    "discovery-job": DiscoveryJob,
    "grant-candidate": GrantCandidate,
    "user-view": UserView,
    "me-view": MeView,
}
VERSION = "1.0.0"


def build() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, model in CONTRACTS.items():
        schema = model.model_json_schema(mode="serialization")
        out[f"{name}.schema.json"] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{SCHEMA_BASE}/{name}/{VERSION}",
            **schema,
        }
    _, defs = models_json_schema(
        [(m, "serialization") for m in CONTRACTS.values()], ref_template="#/$defs/{model}"
    )
    out["bundle.schema.json"] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_BASE}/bundle/{VERSION}",
        "title": "HopeContracts",
        **defs,
    }
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, schema in build().items():
        (OUT_DIR / filename).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
        print(f"wrote {filename}")


if __name__ == "__main__":
    main()
