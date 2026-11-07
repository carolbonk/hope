from datetime import timedelta

import pytest
from hope_core.schemas.agency_profile import ApprovalRule
from hope_core.schemas.hitl import Gate
from hope_core.schemas.lifecycle import OpportunityState as S
from hope_core.testing import factories
from hope_core.topics import EventType
from hope_workflow.contracts import AmendmentSignal, LifecycleContext, ProfileArea, RevalidateSignal
from hope_workflow.stubs import StubAgents
from hope_workflow.testing import LifecycleHarness, lifecycle_harness, sample_context
from hope_workflow.workflow import OpportunityLifecycleWorkflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Replayer

DRAFT_GATES = (Gate.COMPLIANCE_ATTESTATION, Gate.EXECUTIVE_APPROVAL)


async def go_and_sign_budget(h: LifecycleHarness) -> None:
    await h.decide(Gate.GO_NO_GO, "go", owner="user:owner")
    await h.decide(Gate.BUDGET_SIGNOFF)


async def test_happy_path_reaches_submitted() -> None:
    async with lifecycle_harness() as h:
        handle = await h.start(sample_context())
        await go_and_sign_budget(h)
        await h.approve_all(*DRAFT_GATES, Gate.SUBMISSION_AUTHORIZATION)
        outcome = await handle.result()

        assert outcome.state is S.SUBMITTED
        assert outcome.receipt is not None and outcome.receipt.accepted
        assert h.pillar.outbound[0].authorized_by == "user:aor"
        states = [e["to"] for e in h.events(EventType.OPPORTUNITY_STATE_CHANGED)]
        assert states == [
            "Screened", "Recommended", "AwaitingGoNoGo", "Planning", "AwaitingBudgetSignoff",
            "Drafting", "InReview", "AwaitingCompliance", "AwaitingExecApproval", "Packaging",
            "AwaitingSubmissionAuth", "Submitted",
        ]  # fmt: skip
        assert [r.gate for r in h.approvals.records] == list(Gate)[1:6]
        assert len(h.events(EventType.HITL_REQUESTED)) == len(h.events(EventType.HITL_DECIDED)) == 5
        assert len(h.events(EventType.SUBMISSION_AUTHORIZED)) == 1
        assert h.events(EventType.NOTIFICATION_REQUESTED)
        (row,) = h.projection.rows.values()
        assert row.state is S.SUBMITTED and row.recommendation == "pursue"
        assert row.internal_deadline is not None
        assert h.agents.calls.count("budget") == 1


async def test_duplicate_start_is_idempotent() -> None:
    async with lifecycle_harness() as h:
        ctx = sample_context()
        first = await h.start(ctx)
        second = await h.start(ctx)
        assert first.id == second.id and first.result_run_id == second.result_run_id
        assert first.id.endswith(f"{ctx.profile.agency_id}:{ctx.opportunity.opportunity_id}")
        await first.terminate()


async def test_no_go_declines() -> None:
    async with lifecycle_harness() as h:
        handle = await h.start(sample_context())
        await h.decide(Gate.GO_NO_GO, "no_go", comment="capacity")
        assert (await handle.result()).state is S.DECLINED
        assert [r.decision for r in h.approvals.records] == ["no_go"]
        assert "budget" not in h.agents.calls


@pytest.mark.parametrize(
    ("agents", "final"),
    [
        (StubAgents(eligibility_status="ineligible"), S.INELIGIBLE),
        (StubAgents(recommendation="skip"), S.ARCHIVED),
    ],
)
async def test_screening_closes_early(agents: StubAgents, final: S) -> None:
    async with lifecycle_harness(agents) as h:
        handle = await h.start(sample_context())
        assert (await handle.result()).state is final


async def test_eligibility_review_gate() -> None:
    async with lifecycle_harness(StubAgents(eligibility_status="needs_review")) as h:
        handle = await h.start(sample_context())
        await h.decide(Gate.ELIGIBILITY_REVIEW, "reject")
        assert (await handle.result()).state is S.INELIGIBLE


async def test_stale_hash_is_rejected_and_gate_rerequested() -> None:
    async with lifecycle_harness() as h:
        handle = await h.start(sample_context())
        first = await h.decide(Gate.GO_NO_GO, "go", artifact_hash="sha256:stale")
        second = await h.wait_for_gate(Gate.GO_NO_GO)

        assert second.request_id != first.request_id
        assert second.artifact_hash == first.artifact_hash
        assert h.approvals.records == []
        assert h.notifications("hitl_rejected")
        assert (await h.status()).state is S.AWAITING_GO_NO_GO

        await h.decide(Gate.GO_NO_GO, "no_go")
        assert (await handle.result()).state is S.DECLINED
        assert len(h.events(EventType.HITL_REQUESTED)) == 2


async def test_separation_of_duties_on_budget_signoff() -> None:
    async with lifecycle_harness() as h:
        handle = await h.start(sample_context())
        await h.decide(Gate.GO_NO_GO, "go", owner="user:alice")
        request = await h.decide(Gate.BUDGET_SIGNOFF, by="user:alice")
        await h.wait_for_notification("separation of duties")
        status = await h.status()
        assert status.state is S.AWAITING_BUDGET_SIGNOFF
        assert status.pending is not None and status.pending.request_id == request.request_id

        h.forget(request)
        await h.decide(Gate.BUDGET_SIGNOFF, by="user:bob")
        await h.approve_all(*DRAFT_GATES)
        await h.wait_for_gate(Gate.SUBMISSION_AUTHORIZATION)
        signoff = [r for r in h.approvals.records if r.gate is Gate.BUDGET_SIGNOFF]
        assert [r.decided_by for r in signoff] == ["user:bob"]
        await handle.terminate()


