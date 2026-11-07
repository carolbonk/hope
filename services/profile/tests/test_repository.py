from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import psycopg
import pytest
from hope_core.db import tenant_tx
from hope_core.money import Money
from hope_core.pillar import InMemoryPillar
from hope_core.schemas.agency_profile import SamRegistration
from hope_core.schemas.hitl import Decision, Gate, HitlDecision
from hope_core.testing.factories import TENANT_A, TENANT_B, agency_profile
from hope_core.topics import EventType
from hope_profile.repository import (
    ApproverRoleError,
    Conn,
    ProfileNotFoundError,
    ProfileRepository,
    ProfileValidationError,
    ProposalStateError,
    SeparationOfDutiesError,
    VersionConflictError,
)

pytestmark = pytest.mark.db

FINANCE = ("finance_director",)


def _create(repo: ProfileRepository) -> UUID:
    return repo.create_agency(TENANT_A, agency_profile(), "onboarding").profile.agency_id


def _decision(
    proposal_id: UUID, artifact_hash: str, by: str, decision: Decision = "approve"
) -> HitlDecision:
    return HitlDecision(
        request_id=proposal_id,
        gate=Gate.PROFILE_COMMIT,
        decision=decision,
        artifact_hash=artifact_hash,
        decided_by=by,
        decided_at=datetime.now(UTC),
    )


def _events(pillar: InMemoryPillar) -> list[str]:
    return [e.event_type.value for e in pillar.log]


def test_create_read_history_and_as_of(repo: ProfileRepository, pillar: InMemoryPillar) -> None:
    agency_id = _create(repo)
    v1 = repo.current(TENANT_A, agency_id)
    assert v1.version == 1 and v1.profile.financials.budget_band == "1m-5m"
    result = repo.propose(TENANT_A, agency_id, {"mission": {"ntee_codes": ["O50"]}}, "u1")
    assert result.status == "committed" and result.version == 2
    assert [c.path for c in result.changes] == ["mission.ntee_codes"]
    assert repo.current(TENANT_A, agency_id).profile.mission.ntee_codes == ["O50"]
    assert repo.as_of(TENANT_A, agency_id, v1.valid_from).version == 1
    history = repo.history(TENANT_A, agency_id)
    assert [h.version for h in history] == [1, 2]
    assert history[0].valid_to == history[1].valid_from
    assert [c.path for c in repo.diff(TENANT_A, agency_id, 1, 2)] == ["mission.ntee_codes"]
    assert _events(pillar) == ["profile.updated", "profile.updated"]
    assert pillar.log[1].payload and pillar.log[1].payload["version"] == 2
    with pytest.raises(ProfileNotFoundError):
        repo.as_of(TENANT_A, agency_id, v1.valid_from - timedelta(days=1))


def test_rls_hides_other_tenants(repo: ProfileRepository) -> None:
    agency_id = _create(repo)
    with pytest.raises(ProfileNotFoundError):
        repo.current(TENANT_B, agency_id)
    with pytest.raises(ProfileNotFoundError):
        repo.propose(TENANT_B, agency_id, {"mission": {"ntee_codes": ["X"]}}, "u1")


def test_commit_writes_audit_log(repo: ProfileRepository, conn: Conn) -> None:
    agency_id = _create(repo)
    repo.propose(TENANT_A, agency_id, {"mission": {"vision_statement": "Every kid"}}, "u1")
    with tenant_tx(conn, TENANT_A) as cur:
        cur.execute(
            "SELECT actor, action, detail FROM audit_log WHERE subject = %s ORDER BY audit_id",
            (f"agency:{agency_id}",),
        )
        rows = cur.fetchall()
    assert [(r["actor"], r["action"]) for r in rows] == [
        ("onboarding", "profile.created"),
        ("u1", "profile.updated"),
    ]
    assert rows[1]["detail"] == {"version": 2, "paths": ["mission.vision_statement"]}


def test_validation_and_concurrency(repo: ProfileRepository) -> None:
    agency_id = _create(repo)
    with pytest.raises(ProfileValidationError):
        repo.propose(TENANT_A, agency_id, {"version": 5}, "u1")
    with pytest.raises(ProfileValidationError):
        repo.propose(TENANT_A, agency_id, {"mission": {"mission_statement": None}}, "u1")
    with pytest.raises(VersionConflictError):
        repo.propose(
            TENANT_A, agency_id, {"mission": {"ntee_codes": ["A"]}}, "u1", expected_version=7
        )
    same = repo.propose(
        TENANT_A,
        agency_id,
        {"mission": {"focus_areas": ["youth development", "STEM education"]}},
        "u1",
    )
    assert same.status == "no_change"


