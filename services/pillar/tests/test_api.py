from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from hope_core.db import connect
from hope_core.envelope import PillarEnvelope, Producer, Trace
from hope_core.hashing import content_hash
from hope_core.schemas.hitl import Gate, HitlRequest
from hope_core.settings import get_settings
from hope_core.testing.factories import TENANT_A, TENANT_B, agency_profile, grant_opportunity
from hope_core.topics import EventType
from hope_pillar.api import create_app
from hope_pillar.api.deps import Services
from hope_pillar.dlq import InMemoryDeadLetterSink
from hope_pillar.pillar import KafkaPostgresPillar
from hope_pillar.projector import project
from hope_pillar.router import PillarRouter
from psycopg.types.json import Jsonb

pytestmark = pytest.mark.db

HEADERS = {
    "X-Hope-Tenant": str(TENANT_A),
    "X-Hope-User": "dd-1",
    "X-Hope-Roles": "development_director",
}
AOR = {
    "X-Hope-Tenant": str(TENANT_A),
    "X-Hope-User": "aor-1",
    "X-Hope-Roles": "aor",
    "X-Hope-MFA": "true",
}


@pytest.fixture
def client(migrated_db: str) -> Iterator[TestClient]:
    pillar = KafkaPostgresPillar(dead_letters=InMemoryDeadLetterSink())
    services = Services(
        pillar,
        PillarRouter(pillar, pillar.dead_letters),
        get_settings().database_url,
        presigner_factory=lambda: lambda key, ctype, exp: f"https://s3.test/{key}?exp={exp}",
    )
    with TestClient(create_app(services, legacy=True)) as c:
        yield c


def admin(sql: str, *params: Any) -> list[dict[str, Any]]:
    with connect(get_settings().database_admin_url) as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall() if cur.description else []


def outbox_for(key: str, value: str) -> list[dict[str, Any]]:
    return admin(
        "SELECT topic, envelope FROM outbox WHERE envelope->'payload'->>%s = %s", key, value
    )


@pytest.fixture
def world(migrated_db: str) -> dict[str, Any]:
    profile = agency_profile()
    opp = grant_opportunity()
    workflow_id = f"wf-{uuid4().hex[:8]}"
    admin(
        "INSERT INTO agencies (agency_id, tenant_id, legal_name) VALUES (%s, %s, 'Riverbend')",
        profile.agency_id,
        TENANT_A,
    )
    admin(
        "INSERT INTO agency_profile_versions (agency_id, tenant_id, version, profile, recorded_by)"
        " VALUES (%s, %s, 1, %s, 'seed')",
        profile.agency_id,
        TENANT_A,
        Jsonb(profile.model_dump(mode="json")),
    )
    admin(
        "INSERT INTO opportunities (opportunity_id, source_system, source_id, title)"
        " VALUES (%s, 'grants_gov', %s, %s)",
        opp.opportunity_id,
        uuid4().hex,
        opp.title,
    )
    admin(
        "INSERT INTO opportunity_versions (opportunity_id, version, normalized, content_hash)"
        " VALUES (%s, 1, %s, %s)",
        opp.opportunity_id,
        Jsonb(opp.model_dump(mode="json")),
        content_hash(opp),
    )
    admin(
        "INSERT INTO tenant_opportunity (tenant_id, opportunity_id, agency_id, state, workflow_id,"
        " composite_score) VALUES (%s, %s, %s, 'AwaitingGoNoGo', %s, 81.5)",
        TENANT_A,
        opp.opportunity_id,
        profile.agency_id,
        workflow_id,
    )
    return {"agency_id": profile.agency_id, "opp": opp, "workflow_id": workflow_id}