async def test_sla_escalation() -> None:
    ctx = sample_context()
    profile = ctx.profile.model_copy(
        update={
            "approval_hierarchy": [
                ApprovalRule(gate=Gate.GO_NO_GO, approver_roles=["development_director"]),
                ApprovalRule(
                    gate=Gate.BUDGET_SIGNOFF,
                    approver_roles=["finance_director"],
                    sla_hours=24,
                    escalate_to_role="cfo",
                ),
                ApprovalRule(
                    gate=Gate.BUDGET_SIGNOFF,
                    condition={">": [{"var": "request_minor"}, 100_000_000]},
                    approver_roles=["board_treasurer"],
                ),
            ]
        }
    )
    async with lifecycle_harness() as h:
        handle = await h.start(LifecycleContext(profile=profile, opportunity=ctx.opportunity))
        await h.decide(Gate.GO_NO_GO, "go")
        before = await h.wait_for_gate(Gate.BUDGET_SIGNOFF)
        assert before.approver_roles == ["finance_director"]
        assert before.due_at is not None

        await h.env.sleep(timedelta(hours=25))
        after = (await h.status()).pending
        assert after is not None and after.approver_roles == ["finance_director", "cfo"]
        assert h.notifications("escalation")
        assert any(n.recipient_roles == ["cfo"] for n in h.channel.sent if n.kind == "escalation")

        await h.decide(Gate.BUDGET_SIGNOFF, role="cfo")
        await h.wait_for_gate(Gate.COMPLIANCE_ATTESTATION)
        await handle.terminate()


async def test_deadline_expiry_with_warnings() -> None:
    async with lifecycle_harness() as h:
        now = await h.env.get_current_time()
        ctx = sample_context()
        opp = ctx.opportunity
        due = opp.deadlines.application_due
        assert due is not None
        deadlines = opp.deadlines.model_copy(
            update={"application_due": due.model_copy(update={"value": now + timedelta(days=8)})}
        )
        ctx = LifecycleContext(
            profile=ctx.profile, opportunity=opp.model_copy(update={"deadlines": deadlines})
        )
        handle = await h.start(ctx)
        await h.wait_for_gate(Gate.GO_NO_GO)
        outcome = await handle.result()

        assert outcome.state is S.EXPIRED
        warnings = h.notifications("deadline_warning")
        assert [w.split()[3] for w in warnings] == ["72h;", "24h;"]
        assert h.notifications("expired")
        assert h.notifications("escalation")
        (row,) = h.projection.rows.values()
        assert row.state is S.EXPIRED
        assert row.internal_deadline == now + timedelta(days=8) - timedelta(hours=72)


async def test_revalidation_rolls_back_and_invalidates_approvals() -> None:
    async with lifecycle_harness() as h:
        ctx = sample_context()
        handle = await h.start(ctx)
        await go_and_sign_budget(h)
        await h.decide(Gate.COMPLIANCE_ATTESTATION)
        await h.wait_for_gate(Gate.EXECUTIVE_APPROVAL)
        first_hash = h.approvals.records[1].artifact_hash

        h.contexts.put(
            ctx.model_copy(update={"profile": ctx.profile.model_copy(update={"version": 2})})
        )
        await handle.signal(
            OpportunityLifecycleWorkflow.revalidate,
            RevalidateSignal(profile_version=2, changed_paths=["financials.indirect_rate"]),
        )
        resign = await h.wait_for_gate(Gate.BUDGET_SIGNOFF)
        assert resign.artifact_hash != first_hash

        invalidated = {r.gate for r in h.approvals.records if r.decision == "invalidated"}
        assert invalidated == {Gate.BUDGET_SIGNOFF, Gate.COMPLIANCE_ATTESTATION}
        status = await h.status()
        assert set(status.approvals) == {Gate.GO_NO_GO}
        assert h.notifications("revalidation")
        assert h.events(EventType.OPPORTUNITY_STATE_CHANGED)[-2]["to"] == "Planning"

        await h.decide(Gate.BUDGET_SIGNOFF)
        await h.approve_all(*DRAFT_GATES, Gate.SUBMISSION_AUTHORIZATION)
        assert (await handle.result()).state is S.SUBMITTED
        assert h.agents.calls.count("eligibility") == 1


async def test_amendment_touching_eligibility_restarts_screening() -> None:
    async with lifecycle_harness() as h:
        handle = await h.start(sample_context())
        await h.decide(Gate.GO_NO_GO, "go")
        await h.wait_for_gate(Gate.BUDGET_SIGNOFF)
        await handle.signal(
            OpportunityLifecycleWorkflow.opportunity_amended,
            AmendmentSignal(amendment_seq=1, affected=[ProfileArea.ELIGIBILITY]),
        )
        await h.decide(Gate.GO_NO_GO, "no_go")
        assert (await handle.result()).state is S.DECLINED
        assert h.agents.calls.count("eligibility") == 2
        assert [r.decision for r in h.approvals.records] == ["go", "invalidated", "no_go"]


def test_factories_profile_has_hierarchy() -> None:
    assert factories.agency_profile().approval_hierarchy


async def test_history_replays_deterministically() -> None:
    async with lifecycle_harness() as h:
        handle = await h.start(sample_context())
        await go_and_sign_budget(h)
        await h.approve_all(*DRAFT_GATES, Gate.SUBMISSION_AUTHORIZATION)
        await handle.result()
        history = await handle.fetch_history()
    replayer = Replayer(
        workflows=[OpportunityLifecycleWorkflow], data_converter=pydantic_data_converter
    )
    await replayer.replay_workflow(history)
