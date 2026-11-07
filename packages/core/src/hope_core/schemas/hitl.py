from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from hope_core.schemas.common import Contract


class Gate(StrEnum):
    PROFILE_COMMIT = "HITL-0"
    GO_NO_GO = "HITL-1"
    BUDGET_SIGNOFF = "HITL-2"
    COMPLIANCE_ATTESTATION = "HITL-3"
    EXECUTIVE_APPROVAL = "HITL-4"
    SUBMISSION_AUTHORIZATION = "HITL-5"
    ELIGIBILITY_REVIEW = "REVIEW-ELIGIBILITY"
    PARSE_REVIEW = "REVIEW-PARSE"


STEP_UP_MFA_GATES = frozenset(
    {Gate.BUDGET_SIGNOFF, Gate.COMPLIANCE_ATTESTATION, Gate.SUBMISSION_AUTHORIZATION}
)

Decision = Literal["approve", "reject", "request_changes", "go", "no_go", "defer"]


class HitlRequest(Contract):
    request_id: UUID
    tenant_id: UUID
    workflow_id: str
    gate: Gate
    artifact_hash: str = Field(description="approval is void if the artifact changes")
    approver_roles: list[str]
    due_at: datetime | None = None
    summary: str
    payload_ref: str | None = None


class HitlDecision(Contract):
    request_id: UUID
    gate: Gate
    decision: Decision
    artifact_hash: str
    decided_by: str
    decided_at: datetime
    comment: str | None = None
    details: dict[str, Any] = {}
