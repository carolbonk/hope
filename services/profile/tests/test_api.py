from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hope_core.money import Money
from hope_core.testing.factories import TENANT_A, agency_profile
from hope_profile.api import Principal, get_principal, get_repository, router
from hope_profile.repository import ProfileRepository

pytestmark = pytest.mark.db


@pytest.fixture
def client(repo: ProfileRepository) -> Iterator[tuple[TestClient, dict[str, Principal]]]:
    who = {"user": Principal(TENANT_A, "writer", ("development_director",))}
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_principal] = lambda: who["user"]
    with TestClient(app) as test_client:
        yield test_client, who


def test_unconfigured_router_fails_closed() -> None:
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/agencies/00000000-0000-4000-8000-000000000001/profile")
    assert response.status_code in (401, 503)


def test_profile_flow(client: tuple[TestClient, dict[str, Principal]]) -> None:
    http, who = client
    profile = agency_profile()
    created = http.post("/v1/agencies", json=profile.model_dump(mode="json"))
    assert created.status_code == 201
    base = f"/v1/agencies/{profile.agency_id}/profile"

    got = http.get(base)
    assert got.status_code == 200 and got.headers["ETag"] == '"1"'
    patched = http.patch(
        base, json={"mission": {"ntee_codes": ["O50"]}}, headers={"If-Match": '"1"'}
    )
    assert patched.status_code == 200 and patched.json()["version"] == 2
    stale = http.patch(base, json={"mission": {"ntee_codes": ["B"]}}, headers={"If-Match": '"1"'})
    assert stale.status_code == 409
    assert http.get(base, params={"as_of": got.json()["valid_from"]}).json()["version"] == 1
    assert (
        http.get(f"{base}/diff", params={"from_version": 1, "to_version": 2}).json()[0]["path"]
        == "mission.ntee_codes"
    )
    assert len(http.get(f"{base}/history").json()) == 2
    assert 0 < http.get(f"{base}/completeness").json()["score"] < 100

    budget = Money.from_decimal("200000").model_dump()
    pending = http.patch(base, json={"financials": {"annual_operating_budget": budget}})
    assert pending.status_code == 202 and pending.json()["status"] == "pending_approval"
    proposal = pending.json()["proposal"]
    approve = f"{base}/proposals/{proposal['proposal_id']}/approve"
    body = {"artifact_hash": proposal["content_hash"]}

    assert http.post(approve, json=body).status_code == 403  # proposer
    who["user"] = Principal(TENANT_A, "cfo", ("finance_director",))
    assert http.post(approve, json={"artifact_hash": "sha256:x"}).status_code == 409
    assert [p["proposal_id"] for p in http.get(f"{base}/proposals").json()] == [
        proposal["proposal_id"]
    ]
    done = http.post(approve, json=body)
    assert done.status_code == 200 and done.json()["version"] == 3
    assert http.get(base).json()["profile"]["financials"]["budget_band"] == "<250k"
    assert (
        http.post(f"{base}/proposals/{proposal['proposal_id']}/reject", json=body).status_code
        == 409
    )
    assert http.patch(base, json={"legal": {"ein": "bad"}}).status_code == 422