def test_protected_change_needs_hitl0(
    repo: ProfileRepository, pillar: InMemoryPillar, conn: Conn
) -> None:
    agency_id = _create(repo)
    budget = Money.from_decimal("6000000").model_dump()
    result = repo.propose(
        TENANT_A, agency_id, {"financials": {"annual_operating_budget": budget}}, "writer"
    )
    assert result.status == "pending_approval" and result.proposal
    proposal = result.proposal
    assert {c.path for c in result.changes} == {
        "financials.annual_operating_budget.amount_minor",
        "financials.budget_band",
    }
    assert repo.current(TENANT_A, agency_id).version == 1
    assert _events(pillar)[1:] == ["profile.change_proposed", "hitl.requested"]
    hitl = pillar.log[2].payload
    assert hitl and hitl["artifact_hash"] == proposal.content_hash and hitl["gate"] == "HITL-0"
    assert hitl["approver_roles"] == ["org_admin", "finance_director"]

    with pytest.raises(SeparationOfDutiesError):
        repo.decide(
            TENANT_A, _decision(proposal.proposal_id, proposal.content_hash, "writer"), FINANCE
        )
    with pytest.raises(ApproverRoleError):
        repo.decide(
            TENANT_A, _decision(proposal.proposal_id, proposal.content_hash, "cfo"), ("intern",)
        )
    with pytest.raises(ProposalStateError, match="stale"):
        repo.decide(TENANT_A, _decision(proposal.proposal_id, "sha256:old", "cfo"), FINANCE)

    done = repo.decide(
        TENANT_A, _decision(proposal.proposal_id, proposal.content_hash, "cfo"), FINANCE
    )
    assert done.status == "committed" and done.version == 2
    current = repo.current(TENANT_A, agency_id)
    assert current.profile.financials.budget_band == "5m-25m" and current.recorded_by == "cfo"
    assert repo.proposals(TENANT_A, agency_id) == []
    updated = pillar.log[-1]
    assert updated.event_type == EventType.PROFILE_UPDATED and updated.payload
    assert updated.payload["approved_by"] == "cfo" and updated.payload["protected_changed"]
    with tenant_tx(conn, TENANT_A) as cur:
        cur.execute(
            "SELECT gate, decision, artifact_hash FROM approvals WHERE workflow_id = %s",
            (f"profile-proposal:{proposal.proposal_id}",),
        )
        assert cur.fetchall() == [
            {"gate": "HITL-0", "decision": "approve", "artifact_hash": proposal.content_hash}
        ]
    with pytest.raises(ProposalStateError, match="already approved"):
        repo.decide(
            TENANT_A, _decision(proposal.proposal_id, proposal.content_hash, "cfo"), FINANCE
        )


def test_reject_keeps_profile(repo: ProfileRepository) -> None:
    agency_id = _create(repo)
    result = repo.propose(TENANT_A, agency_id, {"legal": {"uei": "J7M9HPTGJ1S9"}}, "writer")
    assert result.proposal
    done = repo.decide(
        TENANT_A,
        _decision(result.proposal.proposal_id, result.proposal.content_hash, "admin", "reject"),
        ("org_admin",),
    )
    assert done.status == "rejected" and done.proposal and done.proposal.status == "rejected"
    assert repo.current(TENANT_A, agency_id).profile.legal.uei is None


def test_approval_rebases_or_conflicts(repo: ProfileRepository) -> None:
    agency_id = _create(repo)
    first = repo.propose(TENANT_A, agency_id, {"legal": {"uei": "J7M9HPTGJ1S9"}}, "writer")
    clash = repo.propose(TENANT_A, agency_id, {"legal": {"uei": "K8N9HPTGJ1S9"}}, "writer")
    repo.propose(TENANT_A, agency_id, {"mission": {"ntee_codes": ["O50"]}}, "writer")
    assert first.proposal and clash.proposal
    landed = repo.decide(
        TENANT_A, _decision(first.proposal.proposal_id, first.proposal.content_hash, "cfo"), FINANCE
    )
    assert landed.version == 3
    current = repo.current(TENANT_A, agency_id).profile
    assert current.legal.uei == "J7M9HPTGJ1S9" and current.mission.ntee_codes == ["O50"]
    with pytest.raises(VersionConflictError, match=r"legal\.uei"):
        repo.decide(
            TENANT_A,
            _decision(clash.proposal.proposal_id, clash.proposal.content_hash, "cfo"),
            FINANCE,
        )


def test_tampered_proposal_is_refused(repo: ProfileRepository, migrated_db: str) -> None:
    agency_id = _create(repo)
    result = repo.propose(TENANT_A, agency_id, {"legal": {"uei": "J7M9HPTGJ1S9"}}, "writer")
    assert result.proposal
    with psycopg.connect(migrated_db, autocommit=True) as admin:
        admin.execute(
            'UPDATE profile_change_proposals SET patch = \'{"legal": {"uei": "EVIL00000000"}}\''
            " WHERE proposal_id = %s",
            (result.proposal.proposal_id,),
        )
    with pytest.raises(ProposalStateError, match="does not match"):
        repo.decide(
            TENANT_A,
            _decision(result.proposal.proposal_id, result.proposal.content_hash, "cfo"),
            FINANCE,
        )


def test_scan_stale_emits_once(repo: ProfileRepository, pillar: InMemoryPillar) -> None:
    profile = agency_profile()
    profile.legal.sam_registration = SamRegistration(status="active", expires_on=date(2026, 12, 31))
    agency_id = repo.create_agency(TENANT_A, profile, "onboarding").profile.agency_id
    first = repo.scan_stale(TENANT_A, agency_id, date(2026, 11, 7))
    assert [(a.field, a.threshold) for a in first] == [("legal.sam_registration.expires_on", "60d")]
    assert repo.scan_stale(TENANT_A, agency_id, date(2026, 11, 8)) == []
    assert [a.threshold for a in repo.scan_stale(TENANT_A, agency_id, date(2026, 12, 1))] == ["30d"]
    stale = [e for e in pillar.log if e.event_type == EventType.PROFILE_STALE_FIELD]
    assert len(stale) == 2 and stale[0].schema_ref == "stale-field-alert/1.0.0"


def test_create_rejects_bad_tenant_and_ein(repo: ProfileRepository) -> None:
    with pytest.raises(ProfileValidationError):
        repo.create_agency(TENANT_B, agency_profile(), "onboarding")
    bad = agency_profile()
    bad.legal.ein = "00-1234567"
    with pytest.raises(ProfileValidationError, match="prefix"):
        repo.create_agency(TENANT_A, bad, "onboarding")
