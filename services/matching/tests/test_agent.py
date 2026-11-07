from hope_core.envelope import PillarEnvelope, Producer
from hope_core.pillar import InMemoryPillar
from hope_core.schemas.opportunity_matrix import OpportunityMatrix
from hope_core.testing.factories import TENANT_A, TENANT_B
from hope_core.topics import EventType
from hope_matching.agents import MatchingAgent
from hope_matching.contracts import AlignmentAssessment, EligibilityResult
from hope_matching.testing import NOW, gateway, opportunity, profile

SOURCE = Producer(service="test")


def profile_event(p: object, tenant: object = TENANT_A) -> PillarEnvelope:
    return PillarEnvelope(
        event_type=EventType.PROFILE_UPDATED,
        schema_ref="agency-profile/1.0.0",
        tenant_id=tenant,
        subject_id="agency",
        producer=SOURCE,
        data_classification="confidential",
        payload={"profile": p.model_dump(mode="json")},  # type: ignore[attr-defined]
    )


def opportunity_event(o: object) -> PillarEnvelope:
    return PillarEnvelope(
        event_type=EventType.OPPORTUNITY_NORMALIZED,
        schema_ref="grant-opportunity/1.0.0",
        subject_id="opp",
        producer=SOURCE,
        data_classification="public",
        payload=o.model_dump(mode="json"),  # type: ignore[attr-defined]
    )


def emitted(pillar: InMemoryPillar, event_type: EventType) -> list[PillarEnvelope]:
    return [e for e in pillar.log if e.event_type == event_type]


def test_rescores_on_profile_and_opportunity_events() -> None:
    pillar = InMemoryPillar()
    agent = MatchingAgent(pillar, gateway(), clock=lambda: NOW)
    p = profile()
    pillar.publish(profile_event(p))
    pillar.publish(opportunity_event(opportunity(1)))
    pillar.publish(opportunity_event(opportunity(2)))
    assert agent.run() == 3

    matrices = emitted(pillar, EventType.RECOMMENDATION_UPDATED)
    assert len(matrices) == 3
    latest = OpportunityMatrix.model_validate(matrices[-1].payload)
    assert latest.agency_id == p.agency_id and len(latest.rows) == 2
    assert all(e.tenant_id == TENANT_A for e in matrices)
    assert all(e.data_classification == "confidential" for e in matrices)
    assert matrices[-1].trace.causation_id == str(pillar.log[2].event_id)
    for env in emitted(pillar, EventType.OPPORTUNITY_ELIGIBILITY_EVALUATED):
        EligibilityResult.model_validate(env.payload)
    for env in emitted(pillar, EventType.OPPORTUNITY_ALIGNMENT_SCORED):
        AlignmentAssessment.model_validate(env.payload)
    assert len(emitted(pillar, EventType.OPPORTUNITY_ELIGIBILITY_EVALUATED)) == 2

    pillar.publish(profile_event(p.model_copy(update={"version": 2})))
    assert agent.run() == 1
    assert len(emitted(pillar, EventType.RECOMMENDATION_UPDATED)) == 4
    assert agent.run() == 0  # idempotent: nothing new


def test_stale_profile_versions_and_cross_tenant_payloads_are_ignored() -> None:
    pillar = InMemoryPillar()
    agent = MatchingAgent(pillar, gateway(), clock=lambda: NOW)
    p = profile(version=3)
    agent.handle(profile_event(p))
    assert agent.handle(profile_event(p.model_copy(update={"version": 2}))) == []
    try:
        agent.handle(profile_event(p, tenant=TENANT_B))
    except ValueError:
        pass
    else:
        raise AssertionError("tenant mismatch must be rejected")


def test_expired_opportunities_are_not_ranked() -> None:
    pillar = InMemoryPillar()
    agent = MatchingAgent(pillar, gateway(), clock=lambda: NOW)
    agent.handle(profile_event(profile()))
    out = agent.handle(opportunity_event(opportunity(9, days=-1)))
    matrix = OpportunityMatrix.model_validate(out[-1].payload)
    assert matrix.rows == []
