import json

import pytest
from hope_core.envelope import PillarEnvelope, Producer
from hope_core.hashing import content_hash
from hope_core.schemas.export import OUT_DIR, build
from hope_core.schemas.lifecycle import OpportunityState as S
from hope_core.schemas.lifecycle import assert_transition, can_transition
from hope_core.schemas.proposal_framework import BudgetLedger, Totals
from hope_core.testing.factories import agency_profile, grant_opportunity
from hope_core.topics import EventType, Topic
from pydantic import ValidationError


def test_factories_are_valid_and_roundtrip() -> None:
    for model in (agency_profile(), grant_opportunity()):
        assert type(model).model_validate_json(model.model_dump_json()) == model


def test_unknown_fields_rejected() -> None:
    data = agency_profile().model_dump(mode="json") | {"surprise": 1}
    with pytest.raises(ValidationError):
        type(agency_profile()).model_validate(data)


def test_extracted_field_requires_evidence() -> None:
    data = grant_opportunity().model_dump(mode="json")
    data["deadlines"]["application_due"]["evidence"] = []
    with pytest.raises(ValidationError):
        type(grant_opportunity()).model_validate(data)


def test_ledger_must_come_from_budget_engine() -> None:
    totals = Totals(
        direct_minor=0,
        mtdc_base_minor=0,
        indirect_minor=0,
        request_minor=0,
        cost_share_minor=0,
        project_total_minor=0,
    )
    with pytest.raises(ValidationError):
        BudgetLedger(
            ledger_id="l1",
            computed_by="llm",
            engine_version="x",  # type: ignore[arg-type]
            line_items=[],
            totals=totals,
            cap_checks=[],
        )


def test_content_hash_is_order_independent() -> None:
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})


def test_envelope_rules() -> None:
    producer = Producer(service="t")
    env = PillarEnvelope(
        event_type=EventType.PROFILE_UPDATED,
        schema_ref="agency-profile/1.0.0",
        subject_id="x",
        producer=producer,
        payload={},
    )
    assert env.topic is Topic.PROFILE_EVENTS
    child = env.caused(
        event_type=EventType.RECOMMENDATION_UPDATED, schema_ref="m", producer=producer, payload={}
    )
    assert child.trace.trace_id == env.trace.trace_id
    assert child.trace.causation_id == str(env.event_id)
    with pytest.raises(ValidationError):
        PillarEnvelope(
            event_type=EventType.PROFILE_UPDATED,
            schema_ref="s",
            subject_id="x",
            producer=producer,
            payload={},
            payload_ref="s3://x",
        )
    with pytest.raises(ValidationError):
        PillarEnvelope(
            event_type=EventType.PROFILE_UPDATED,
            schema_ref="s",
            subject_id="x",
            producer=producer,
            payload={},
            data_classification="restricted",
        )
    assert Topic.INGEST_RAW.dlq == "gop.dlq.ingest.raw"


def test_lifecycle_transitions() -> None:
    assert can_transition(S.AWAITING_GO_NO_GO, S.PLANNING)
    assert can_transition(S.DRAFTING, S.EXPIRED)
    assert not can_transition(S.SUBMITTED, S.EXPIRED)
    assert not can_transition(S.PLANNING, S.SUBMITTED)
    with pytest.raises(ValueError):
        assert_transition(S.DECLINED, S.PLANNING)


def test_exported_schemas_are_up_to_date() -> None:
    for filename, schema in build().items():
        on_disk = json.loads((OUT_DIR / filename).read_text())
        assert on_disk == schema, f"{filename} is stale: run `uv run hope-export-schemas`"
