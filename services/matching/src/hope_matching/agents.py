"""Thin pillar wrappers for A4/A5/A6. Re-scores an agency's portfolio on `opportunity.normalized`
and `profile.updated`, and emits eligibility, alignment and `recommendation.updated` events."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from hope_core.envelope import PillarEnvelope, Producer
from hope_core.hashing import content_hash
from hope_core.model_gateway import ModelGateway, RunBudget
from hope_core.pillar import PillarPort
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.grant_opportunity import GrantOpportunity
from hope_core.schemas.opportunity_matrix import OpportunityMatrix
from hope_core.topics import EventType
from pydantic import BaseModel

from hope_matching.alignment import assess_alignment
from hope_matching.config import MatchingConfig
from hope_matching.contracts import AlignmentAssessment, EligibilityResult
from hope_matching.eligibility import evaluate_eligibility
from hope_matching.recommender import Assessed, build_matrix

SERVICE = "matching"
CONSUMER_GROUP = "matching"
HANDLED = [EventType.OPPORTUNITY_NORMALIZED.value, EventType.PROFILE_UPDATED.value]
SCHEMA_REFS = {
    EventType.OPPORTUNITY_ELIGIBILITY_EVALUATED: "eligibility-result/1.0.0",
    EventType.OPPORTUNITY_ALIGNMENT_SCORED: "alignment-assessment/1.0.0",
    EventType.RECOMMENDATION_UPDATED: "opportunity-matrix/1.0.0",
}
PRODUCERS = {
    EventType.OPPORTUNITY_ELIGIBILITY_EVALUATED: Producer(service=SERVICE, agent_id="A4"),
    EventType.OPPORTUNITY_ALIGNMENT_SCORED: Producer(service=SERVICE, agent_id="A5"),
    EventType.RECOMMENDATION_UPDATED: Producer(service=SERVICE, agent_id="A6"),
}

ConfigFor = Callable[[UUID], MatchingConfig]
Clock = Callable[[], datetime]


def _contract(payload: dict[str, Any] | None, key: str, model: type[BaseModel]) -> Any:
    if payload is None:
        raise ValueError("claim-check payloads (payload_ref) are not supported yet")
    return model.model_validate(payload.get(key, payload))


class MatchingAgent:
    """Keeps the latest profiles and open opportunities in memory and caches A4/A5 results by
    content hash, so a re-score only calls the judge for changed (profile, opportunity) pairs."""

    def __init__(
        self,
        pillar: PillarPort,
        gateway: ModelGateway,
        config_for: ConfigFor = lambda _tenant: MatchingConfig(),
        clock: Clock = lambda: datetime.now(UTC),
    ) -> None:
        self.pillar = pillar
        self.gateway = gateway
        self.config_for = config_for
        self.clock = clock
        self.profiles: dict[UUID, AgencyProfile] = {}
        self.opportunities: dict[UUID, GrantOpportunity] = {}
        self._cache: dict[tuple[str, str], Assessed] = {}

    def run(self, max_events: int | None = None) -> int:
        handled = 0
        for env in self.pillar.subscribe(HANDLED, CONSUMER_GROUP, max_events=max_events):
            self.handle(env)
            handled += 1
        return handled

    def handle(self, env: PillarEnvelope) -> list[PillarEnvelope]:
        if env.event_type == EventType.OPPORTUNITY_NORMALIZED:
            return self.on_opportunity_normalized(env)
        if env.event_type == EventType.PROFILE_UPDATED:
            return self.on_profile_updated(env)
        return []

    def on_opportunity_normalized(self, env: PillarEnvelope) -> list[PillarEnvelope]:
        opportunity: GrantOpportunity = _contract(env.payload, "opportunity", GrantOpportunity)
        self.opportunities[opportunity.opportunity_id] = opportunity
        out = []
        for profile in self.profiles.values():
            if env.tenant_id is None or env.tenant_id == profile.tenant_id:
                out += self._rescore(env, profile, only={opportunity.opportunity_id})
        return out

    def on_profile_updated(self, env: PillarEnvelope) -> list[PillarEnvelope]:
        profile: AgencyProfile = _contract(env.payload, "profile", AgencyProfile)
        if env.tenant_id is not None and env.tenant_id != profile.tenant_id:
            raise ValueError("profile tenant does not match the envelope tenant")
        current = self.profiles.get(profile.agency_id)
        if current is not None and current.version > profile.version:
            return []
        self.profiles[profile.agency_id] = profile
        return self._rescore(env, profile, only=None)

    def _open(self) -> list[GrantOpportunity]:
        now = self.clock()
        return [
            o
            for o in self.opportunities.values()
            if o.deadlines.application_due is None or o.deadlines.application_due.value > now
        ]

    def _assess(
        self, profile: AgencyProfile, opp: GrantOpportunity, config: MatchingConfig
    ) -> Assessed:
        key = (content_hash(profile), content_hash(opp))
        if key not in self._cache:
            today = self.clock().date()
            eligibility = evaluate_eligibility(profile, opp, today)
            alignment = None
            if eligibility.status != "ineligible":
                alignment = assess_alignment(self.gateway, profile, opp, config, RunBudget())
            self._cache[key] = Assessed(opp, eligibility, alignment)
        return self._cache[key]

    def _rescore(
        self, cause: PillarEnvelope, profile: AgencyProfile, only: set[UUID] | None
    ) -> list[PillarEnvelope]:
        config = self.config_for(profile.tenant_id)
        assessed = [self._assess(profile, o, config) for o in self._open()]
        out: list[PillarEnvelope] = []
        for item in assessed:
            if only is not None and item.opportunity.opportunity_id not in only:
                continue
            out.append(
                self._emit(
                    cause, profile, EventType.OPPORTUNITY_ELIGIBILITY_EVALUATED, item.eligibility
                )
            )
            if item.alignment is not None:
                out.append(
                    self._emit(
                        cause, profile, EventType.OPPORTUNITY_ALIGNMENT_SCORED, item.alignment
                    )
                )
        matrix = build_matrix(profile, assessed, config, generated_at=self.clock())
        out.append(self._emit(cause, profile, EventType.RECOMMENDATION_UPDATED, matrix))
        return out

    def _emit(
        self,
        cause: PillarEnvelope,
        profile: AgencyProfile,
        event_type: EventType,
        body: EligibilityResult | AlignmentAssessment | OpportunityMatrix,
    ) -> PillarEnvelope:
        subject = (
            str(profile.agency_id)
            if isinstance(body, OpportunityMatrix)
            else str(body.opportunity_id)
        )
        env = cause.caused(
            event_type=event_type,
            schema_ref=SCHEMA_REFS[event_type],
            producer=PRODUCERS[event_type],
            tenant_id=profile.tenant_id,
            subject_id=subject,
            data_classification="confidential",
            payload=body.model_dump(mode="json"),
        )
        self.pillar.publish(env)
        return env
