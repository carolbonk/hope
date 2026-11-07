"""/v1 endpoints (blueprint 7.4). Reads come from Postgres projections; writes go through
the Router into the outbox in the request's tenant transaction."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from hope_core.envelope import PillarEnvelope, Producer, Trace
from hope_core.hashing import content_hash
from hope_core.pillar import OutboundPackage
from hope_core.schemas.agency_profile import PROTECTED_PROFILE_PATHS
from hope_core.schemas.export import VERSION
from hope_core.schemas.hitl import STEP_UP_MFA_GATES, Decision, Gate, HitlDecision
from hope_core.topics import EventType

from hope_pillar.api.deps import UPLOAD_EXPIRES_SECONDS, Tx, TxDep
from hope_pillar.api.models import (
    ArtifactUpload,
    ArtifactUploadRequest,
    AuthorizeBody,
    DecisionAccepted,
    FrameworkView,
    GateView,
    IngestAccepted,
    LedgerView,
    MatrixItem,
    MatrixPage,
    OpportunityProvenance,
    OpportunityView,
    PackageAuthorized,
    ProfilePatch,
    ProfileView,
    ProposalAccepted,
    SignalBody,
    TimelineEntry,
    WorkflowView,
)
from hope_pillar.contracts import IngestRequest, IngestSource, ProfileChangeProposal
from hope_pillar.pillar import SERVICE

router = APIRouter(prefix="/v1")
Row = dict[str, Any]


def _envelope(
    tx: Tx, event_type: EventType, subject: str, payload: Any, **extra: Any
) -> PillarEnvelope:
    return PillarEnvelope(
        event_type=event_type,
        schema_ref=f"{extra.pop('schema')}/{VERSION}",
        tenant_id=tx.principal.tenant_id,
        subject_id=subject,
        producer=Producer(service=SERVICE),
        data_classification=extra.pop("classification", "confidential"),
        payload=payload.model_dump(mode="json"),
        **extra,
    )


def _one(tx: Tx, sql: str, *params: Any) -> Row | None:
    tx.cur.execute(sql, params)
    return tx.cur.fetchone()


def _all(tx: Tx, sql: str, *params: Any) -> list[Row]:
    tx.cur.execute(sql, params)
    return tx.cur.fetchall()


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


@router.post("/ingest/opportunities", status_code=status.HTTP_202_ACCEPTED)
def ingest_opportunity(
    body: IngestSource,
    tx: TxDep,
    response: Response,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=255)],
) -> IngestAccepted:
    request_hash = content_hash(body)
    inserted = _one(
        tx,
        "INSERT INTO pillar_ingest_requests (tenant_id, idempotency_key, ingest_id, request_hash)"
        " VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING ingest_id",
        tx.principal.tenant_id,
        idempotency_key,
        uuid4(),
        request_hash,
    )
    if inserted is None:
        prior = _one(
            tx,
            "SELECT ingest_id, request_hash FROM pillar_ingest_requests"
            " WHERE tenant_id = %s AND idempotency_key = %s",
            tx.principal.tenant_id,
            idempotency_key,
        )
        if prior is None or prior["request_hash"] != request_hash:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Idempotency-Key was already used with a different request body",
            )
        response.headers["Idempotent-Replayed"] = "true"
        return IngestAccepted(ingest_id=prior["ingest_id"], replayed=True)
    request = IngestRequest(
        **body.model_dump(),
        ingest_id=inserted["ingest_id"],
        tenant_id=tx.principal.tenant_id,
        submitted_by=tx.principal.user_id,
        received_at=datetime.now(UTC),
    )
    tx.publish(
        _envelope(
            tx,
            EventType.OPPORTUNITY_RAW_INGESTED,
            body.partition_key or str(request.ingest_id),
            request,
            schema="ingest-request",
            classification="internal",
        )
    )
    return IngestAccepted(ingest_id=request.ingest_id)


@router.post("/ingest/artifacts", status_code=status.HTTP_201_CREATED)
def ingest_artifact(body: ArtifactUploadRequest, tx: TxDep) -> ArtifactUpload:
    """Pre-signed upload. The ingestion service virus-scans before raw_ingested."""
    artifact_id = uuid4()
    key = f"tenants/{tx.principal.tenant_id}/artifacts/{artifact_id}/{body.filename}"
    services = tx.services
    storage_uri = f"s3://{services.bucket}/{key}"
    tx.cur.execute(
        "INSERT INTO artifacts (artifact_id, tenant_id, sha256, storage_uri, media_type,"
        " classification) VALUES (%s, %s, %s, %s, %s, 'confidential')",
        (artifact_id, tx.principal.tenant_id, body.sha256, storage_uri, body.media_type),
    )
    url = services.presign(key, body.media_type, UPLOAD_EXPIRES_SECONDS)
    return ArtifactUpload(
        artifact_id=artifact_id,
        upload_url=url,
        storage_uri=storage_uri,
        expires_in=UPLOAD_EXPIRES_SECONDS,
    )


def _profile_row(tx: Tx, agency_id: UUID, as_of: datetime | None = None) -> Row:
    row = _one(
        tx,
        "SELECT version, profile, valid_from, recorded_at FROM agency_profile_versions"
        " WHERE agency_id = %s AND (%s::timestamptz IS NULL OR valid_from <= %s)"
        " ORDER BY version DESC LIMIT 1",
        agency_id,
        as_of,
        as_of,
    )
    if row is None:
        raise _not_found("agency profile")
    return row


@router.get("/agencies/{agency_id}/profile")
def get_profile(
    agency_id: UUID, tx: TxDep, response: Response, as_of: datetime | None = None
) -> ProfileView:
    row = _profile_row(tx, agency_id, as_of)
    response.headers["ETag"] = f'"{row["version"]}"'
    return ProfileView(agency_id=agency_id, **row)


@router.patch("/agencies/{agency_id}/profile", status_code=status.HTTP_202_ACCEPTED)
def patch_profile(
    agency_id: UUID,
    body: ProfilePatch,
    tx: TxDep,
    if_match: Annotated[str | None, Header()] = None,
) -> ProposalAccepted:
    """Proposes a change; the profile steward applies it. Protected paths need HITL-0."""
    if if_match is None:
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, "If-Match header required")
    current = int(_profile_row(tx, agency_id)["version"])
    if if_match.removeprefix("W/").strip('"') != str(current):
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, f"profile is at version {current}")
    protected = sorted(
        path
        for path in body.changes
        if any(path == p or path.startswith(p + ".") for p in PROTECTED_PROFILE_PATHS)
    )
    proposal = ProfileChangeProposal(
        proposal_id=uuid4(),
        tenant_id=tx.principal.tenant_id,
        agency_id=agency_id,
        base_version=current,
        changes=body.changes,
        protected_paths=protected,
        proposed_by=tx.principal.user_id,
        reason=body.reason,
    )
    tx.publish(
        _envelope(
            tx,
            EventType.PROFILE_CHANGE_PROPOSED,
            str(agency_id),
            proposal,
            schema="profile-change-proposal",
        )
    )
    return ProposalAccepted(
        proposal_id=proposal.proposal_id,
        status="pending_approval" if protected else "accepted",
        protected_paths=protected,
    )


def _decode_cursor(cursor: str) -> tuple[Decimal, UUID]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return Decimal(data["s"]), UUID(data["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from exc


def _encode_cursor(score: Decimal, opportunity_id: UUID) -> str:
    raw = json.dumps({"s": str(score), "id": str(opportunity_id)})
    return base64.urlsafe_b64encode(raw.encode()).decode()


@router.get("/agencies/{agency_id}/matrix")
def get_matrix(
    agency_id: UUID,
    tx: TxDep,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    state: str | None = None,
    min_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    due_before: datetime | None = None,
) -> MatrixPage:
    after_score, after_id = _decode_cursor(cursor) if cursor else (None, None)
    rows = _all(
        tx,
        "SELECT t.opportunity_id, o.title, t.state, t.composite_score, t.recommendation,"
        " t.internal_deadline, o.application_due, t.workflow_id,"
        " coalesce(t.composite_score, -1) AS sort_score"
        " FROM tenant_opportunity t JOIN opportunities o USING (opportunity_id)"
        " WHERE t.agency_id = %s"
        " AND (%s::text IS NULL OR t.state = %s)"
        " AND (%s::numeric IS NULL OR t.composite_score >= %s)"
        " AND (%s::timestamptz IS NULL OR coalesce(t.internal_deadline, o.application_due) <= %s)"
        " AND (%s::numeric IS NULL OR (coalesce(t.composite_score, -1), t.opportunity_id)"
        "      < (%s::numeric, %s::uuid))"
        " ORDER BY sort_score DESC, t.opportunity_id DESC LIMIT %s",
        agency_id,
        state,
        state,
        min_score,
        min_score,
        due_before,
        due_before,
        after_score,
        after_score,
        after_id,
        limit + 1,
    )
    page, more = rows[:limit], len(rows) > limit
    last = page[-1] if page else None
    return MatrixPage(
        items=[MatrixItem(**{k: v for k, v in r.items() if k != "sort_score"}) for r in page],
        next_cursor=_encode_cursor(last["sort_score"], last["opportunity_id"])
        if more and last
        else None,
    )


@router.get("/opportunities/{opportunity_id}")
def get_opportunity(opportunity_id: UUID, tx: TxDep) -> OpportunityView:
    row = _one(
        tx,
        "SELECT o.opportunity_id, o.title, o.application_due, o.source_system, o.source_id,"
        " v.version, v.amendment_seq, v.normalized, v.content_hash, v.recorded_at"
        " FROM opportunities o JOIN opportunity_versions v"
        " ON v.opportunity_id = o.opportunity_id AND v.version = o.current_version"
        " WHERE o.opportunity_id = %s",
        opportunity_id,
    )
    if row is None:
        raise _not_found("opportunity")
    return OpportunityView(
        opportunity_id=row["opportunity_id"],
        title=row["title"],
        application_due=row["application_due"],
        normalized=row["normalized"],
        provenance=OpportunityProvenance(**row),
    )


GATE_COLUMNS = (
    "request_id, tenant_id, workflow_id, subject_id, gate, artifact_hash, approver_roles,"
    " due_at, summary, payload_ref, status, decision, decided_by, requested_at, decided_at"
)


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str, tx: TxDep) -> WorkflowView:
    lifecycle = _one(
        tx,
        "SELECT opportunity_id, agency_id, state, updated_at FROM tenant_opportunity"
        " WHERE workflow_id = %s ORDER BY updated_at DESC LIMIT 1",
        workflow_id,
    )
    gates = _all(
        tx,
        f"SELECT {GATE_COLUMNS} FROM pillar_gate_requests WHERE workflow_id = %s"
        " ORDER BY requested_at",
        workflow_id,
    )
    timeline = _all(
        tx,
        "SELECT event_id, event_type, occurred_at FROM pillar_workflow_timeline"
        " WHERE workflow_id = %s ORDER BY occurred_at",
        workflow_id,
    )
    if lifecycle is None and not gates and not timeline:
        raise _not_found("workflow")
    return WorkflowView(
        workflow_id=workflow_id,
        **(lifecycle or dict.fromkeys(("opportunity_id", "agency_id", "state", "updated_at"))),
        gates=[GateView(**g) for g in gates],
        timeline=[TimelineEntry(**t) for t in timeline],
    )


def _lock_gate(tx: Tx, where: str, *params: Any) -> Row:
    """Latest gate request matching `where`, locked, after authorization checks."""
    gate = _one(
        tx,
        f"SELECT {GATE_COLUMNS} FROM pillar_gate_requests WHERE {where}"
        " ORDER BY requested_at DESC LIMIT 1 FOR UPDATE",
        *params,
    )
    if gate is None:
        raise _not_found("gate request")
    principal = tx.principal
    if gate["approver_roles"] and not principal.roles & set(gate["approver_roles"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "principal lacks an approver role")
    if Gate(gate["gate"]) in STEP_UP_MFA_GATES and not principal.mfa:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "step-up MFA required for this gate")
    if gate["status"] != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"gate request is {gate['status']}")
    return gate


def _decide(
    tx: Tx, gate: Row, decision: Decision, artifact_hash: str, comment: str | None
) -> PillarEnvelope:
    if artifact_hash != gate["artifact_hash"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "artifact_hash is stale; review the current artifact"
        )
    decided = HitlDecision(
        request_id=gate["request_id"],
        gate=gate["gate"],
        decision=decision,
        artifact_hash=artifact_hash,
        decided_by=tx.principal.user_id,
        decided_at=datetime.now(UTC),
        comment=comment,
    )
    tx.cur.execute(
        "INSERT INTO approvals (tenant_id, workflow_id, gate, decision, artifact_hash,"
        " decided_by, decided_at, comment) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            tx.principal.tenant_id,
            gate["workflow_id"],
            decided.gate.value,
            decision,
            artifact_hash,
            decided.decided_by,
            decided.decided_at,
            comment,
        ),
    )
    tx.cur.execute(
        "UPDATE pillar_gate_requests SET status = 'decided', decision = %s, decided_by = %s,"
        " decided_at = %s WHERE request_id = %s",
        (decision, decided.decided_by, decided.decided_at, decided.request_id),
    )
    envelope = _envelope(
        tx,
        EventType.HITL_DECIDED,
        gate["subject_id"],
        decided,
        schema="hitl-decision",
        trace=Trace(correlation_id=gate["workflow_id"]),
    )
    tx.publish(envelope)
    return envelope


@router.post("/workflows/{workflow_id}/signals/{gate}", status_code=status.HTTP_202_ACCEPTED)
def signal_gate(workflow_id: str, gate: Gate, body: SignalBody, tx: TxDep) -> DecisionAccepted:
    """Submit a HITL decision. 409 when artifact_hash no longer matches the open request."""
    if gate == Gate.SUBMISSION_AUTHORIZATION and body.decision == "approve":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "HITL-5 approval goes through POST /v1/packages/{id}/authorize",
        )
    row = _lock_gate(tx, "workflow_id = %s AND gate = %s", workflow_id, gate.value)
    envelope = _decide(tx, row, body.decision, body.artifact_hash, body.comment)
    return DecisionAccepted(
        request_id=row["request_id"], event_id=envelope.event_id, decision=body.decision
    )


@router.post("/packages/{package_id}/authorize", status_code=status.HTTP_202_ACCEPTED)
def authorize_package(package_id: UUID, body: AuthorizeBody, tx: TxDep) -> PackageAuthorized:
    """HITL-5 AOR authorization (step-up MFA). package_id is the HITL-5 gate request id."""
    row = _lock_gate(
        tx, "request_id = %s AND gate = %s", package_id, Gate.SUBMISSION_AUTHORIZATION.value
    )
    if row["payload_ref"] is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "package has no payload_ref")
    envelope = _decide(tx, row, "approve", body.manifest_hash, body.comment)
    receipt = tx.route_outbound(
        OutboundPackage(
            tenant_id=tx.principal.tenant_id,
            opportunity_id=UUID(row["subject_id"]),
            channel=body.channel,
            manifest_hash=body.manifest_hash,
            authorized_by=tx.principal.user_id,
            payload_ref=row["payload_ref"],
        )
    )
    if not receipt.accepted or receipt.tracking_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, receipt.reason or "routing rejected")
    return PackageAuthorized(
        request_id=row["request_id"],
        event_id=envelope.event_id,
        decision="approve",
        tracking_id=receipt.tracking_id,
    )


@router.get("/frameworks/{framework_id}")
def get_framework(framework_id: UUID, tx: TxDep) -> FrameworkView:
    row = _one(
        tx,
        "SELECT framework_id, opportunity_id, agency_id, version, status, framework,"
        " content_hash FROM frameworks WHERE framework_id = %s",
        framework_id,
    )
    if row is None:
        raise _not_found("framework")
    ledgers = _all(
        tx,
        "SELECT ledger_id, engine_version, ledger, content_hash, created_at FROM budget_ledgers"
        " WHERE framework_id = %s ORDER BY created_at",
        framework_id,
    )
    return FrameworkView(**row, ledgers=[LedgerView(**ledger) for ledger in ledgers])


@router.post(
    "/frameworks/{framework_id}/recompute",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    responses={501: {"description": "pending a recompute command event type in hope_core"}},
)
def recompute_framework(framework_id: UUID, tx: TxDep) -> None:
    get_framework(framework_id, tx)
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED, "recompute goes through the Budget Engine (not wired yet)"
    )