def open_gate(world: dict[str, Any], gate: Gate, artifact_hash: str, roles: list[str]) -> UUID:
    request = HitlRequest(
        request_id=uuid4(),
        tenant_id=TENANT_A,
        workflow_id=world["workflow_id"],
        gate=gate,
        artifact_hash=artifact_hash,
        approver_roles=roles,
        summary="review",
        payload_ref="s3://hope-artifacts/pkg.zip",
    )
    env = PillarEnvelope(
        event_type=EventType.HITL_REQUESTED,
        schema_ref="hitl-request/1.0.0",
        tenant_id=TENANT_A,
        subject_id=str(world["opp"].opportunity_id),
        producer=Producer(service="workflow"),
        trace=Trace(correlation_id=world["workflow_id"]),
        payload=request.model_dump(mode="json"),
    )
    with (
        connect(get_settings().database_admin_url) as conn,
        conn.transaction(),
        conn.cursor() as cur,
    ):
        project(cur, env)
        project(cur, env)
    return request.request_id


def test_requires_tenant(client: TestClient) -> None:
    assert client.get(f"/v1/opportunities/{uuid4()}").status_code == 401


def test_ingest_is_idempotent(client: TestClient) -> None:
    body = {
        "kind": "url",
        "url": "https://grants.gov/x",
        "source_system": "grants_gov",
        "source_id": uuid4().hex,
    }
    key = {"Idempotency-Key": uuid4().hex}
    assert client.post("/v1/ingest/opportunities", json=body, headers=HEADERS).status_code == 422
    first = client.post("/v1/ingest/opportunities", json=body, headers=HEADERS | key)
    assert first.status_code == 202
    again = client.post("/v1/ingest/opportunities", json=body, headers=HEADERS | key)
    assert again.json() == {"ingest_id": first.json()["ingest_id"], "replayed": True}
    assert again.headers["Idempotent-Replayed"] == "true"
    other = client.post(
        "/v1/ingest/opportunities", json=body | {"source_id": "other"}, headers=HEADERS | key
    )
    assert other.status_code == 422
    [row] = outbox_for("ingest_id", first.json()["ingest_id"])
    assert row["topic"] == "gop.ingest.raw"
    assert row["envelope"]["subject_id"] == f"grants_gov:{body['source_id']}"


def test_ingest_validates_kind(client: TestClient) -> None:
    resp = client.post(
        "/v1/ingest/opportunities",
        json={"kind": "file"},
        headers=HEADERS | {"Idempotency-Key": "k"},
    )
    assert resp.status_code == 422


