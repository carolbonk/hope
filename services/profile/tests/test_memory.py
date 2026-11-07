import pytest
from hope_core.model_gateway import MockProvider, ModelGateway
from hope_core.testing.factories import TENANT_A, TENANT_B, agency_profile
from hope_profile.memory import NarrativeMemory
from hope_profile.repository import Conn, ProfileRepository

pytestmark = pytest.mark.db

BOILERPLATE = "Riverbend has mentored 1,200 youth since 2012.\n\nOur STEM lab serves grades 6-9."


def test_index_and_search(repo: ProfileRepository, conn: Conn) -> None:
    agency_id = repo.create_agency(TENANT_A, agency_profile(), "onboarding").profile.agency_id
    memory = NarrativeMemory(conn, ModelGateway([MockProvider()]))
    assert memory.index_asset(TENANT_A, agency_id, "boiler-1", "boilerplate", BOILERPLATE) == 1
    memory.index_asset(
        TENANT_A, agency_id, "bio-ed", "bio", "Dr. Lee leads Riverbend.", approved_for_reuse=True
    )
    hits = memory.search(TENANT_A, "Dr. Lee leads Riverbend.", k=5, agency_id=agency_id)
    assert [h.asset_id for h in hits] == ["bio-ed"]
    assert hits[0].score == pytest.approx(1.0)

    everything = memory.search(
        TENANT_A, BOILERPLATE.replace("\n\n", "\n"), k=5, agency_id=agency_id, approved_only=False
    )
    assert everything[0].asset_id == "boiler-1" and len(everything) == 2

    assert memory.set_approved_for_reuse(TENANT_A, agency_id, "boiler-1", True) == 1
    assert len(memory.search(TENANT_A, "youth", k=5, agency_id=agency_id)) == 2
    assert memory.index_asset(TENANT_A, agency_id, "boiler-1", "boilerplate", "Short.") == 1
    assert memory.search(TENANT_B, "youth", k=5, approved_only=False) == []
