"""Canonical data contracts. Pydantic models here are the single source of truth;
JSON Schema (packages/schemas/json) and TypeScript types (packages/schemas/ts) are generated."""

from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.common import Evidence, ExtractionMeta, Provenance
from hope_core.schemas.grant_opportunity import GrantOpportunity
from hope_core.schemas.hitl import Gate, HitlDecision, HitlRequest
from hope_core.schemas.lifecycle import OpportunityState
from hope_core.schemas.opportunity_matrix import OpportunityMatrix
from hope_core.schemas.proposal_framework import ProposalFramework

__all__ = [
    "AgencyProfile",
    "Evidence",
    "ExtractionMeta",
    "Gate",
    "GrantOpportunity",
    "HitlDecision",
    "HitlRequest",
    "OpportunityMatrix",
    "OpportunityState",
    "ProposalFramework",
    "Provenance",
]