def test_artifact_presign(client: TestClient) -> None:
    body = {
        "filename": "rfp.pdf",
        "media_type": "application/pdf",
        "sha256": "a" * 64,
        "size_bytes": 10,
    }
    resp = client.post("/v1/ingest/artifacts", json=body, headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["upload_url"].startswith(f"https://s3.test/tenants/{TENANT_A}/artifacts/")
    assert admin("SELECT 1 FROM artifacts WHERE artifact_id = %s", data["artifact_id"])


def test_profile_etag_and_protected_patch(client: TestClient, world: dict[str, Any]) -> None:
    url = f"/v1/agencies/{world['agency_id']}/profile"
    got = client.get(url, headers=HEADERS)
    assert got.status_code == 200 and got.headers["ETag"] == '"1"'
    change = {"changes": {"financials.fringe_rate_bps": 3000, "mission.focus_areas": ["STEM"]}}
    assert client.patch(url, json=change, headers=HEADERS).status_code == 428
    assert client.patch(url, json=change, headers=HEADERS | {"If-Match": '"7"'}).status_code == 412
    resp = client.patch(url, json=change, headers=HEADERS | {"If-Match": '"1"'})
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending_approval"
    assert resp.json()["protected_paths"] == ["financials.fringe_rate_bps"]
    [row] = outbox_for("proposal_id", resp.json()["proposal_id"])
    assert row["topic"] == "gop.profile.events"
    other_tenant = HEADERS | {"X-Hope-Tenant": str(TENANT_B)}
    assert client.get(url, headers=other_tenant).status_code == 404


def test_matrix_and_opportunity(client: TestClient, world: dict[str, Any]) -> None:
    page = client.get(f"/v1/agencies/{world['agency_id']}/matrix?limit=1", headers=HEADERS).json()
    assert [i["composite_score"] for i in page["items"]] == [81.5]
    assert page["next_cursor"] is None
    assert (
        client.get(
            f"/v1/agencies/{world['agency_id']}/matrix?cursor=bad", headers=HEADERS
        ).status_code
        == 400
    )
    opp = client.get(f"/v1/opportunities/{world['opp'].opportunity_id}", headers=HEADERS).json()
    assert opp["provenance"]["content_hash"] == content_hash(world["opp"])


def test_signal_rejects_stale_hash_and_publishes_decision(
    client: TestClient, world: dict[str, Any]
) -> None:
    request_id = open_gate(world, Gate.GO_NO_GO, "sha256:v2", ["development_director"])
    url = f"/v1/workflows/{world['workflow_id']}/signals/HITL-1"
    stale = client.post(url, json={"decision": "go", "artifact_hash": "sha256:v1"}, headers=HEADERS)
    assert stale.status_code == 409
    forbidden = HEADERS | {"X-Hope-Roles": "intern"}
    assert (
        client.post(
            url, json={"decision": "go", "artifact_hash": "sha256:v2"}, headers=forbidden
        ).status_code
        == 403
    )
    ok = client.post(url, json={"decision": "go", "artifact_hash": "sha256:v2"}, headers=HEADERS)
    assert ok.status_code == 202
    [row] = outbox_for("request_id", str(request_id))
    assert (row["topic"], row["envelope"]["event_type"]) == ("gop.hitl.events", "hitl.decided")
    assert row["envelope"]["trace"]["correlation_id"] == world["workflow_id"]
    again = client.post(url, json={"decision": "go", "artifact_hash": "sha256:v2"}, headers=HEADERS)
    assert again.status_code == 409
    view = client.get(f"/v1/workflows/{world['workflow_id']}", headers=HEADERS).json()
    assert view["state"] == "AwaitingGoNoGo"
    assert [(g["gate"], g["status"], g["decided_by"]) for g in view["gates"]] == [
        ("HITL-1", "decided", "dd-1")
    ]
    assert [t["event_type"] for t in view["timeline"]] == ["hitl.requested"]


def test_package_authorization(client: TestClient, world: dict[str, Any]) -> None:
    manifest = f"sha256:{uuid4().hex}"
    package_id = open_gate(world, Gate.SUBMISSION_AUTHORIZATION, manifest, ["aor"])
    url = f"/v1/packages/{package_id}/authorize"
    body = {"manifest_hash": manifest, "channel": "grants_gov"}
    no_mfa = AOR | {"X-Hope-MFA": "false"}
    assert client.post(url, json=body, headers=no_mfa).status_code == 403
    signal = f"/v1/workflows/{world['workflow_id']}/signals/HITL-5"
    assert (
        client.post(
            signal, json={"decision": "approve", "artifact_hash": manifest}, headers=AOR
        ).status_code
        == 409
    )
    resp = client.post(url, json=body, headers=AOR)
    assert resp.status_code == 202, resp.text
    [row] = outbox_for("manifest_hash", manifest)
    assert row["envelope"]["event_type"] == "submission.authorized"
    assert str(row["envelope"]["event_id"]) == resp.json()["tracking_id"]


def test_framework_endpoints(client: TestClient) -> None:
    assert client.get(f"/v1/frameworks/{uuid4()}", headers=HEADERS).status_code == 404


def test_tenant_isolation_on_outbox(migrated_db: str) -> None:
    with psycopg.connect(get_settings().database_url) as conn:
        conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(TENANT_B),))
        rows = conn.execute(
            "SELECT count(*) FROM outbox WHERE tenant_id = %s", (TENANT_A,)
        ).fetchone()
    assert rows == (0,)
