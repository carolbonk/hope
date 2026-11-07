from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    """Base for every cross-service contract: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


ProvenanceSource = Literal[
    "user_input", "document_extraction", "crm_sync", "erp_sync", "sam_gov", "irs", "system"
]


class Provenance(Contract):
    source: ProvenanceSource
    source_ref: str | None = Field(None, description="artifact_id, record id or URL")
    captured_at: datetime
    verified_by: str | None = Field(None, description="user_id if confirmed by a human")
    confidence: float | None = Field(None, ge=0, le=1)


class Evidence(Contract):
    artifact_id: str
    page: int = Field(ge=1)
    char_start: int | None = None
    char_end: int | None = None
    quote: str | None = Field(None, max_length=500)


class ExtractionMeta(Contract):
    """Provenance carried by every field extracted from an RFP. No evidence, no field."""

    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(min_length=1)
    extractor: str | None = Field(None, description="model or parser id + version")
