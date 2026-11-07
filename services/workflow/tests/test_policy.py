from datetime import UTC, datetime, timedelta

import pytest
from hope_core.schemas.agency_profile import ApprovalRule
from hope_core.schemas.grant_opportunity import GrantOpportunity, Source, SourceSystem
from hope_core.schemas.hitl import Gate
from hope_core.schemas.lifecycle import InvalidTransitionError
from hope_core.schemas.lifecycle import OpportunityState as S
from hope_core.testing import factories
from hope_workflow import policy
from hope_workflow.contracts import ProfileArea
from hope_workflow.deadlines import plan_deadlines

NOW = datetime(2027, 1, 4, 12, tzinfo=UTC)


def test_json_logic() -> None:
    data = {"request_minor": 600, "ask": {"tier": "big"}}
    assert policy.json_logic({">": [{"var": "request_minor"}, 500]}, data)
    assert policy.json_logic(
        {"and": [{"==": [{"var": "ask.tier"}, "big"]}, {"!": [{"<": [{"var": "x"}, 1]}]}]}, data
    )
    assert not policy.json_logic({">=": [{"var": "missing"}, 1]}, data)
    with pytest.raises(ValueError):
        policy.json_logic({"in": ["a", ["a"]]}, data)


def test_matching_conditional_rule_beats_default() -> None:
    rules = [
        ApprovalRule(gate=Gate.BUDGET_SIGNOFF, approver_roles=["finance_director"]),
        ApprovalRule(
            gate=Gate.BUDGET_SIGNOFF,
            condition={">": [{"var": "request_minor"}, 50_000_000]},
            approver_roles=["cfo"],
            min_approvals=2,
        ),
    ]
    big = policy.select_rule(rules, Gate.BUDGET_SIGNOFF, {"request_minor": 60_000_000})
    small = policy.select_rule(rules, Gate.BUDGET_SIGNOFF, {"request_minor": 1})
    assert big is not None and big.approver_roles == ["cfo"]
    assert small is not None and small.approver_roles == ["finance_director"]
    assert policy.select_rule(rules, Gate.GO_NO_GO, {}) is None


def test_gate_policy_defaults_and_go_no_go_sla() -> None:
    profile = factories.agency_profile()
    pol = policy.gate_policy(profile, Gate.GO_NO_GO, {}, NOW, NOW + timedelta(days=10))
    assert pol.roles == ("development_director",)
    assert pol.sla == timedelta(days=2)
    compliance = policy.gate_policy(profile, Gate.COMPLIANCE_ATTESTATION, {}, NOW, None)
    assert compliance.roles == ("compliance_officer",)
    assert compliance.escalate_to == "executive_director"
    auth = policy.gate_policy(profile, Gate.SUBMISSION_AUTHORIZATION, {}, NOW, NOW + timedelta(1))
    assert auth.sla == timedelta(days=1)


def test_rollback_targets() -> None:
    areas = policy.areas_for_paths(["financials.indirect_rate", "mission"])
    assert areas == {ProfileArea.BUDGET}
    assert policy.rollback_target(S.AWAITING_EXEC_APPROVAL, areas) is S.PLANNING
    assert policy.rollback_target(S.AWAITING_GO_NO_GO, areas) is None
    assert policy.rollback_target(S.SUBMITTED, areas) is None
    both = {ProfileArea.BUDGET, ProfileArea.ELIGIBILITY}
    assert policy.rollback_target(S.PACKAGING, both) is S.NORMALIZED
    assert policy.invalidated_gates(S.DRAFTING) == [
        Gate.COMPLIANCE_ATTESTATION,
        Gate.EXECUTIVE_APPROVAL,
        Gate.SUBMISSION_AUTHORIZATION,
    ]
    with pytest.raises(InvalidTransitionError):
        policy.assert_rollback(S.PLANNING, S.DRAFTING)
    with pytest.raises(InvalidTransitionError):
        policy.assert_rollback(S.SUBMITTED, S.PLANNING)


def _opportunity(
    due: datetime, tz: str = "America/New_York", system: SourceSystem = "grants_gov"
) -> GrantOpportunity:
    opp = factories.grant_opportunity()
    app_due = opp.deadlines.application_due
    assert app_due is not None
    deadlines = opp.deadlines.model_copy(
        update={"application_due": app_due.model_copy(update={"value": due, "timezone": tz})}
    )
    return opp.model_copy(
        update={
            "deadlines": deadlines,
            "source": Source(system=system, source_id="X"),
        }
    )


def test_deadline_plan_grants_gov_buffer_and_funder_timezone() -> None:
    # 2027-03-20 17:00 New York (EDT). Milestones three weeks earlier fall before DST starts.
    due = datetime(2027, 3, 20, 21, tzinfo=UTC)
    plan = plan_deadlines(_opportunity(due), NOW)
    assert plan.buffer_hours == 72
    assert plan.internal_deadline == due - timedelta(hours=72)
    go = next(m for m in plan.milestones if m.name == "go_no_go")
    assert go.due_at == datetime(2027, 2, 24, 22, tzinfo=UTC)  # 17:00 EST, wall clock kept
    assert [m.due_at for m in plan.milestones] == sorted(m.due_at for m in plan.milestones)


def test_deadline_plan_without_buffer_skips_past_milestones() -> None:
    due = NOW + timedelta(days=5)
    plan = plan_deadlines(_opportunity(due, "UTC", "candid"), NOW)
    assert plan.buffer_hours == 0 and plan.internal_deadline == due
    assert [m.name for m in plan.milestones] == [
        "executive_approval",
        "package_ready",
        "submission_authorization",
    ]


def test_rolling_opportunity_has_no_deadline() -> None:
    opp = factories.grant_opportunity()
    opp = opp.model_copy(
        update={"deadlines": opp.deadlines.model_copy(update={"application_due": None})}
    )
    assert plan_deadlines(opp, NOW).internal_deadline is None
