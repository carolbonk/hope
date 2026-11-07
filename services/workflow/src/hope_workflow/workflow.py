"""OpportunityLifecycleWorkflow (A0): deterministic control path, no LLM (blueprint 4, App. B).

Every forward transition goes through `assert_transition`. Global guards (deadline expiry and
revalidation rollback) interrupt the running step at a safe point and are validated in policy.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager, suppress
from datetime import timedelta
from typing import Any
from uuid import UUID

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from hope_core.hashing import content_hash
    from hope_core.pillar import RouteReceipt
    from hope_core.schemas.hitl import Gate, HitlDecision, HitlRequest
    from hope_core.schemas.lifecycle import PRE_SUBMISSION_ACTIVE, TERMINAL, assert_transition
    from hope_core.schemas.lifecycle import OpportunityState as S
    from hope_core.schemas.opportunity_matrix import MatrixRow
    from hope_core.schemas.proposal_framework import Approval, ProposalFramework
    from hope_core.topics import EventType

    from hope_workflow import policy
    from hope_workflow.activities import PlatformActivities
    from hope_workflow.agents import AgentActivities
    from hope_workflow.contracts import (
        AgentContext,
        AmendmentSignal,
        ApprovalRecord,
        BudgetDraft,
        BudgetRequest,
        ComplianceRequest,
        DeadlinePlan,
        DeadlinePlanRequest,
        EligibilityResult,
        EventRequest,
        LifecycleContext,
        LifecycleInput,
        LifecycleOutcome,
        LifecycleStatus,
        NarrativeDraft,
        NarrativeRequest,
        NotificationKind,
        NotificationRequest,
        PackageRequest,
        ProfileArea,
        ProjectionRow,
        RecommendRequest,
        RevalidateSignal,
        SubmissionPackage,
        SubmitRequest,
        VerificationReport,
        VerifyRequest,
    )
    from hope_workflow.deadlines import WARNING_OFFSETS
    from hope_workflow.queues import TaskQueue

AGENT_TIMEOUT = timedelta(minutes=15)
RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=8,
)
MAX_REVISIONS = 3
SYSTEM_ACTOR = "system:workflow"
DONE = TERMINAL | {S.SUBMITTED}


def lifecycle_workflow_id(tenant_id: UUID, agency_id: UUID, opportunity_id: UUID) -> str:
    return f"opportunity-lifecycle:{tenant_id}:{agency_id}:{opportunity_id}"


def _need[T](value: T | None) -> T:
    if value is None:
        raise RuntimeError("workflow step reached without its upstream artifact")
    return value


@workflow.defn
class OpportunityLifecycleWorkflow:
    def __init__(self) -> None:
        self.state = S.NORMALIZED
        self._ctx: LifecycleContext | None = None
        self._plan = DeadlinePlan(internal_deadline=None)
        self._plan_version = 0
        self._pending: HitlRequest | None = None
        self._decisions: list[HitlDecision] = []
        self._approvals: dict[Gate, HitlDecision] = {}
        self._changes: set[ProfileArea] | None = None
        self._expired = False
        self._critical = 0
        self._feedback: list[str] = []
        self._eligibility: EligibilityResult | None = None
        self._matrix_row: MatrixRow | None = None
        self._go: HitlDecision | None = None
        self._budget: BudgetDraft | None = None
        self._framework: ProposalFramework | None = None
        self._draft: NarrativeDraft | None = None
        self._package: SubmissionPackage | None = None
        self._receipt: RouteReceipt | None = None

    # ---- run loop and global guards -------------------------------------------------------

    @workflow.run
    async def run(self, inp: LifecycleInput) -> LifecycleOutcome:
        self._inp = inp
        self._wf_id = workflow.info().workflow_id
        self._ctx = await self._act(PlatformActivities.load_context, inp)
        await self._replan()
        await self._mirror()
        guard = asyncio.create_task(self._deadline_guard())
        while True:
            drive = asyncio.create_task(self._drive())
            await workflow.wait_condition(self._interrupted(drive))
            await workflow.wait_condition(lambda: self._critical == 0)
            if not drive.done():
                drive.cancel()
            with suppress(asyncio.CancelledError):
                await drive
            if self._expired and self.state in PRE_SUBMISSION_ACTIVE:
                await self._transition(S.EXPIRED, "internal deadline passed")
                await self._notify("expired", self._owner_roles(), "Opportunity expired")
            if self.state in DONE or self._expired:
                break
            if self._changes is not None:
                areas, self._changes = self._changes, None
                await self._apply_changes(areas)
        guard.cancel()
        return LifecycleOutcome(
            state=self.state, receipt=self._receipt, matrix_row=self._matrix_row
        )

    async def _deadline_guard(self) -> None:
        fired: set[str] = set()
        while True:
            version = self._plan_version
            upcoming = sorted((at, key) for key, at in self._timeline().items() if key not in fired)
            if not upcoming:
                await workflow.wait_condition(self._replanned(version))
                continue
            at, key = upcoming[0]
            delay = at - workflow.now()
            if delay > timedelta(0):
                try:
                    await workflow.wait_condition(self._replanned(version), timeout=delay)
                    continue
                except TimeoutError:
                    pass
            fired.add(key)
            if self.state not in PRE_SUBMISSION_ACTIVE:
                continue
            if key == "expire":
                self._expired = True
                return
            kind, _, name = key.partition(":")
            if kind == "warning":
                await self._notify(
                    "deadline_warning",
                    [*self._owner_roles(), "executive_director"],
                    f"Internal deadline in {name}h; current state {self.state}",
                )
            else:
                milestone = next(m for m in self._plan.milestones if m.name == name)
                await self._notify(
                    "milestone", [milestone.owner_role], f"Milestone due: {name}", milestone.gate
                )

    def _interrupted(self, drive: asyncio.Task[None]) -> Callable[[], bool]:
        return lambda: drive.done() or self._expired or self._changes is not None

    def _replanned(self, version: int) -> Callable[[], bool]:
        return lambda: self._plan_version != version

    def _timeline(self) -> dict[str, Any]:
        deadline = self._plan.internal_deadline
        if deadline is None:
            return {}
        events: dict[str, Any] = {f"milestone:{m.name}": m.due_at for m in self._plan.milestones}
        for offset in WARNING_OFFSETS:
            events[f"warning:{int(offset.total_seconds() // 3600)}"] = deadline - offset
        events["expire"] = deadline
        return events

    async def _apply_changes(self, areas: set[ProfileArea]) -> None:
        self._pending = None
        self._ctx = await self._act(PlatformActivities.load_context, self._inp)
        await self._replan()
        target = policy.rollback_target(self.state, areas)
        if target is None:
            return
        policy.assert_rollback(self.state, target)
        for gate in policy.invalidated_gates(target):
            if (old := self._approvals.pop(gate, None)) is not None:
                await self._record(gate, "invalidated", old.artifact_hash, SYSTEM_ACTOR, target)
        self._feedback = [f"revalidation: {', '.join(sorted(areas))}"]
        await self._set_state(target, f"rollback: {', '.join(sorted(areas))}")
        await self._notify(
            "revalidation", self._owner_roles(), f"Re-running from {target} after a change"
        )

    async def _replan(self) -> None:
        req = DeadlinePlanRequest(opportunity=self._context.opportunity, now=workflow.now())
        self._plan = await self._act(PlatformActivities.plan_deadlines, req, TaskQueue.NOTIFY)
        self._plan_version += 1

    # ---- signals and queries -------------------------------------------------------------

    @workflow.signal
    def submit_decision(self, decision: HitlDecision) -> None:
        if self._pending is not None:
            self._decisions.append(decision)

    @workflow.signal
    def revalidate(self, signal: RevalidateSignal) -> None:
        self._queue_change(policy.areas_for_paths(signal.changed_paths))

    @workflow.signal
    def opportunity_amended(self, signal: AmendmentSignal) -> None:
        self._queue_change({*signal.affected, ProfileArea.DEADLINE})

    def _queue_change(self, areas: set[ProfileArea]) -> None:
        if self.state not in DONE:
            self._changes = (self._changes or set()) | areas

    @workflow.query
    def status(self) -> LifecycleStatus:
        return LifecycleStatus(
            state=self.state, pending=self._pending, approvals=self._approvals, plan=self._plan
        )

    # ---- lifecycle steps -----------------------------------------------------------------

    async def _drive(self) -> None:
        steps: dict[S, Callable[[], Awaitable[None]]] = {
            S.NORMALIZED: self._screen_eligibility,
            S.NEEDS_ELIGIBILITY_REVIEW: self._review_eligibility,
            S.SCREENED: self._recommend,
            S.RECOMMENDED: lambda: self._transition(S.AWAITING_GO_NO_GO),
            S.AWAITING_GO_NO_GO: self._go_no_go,
            S.PLANNING: self._plan_budget,
            S.AWAITING_BUDGET_SIGNOFF: self._budget_signoff,
            S.DRAFTING: self._draft_narrative,
            S.IN_REVIEW: self._check_compliance,
            S.AWAITING_COMPLIANCE: self._compliance_attestation,
            S.AWAITING_EXEC_APPROVAL: self._exec_approval,
            S.PACKAGING: self._assemble_package,
            S.AWAITING_SUBMISSION_AUTH: self._authorize_and_submit,
            S.SUBMISSION_ERROR: lambda: self._transition(S.PACKAGING, "retry after portal error"),
        }
        while self.state not in DONE:
            await steps[self.state]()

    async def _screen_eligibility(self) -> None:
        result = await self._agent(
            AgentActivities.eligibility, self._agent_ctx(), TaskQueue.ELIGIBILITY
        )
        self._eligibility = result
        target = {
            "eligible": S.SCREENED,
            "needs_review": S.NEEDS_ELIGIBILITY_REVIEW,
            "ineligible": S.INELIGIBLE,
        }[result.status]
        await self._transition(target, "; ".join(result.reasons))

    async def _review_eligibility(self) -> None:
        result = _need(self._eligibility)
        decision = await self._gate(
            Gate.ELIGIBILITY_REVIEW, content_hash(result), "Review an ambiguous eligibility clause"
        )
        passed = decision.decision in policy.PASSING
        await self._transition(S.SCREENED if passed else S.INELIGIBLE, decision.comment)

    async def _recommend(self) -> None:
        ctx = self._agent_ctx()
        alignment = await self._agent(AgentActivities.alignment, ctx, TaskQueue.ALIGNMENT)
        row = await self._agent(
            AgentActivities.recommend,
            RecommendRequest(ctx=ctx, alignment=alignment),
            TaskQueue.RECOMMEND,
        )
        self._matrix_row = row
        skip = row.recommendation in ("watch", "skip")
        await self._transition(S.ARCHIVED if skip else S.RECOMMENDED, row.recommendation)

    async def _go_no_go(self) -> None:
        row = _need(self._matrix_row)
        decision = await self._gate(
            Gate.GO_NO_GO,
            content_hash(row),
            f"Go/No-Go: {self._context.opportunity.title} (score {row.composite_score:.0f})",
            {"composite_score": row.composite_score, "recommendation": row.recommendation},
        )
        if decision.decision == "go":
            self._go = decision
            await self._transition(S.PLANNING, "GO")
        elif decision.decision == "no_go":
            await self._transition(S.DECLINED, decision.comment or "NO-GO")

    async def _plan_budget(self) -> None:
        go = _need(self._go)

        async def produce(ctx: AgentContext) -> BudgetDraft:
            return await self._agent(
                AgentActivities.budget, BudgetRequest(ctx=ctx, go=go), TaskQueue.BUDGET
            )

        async def verify(draft: BudgetDraft) -> VerificationReport:
            req = VerifyRequest(
                ctx=self._agent_ctx(), subject="framework", framework=draft.framework
            )
            return await self._agent(AgentActivities.verify, req, TaskQueue.VERIFY)

        budget, self._feedback = await self._until_verified(produce, verify)
        self._budget = budget
        await self._transition(S.AWAITING_BUDGET_SIGNOFF, "framework verified")

    async def _budget_signoff(self) -> None:
        draft = _need(self._budget)
        framework = draft.framework
        forbidden = frozenset() if self._inp.small_org_ack else frozenset({draft.drafted_by})
        decision = await self._gate(
            Gate.BUDGET_SIGNOFF,
            _need(framework.content_hash),
            f"Budget sign-off: request {framework.budget.totals.request_minor / 100:,.2f}",
            {"request_minor": framework.budget.totals.request_minor},
            forbidden,
        )
        if decision.decision not in policy.PASSING:
            self._feedback = [decision.comment or decision.decision]
            await self._transition(S.PLANNING, "budget changes requested")
            return
        approval = Approval(
            gate=Gate.BUDGET_SIGNOFF,
            approver_user_id=decision.decided_by,
            approved_hash=decision.artifact_hash,
            at=decision.decided_at,
        )
        self._framework = framework.model_copy(
            update={"status": "approved_locked", "approvals": [*framework.approvals, approval]}
        )
        await self._transition(S.DRAFTING, "framework locked")

    async def _draft_narrative(self) -> None:
        framework = _need(self._framework)

        async def produce(ctx: AgentContext) -> NarrativeDraft:
            req = NarrativeRequest(ctx=ctx, framework=framework)
            return await self._agent(AgentActivities.narrative, req, TaskQueue.NARRATIVE)

        async def verify(draft: NarrativeDraft) -> VerificationReport:
            req = VerifyRequest(
                ctx=self._agent_ctx(), subject="narrative", framework=framework, draft=draft
            )
            return await self._agent(AgentActivities.verify, req, TaskQueue.VERIFY)

        draft, self._feedback = await self._until_verified(produce, verify)
        self._draft = draft
        await self._transition(S.IN_REVIEW, "sections verified")

    async def _check_compliance(self) -> None:
        req = ComplianceRequest(
            ctx=self._agent_ctx(self._take_feedback()),
            framework=_need(self._framework),
            draft=_need(self._draft),
        )
        report = await self._agent(AgentActivities.compliance, req, TaskQueue.COMPLIANCE)
        if report.passed:
            await self._transition(S.AWAITING_COMPLIANCE, "compliance checklist pass")
        else:
            self._feedback = report.deficiencies
            await self._transition(S.DRAFTING, "compliance deficiencies")

    async def _compliance_attestation(self) -> None:
        await self._draft_gate(
            Gate.COMPLIANCE_ATTESTATION, "Compliance attestation", S.AWAITING_EXEC_APPROVAL
        )

    async def _exec_approval(self) -> None:
        await self._draft_gate(Gate.EXECUTIVE_APPROVAL, "Executive approval", S.PACKAGING)

    async def _draft_gate(self, gate: Gate, summary: str, on_pass: S) -> None:
        framework = _need(self._framework)
        data = {"request_minor": framework.budget.totals.request_minor}
        decision = await self._gate(gate, _need(self._draft).content_hash, summary, data)
        if decision.decision in policy.PASSING:
            await self._transition(on_pass, f"{gate} approved")
        else:
            self._feedback = [decision.comment or decision.decision]
            await self._transition(S.DRAFTING, f"{gate} returned")

    async def _assemble_package(self) -> None:
        req = PackageRequest(
            ctx=self._agent_ctx(), framework=_need(self._framework), draft=_need(self._draft)
        )
        package = await self._agent(AgentActivities.package, req, TaskQueue.PACKAGE)
        self._package = package
        if package.valid:
            await self._transition(S.AWAITING_SUBMISSION_AUTH, "package valid")
        else:
            self._feedback = package.errors
            await self._transition(S.DRAFTING, "package validation failed")

    async def _authorize_and_submit(self) -> None:
        package = _need(self._package)
        decision = await self._gate(
            Gate.SUBMISSION_AUTHORIZATION,
            package.manifest_hash,
            f"Authorize submission via {package.channel}",
        )
        if decision.decision != "approve":
            return
        with self._critical_section():
            await self._publish(
                EventType.SUBMISSION_AUTHORIZED,
                {"manifest_hash": package.manifest_hash, "authorized_by": decision.decided_by},
            )
            req = SubmitRequest(
                ctx=self._agent_ctx(), package=package, authorized_by=decision.decided_by
            )
            receipt = await self._agent(AgentActivities.submit, req, TaskQueue.SUBMIT)
            self._receipt = receipt
            await self._transition(S.SUBMITTED, receipt.tracking_id)
            if not receipt.accepted:
                await self._transition(S.SUBMISSION_ERROR, receipt.reason)

    async def _until_verified[T](
        self,
        produce: Callable[[AgentContext], Awaitable[T]],
        verify: Callable[[T], Awaitable[VerificationReport]],
    ) -> tuple[T, list[str]]:
        """Produce, verify, retry with the critic's issues. Unresolved issues go to the human."""
        feedback = self._take_feedback()
        for _ in range(MAX_REVISIONS):
            output = await produce(self._agent_ctx(feedback))
            report = await verify(output)
            if report.passed:
                return output, []
            feedback = report.issues
        return output, feedback

    # ---- HITL gate -----------------------------------------------------------------------

    async def _gate(
        self,
        gate: Gate,
        artifact_hash: str,
        summary: str,
        data: dict[str, Any] | None = None,
        forbidden: frozenset[str] = frozenset(),
    ) -> HitlDecision:
        """Signal + timer gate (blueprint 4.4). Returns the deciding HitlDecision."""
        pol = policy.gate_policy(
            self._context.profile, gate, data or {}, workflow.now(), self._plan.internal_deadline
        )
        roles = list(pol.roles)
        if self._feedback:
            summary = f"{summary} (unresolved: {'; '.join(self._take_feedback())})"
        due = workflow.now() + pol.sla if pol.sla else None
        request = await self._open_request(gate, artifact_hash, roles, due, summary)
        approvals: dict[str, HitlDecision] = {}
        escalated = False
        while True:
            timeout = request.due_at - workflow.now() if request.due_at else None
            try:
                await workflow.wait_condition(
                    lambda: bool(self._decisions), timeout=timeout if timeout else None
                )
            except TimeoutError:
                if pol.escalate_to and not escalated:
                    escalated = True
                    roles = [*roles, pol.escalate_to] if pol.escalate_to not in roles else roles
                    await self._notify(
                        "escalation", [pol.escalate_to], f"{gate} SLA missed: {summary}", gate
                    )
                request = request.model_copy(update={"approver_roles": roles, "due_at": None})
                self._pending = request
                continue
            decision = self._decisions.pop(0)
            if decision.artifact_hash != request.artifact_hash:
                await self._notify(
                    "hitl_rejected", roles, f"{gate} decision was for a stale artifact", gate
                )
                approvals.clear()
                request = await self._open_request(
                    gate, artifact_hash, roles, request.due_at, summary
                )
                continue
            problem = self._invalid(decision, request, forbidden, approvals)
            if problem:
                await self._notify(
                    "hitl_rejected", roles, f"{gate} decision rejected: {problem}", gate
                )
                continue
            with self._critical_section():
                await self._record(
                    gate,
                    decision.decision,
                    decision.artifact_hash,
                    decision.decided_by,
                    decision.comment,
                )
                await self._publish(EventType.HITL_DECIDED, decision.model_dump(mode="json"))
            if decision.decision in policy.PASSING:
                approvals[decision.decided_by] = decision
                if len(approvals) < pol.min_approvals:
                    continue
                self._approvals[gate] = decision
            self._pending = None
            return decision

    def _invalid(
        self,
        d: HitlDecision,
        request: HitlRequest,
        forbidden: frozenset[str],
        approvals: dict[str, HitlDecision],
    ) -> str | None:
        if d.request_id != request.request_id or d.gate is not request.gate:
            return "unknown request"
        if d.decision not in policy.GATES[request.gate].options:
            return f"decision {d.decision!r} is not an option"
        if d.details.get("role") not in request.approver_roles:
            return "approver role not allowed"
        if d.decided_by in forbidden:
            return "separation of duties"
        if d.decided_by in approvals:
            return "duplicate approver"
        return None

    async def _open_request(
        self, gate: Gate, artifact_hash: str, roles: list[str], due: Any, summary: str
    ) -> HitlRequest:
        request = HitlRequest(
            request_id=workflow.uuid4(),
            tenant_id=self._inp.tenant_id,
            workflow_id=self._wf_id,
            gate=gate,
            artifact_hash=artifact_hash,
            approver_roles=roles,
            due_at=due,
            summary=summary,
        )
        self._pending = request
        with self._critical_section():
            await self._publish(EventType.HITL_REQUESTED, request.model_dump(mode="json"))
            await self._notify("hitl_requested", roles, summary, gate)
        return request

    # ---- side effects (activities) -------------------------------------------------------

    async def _transition(self, target: S, reason: str | None = None) -> None:
        assert_transition(self.state, target)
        await self._set_state(target, reason)

    async def _set_state(self, target: S, reason: str | None) -> None:
        with self._critical_section():
            previous, self.state = self.state, target
            await self._publish(
                EventType.OPPORTUNITY_STATE_CHANGED,
                {"from": previous.value, "to": target.value, "reason": reason},
            )
            await self._mirror()

    async def _mirror(self) -> None:
        row = self._matrix_row
        await self._act(
            PlatformActivities.mirror_state,
            ProjectionRow(
                tenant_id=self._inp.tenant_id,
                opportunity_id=self._inp.opportunity_id,
                agency_id=self._inp.agency_id,
                state=self.state,
                workflow_id=self._wf_id,
                composite_score=row.composite_score if row else None,
                recommendation=row.recommendation if row else None,
                internal_deadline=self._plan.internal_deadline,
            ),
        )

    async def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        req = EventRequest(
            event_id=workflow.uuid4(),
            event_type=event_type,
            tenant_id=self._inp.tenant_id,
            subject_id=str(self._inp.opportunity_id),
            workflow_id=self._wf_id,
            payload=payload,
        )
        await self._act(PlatformActivities.publish, req)

    async def _record(
        self, gate: Gate, decision: str, artifact_hash: str, by: str, comment: str | None
    ) -> None:
        record = ApprovalRecord(
            approval_id=workflow.uuid4(),
            tenant_id=self._inp.tenant_id,
            workflow_id=self._wf_id,
            gate=gate,
            decision=decision,
            artifact_hash=artifact_hash,
            decided_by=by,
            decided_at=workflow.now(),
            comment=comment,
        )
        await self._act(PlatformActivities.record_approval, record)

    async def _notify(
        self, kind: NotificationKind, roles: list[str], title: str, gate: Gate | None = None
    ) -> None:
        req = NotificationRequest(
            notification_id=workflow.uuid4(),
            tenant_id=self._inp.tenant_id,
            workflow_id=self._wf_id,
            subject_id=str(self._inp.opportunity_id),
            kind=kind,
            recipient_roles=list(dict.fromkeys(roles)),
            title=title,
            gate=gate,
        )
        await self._act(PlatformActivities.notify, req, TaskQueue.NOTIFY)

    async def _act[A, R](
        self,
        fn: Callable[[PlatformActivities, A], Awaitable[R]],
        arg: A,
        queue: TaskQueue = TaskQueue.WORKFLOW,
    ) -> R:
        return await workflow.execute_activity_method(
            fn,
            arg,
            task_queue=queue,
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RETRY,
        )

    async def _agent[A, R](
        self, fn: Callable[[AgentActivities, A], Awaitable[R]], arg: A, queue: TaskQueue
    ) -> R:
        return await workflow.execute_activity_method(
            fn, arg, task_queue=queue, start_to_close_timeout=AGENT_TIMEOUT, retry_policy=RETRY
        )

    # ---- helpers -------------------------------------------------------------------------

    @property
    def _context(self) -> LifecycleContext:
        return _need(self._ctx)

    def _agent_ctx(self, feedback: list[str] | None = None) -> AgentContext:
        return AgentContext(
            tenant_id=self._inp.tenant_id,
            agency_id=self._inp.agency_id,
            workflow_id=self._wf_id,
            profile=self._context.profile,
            opportunity=self._context.opportunity,
            feedback=feedback or [],
        )

    def _take_feedback(self) -> list[str]:
        feedback, self._feedback = self._feedback, []
        return feedback

    def _owner_roles(self) -> list[str]:
        return self._pending.approver_roles if self._pending else ["development_director"]

    @contextmanager
    def _critical_section(self) -> Iterator[None]:
        """Guards wait for these to finish so a state change and its events stay together."""
        self._critical += 1
        try:
            yield
        finally:
            self._critical -= 1
