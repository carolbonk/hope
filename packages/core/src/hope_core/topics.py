"""Pillar topics and event types (blueprint 7.2). Every producer and consumer imports these."""

from __future__ import annotations

from enum import StrEnum


class Topic(StrEnum):
    INGEST_RAW = "gop.ingest.raw"
    OPPORTUNITY_EVENTS = "gop.opportunity.events"
    PROFILE_EVENTS = "gop.profile.events"
    AGENT_COMMANDS = "gop.agent.commands"
    AGENT_RESULTS = "gop.agent.results"
    HITL_EVENTS = "gop.hitl.events"
    OUTBOUND_PACKAGES = "gop.outbound.packages"
    NOTIFICATIONS = "gop.notifications"

    @property
    def dlq(self) -> str:
        return "gop.dlq." + self.value.removeprefix("gop.")


class EventType(StrEnum):
    OPPORTUNITY_RAW_INGESTED = "opportunity.raw_ingested"
    OPPORTUNITY_NORMALIZED = "opportunity.normalized"
    OPPORTUNITY_PARSE_INCOMPLETE = "opportunity.parse_incomplete"
    OPPORTUNITY_AMENDED = "opportunity.amended"
    OPPORTUNITY_ELIGIBILITY_EVALUATED = "opportunity.eligibility_evaluated"
    OPPORTUNITY_ALIGNMENT_SCORED = "opportunity.alignment_scored"
    OPPORTUNITY_STATE_CHANGED = "opportunity.state_changed"
    RECOMMENDATION_UPDATED = "recommendation.updated"
    PROFILE_UPDATED = "profile.updated"
    PROFILE_CHANGE_PROPOSED = "profile.change_proposed"
    PROFILE_STALE_FIELD = "profile.stale_field"
    FRAMEWORK_DRAFTED = "framework.drafted"
    FRAMEWORK_LOCKED = "framework.locked"
    VERIFICATION_REPORTED = "verification.reported"
    HITL_REQUESTED = "hitl.requested"
    HITL_DECIDED = "hitl.decided"
    SUBMISSION_AUTHORIZED = "submission.authorized"
    APPLICATION_SUBMITTED = "application.submitted"
    NOTIFICATION_REQUESTED = "notification.requested"


EVENT_TOPIC: dict[EventType, Topic] = {
    EventType.OPPORTUNITY_RAW_INGESTED: Topic.INGEST_RAW,
    EventType.OPPORTUNITY_NORMALIZED: Topic.OPPORTUNITY_EVENTS,
    EventType.OPPORTUNITY_PARSE_INCOMPLETE: Topic.OPPORTUNITY_EVENTS,
    EventType.OPPORTUNITY_AMENDED: Topic.OPPORTUNITY_EVENTS,
    EventType.OPPORTUNITY_ELIGIBILITY_EVALUATED: Topic.OPPORTUNITY_EVENTS,
    EventType.OPPORTUNITY_ALIGNMENT_SCORED: Topic.OPPORTUNITY_EVENTS,
    EventType.OPPORTUNITY_STATE_CHANGED: Topic.OPPORTUNITY_EVENTS,
    EventType.RECOMMENDATION_UPDATED: Topic.OPPORTUNITY_EVENTS,
    EventType.PROFILE_UPDATED: Topic.PROFILE_EVENTS,
    EventType.PROFILE_CHANGE_PROPOSED: Topic.PROFILE_EVENTS,
    EventType.PROFILE_STALE_FIELD: Topic.PROFILE_EVENTS,
    EventType.FRAMEWORK_DRAFTED: Topic.AGENT_RESULTS,
    EventType.FRAMEWORK_LOCKED: Topic.OPPORTUNITY_EVENTS,
    EventType.VERIFICATION_REPORTED: Topic.AGENT_RESULTS,
    EventType.HITL_REQUESTED: Topic.HITL_EVENTS,
    EventType.HITL_DECIDED: Topic.HITL_EVENTS,
    EventType.SUBMISSION_AUTHORIZED: Topic.HITL_EVENTS,
    EventType.APPLICATION_SUBMITTED: Topic.OUTBOUND_PACKAGES,
    EventType.NOTIFICATION_REQUESTED: Topic.NOTIFICATIONS,
}
