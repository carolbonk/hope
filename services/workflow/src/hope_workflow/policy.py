"""Deterministic gate and rollback policy (blueprint 4.3 guards, 4.4 gates). No I/O."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from hope_core.schemas.agency_profile import AgencyProfile, ApprovalRule
from hope_core.schemas.hitl import Decision, Gate
from hope_core.schemas.lifecycle import PRE_SUBMISSION_ACTIVE, InvalidTransitionError
from hope_core.schemas.lifecycle import OpportunityState as S

from hope_workflow.contracts import ProfileArea


@dataclass(frozen=True)
class GateDefault:
    state: S
    roles: tuple[str, ...]
    sla_hours: int | None
    escalate_to: str | None
    options: frozenset[Decision]


_APPROVE = frozenset[Decision]({"approve", "reject", "request_changes"})

GATES: dict[Gate, GateDefault] = {
    Gate.ELIGIBILITY_REVIEW: GateDefault(
        S.NEEDS_ELIGIBILITY_REVIEW, ("development_director",), 72, "executive_director", _APPROVE
    ),
    Gate.GO_NO_GO: GateDefault(
        S.AWAITING_GO_NO_GO,
        ("development_director",),
        5 * 24,
        "executive_director",
        frozenset({"go", "no_go", "defer"}),
    ),
    Gate.BUDGET_SIGNOFF: GateDefault(
        S.AWAITING_BUDGET_SIGNOFF, ("finance_director",), 72, "cfo", _APPROVE
    ),
    Gate.COMPLIANCE_ATTESTATION: GateDefault(
        S.AWAITING_COMPLIANCE, ("compliance_officer",), 48, "executive_director", _APPROVE
    ),
    Gate.EXECUTIVE_APPROVAL: GateDefault(
        S.AWAITING_EXEC_APPROVAL, ("executive_director",), None, None, _APPROVE
    ),
    Gate.SUBMISSION_AUTHORIZATION: GateDefault(
        S.AWAITING_SUBMISSION_AUTH, ("aor",), None, None, frozenset({"approve", "defer"})
    ),
}
"""Defaults from the 4.4 table, used when the approval hierarchy has no rule for a gate."""

PASSING: frozenset[Decision] = frozenset({"approve", "go"})


@dataclass(frozen=True)
class GatePolicy:
    roles: tuple[str, ...]
    min_approvals: int
    sla: timedelta | None
    escalate_to: str | None


def json_logic(rule: Any, data: dict[str, Any]) -> Any:
    """Minimal JSON Logic: var, ==, !=, <, <=, >, >=, and, or, !."""
    if not isinstance(rule, dict):
        return rule
    ((op, raw),) = rule.items()
    args = raw if isinstance(raw, list) else [raw]
    if op == "var":
        value: Any = data
        for key in str(args[0]).split("."):
            value = value.get(key) if isinstance(value, dict) else None
        return value if value is not None or len(args) < 2 else args[1]
    vals = [json_logic(a, data) for a in args]
    match op:
        case "and":
            return all(vals)
        case "or":
            return any(vals)
        case "!":
            return not vals[0]
        case "==":
            return vals[0] == vals[1]
        case "!=":
            return vals[0] != vals[1]
    if vals[0] is None or vals[1] is None:
        return False
    match op:
        case "<":
            return vals[0] < vals[1]
        case "<=":
            return vals[0] <= vals[1]
        case ">":
            return vals[0] > vals[1]
        case ">=":
            return vals[0] >= vals[1]
    raise ValueError(f"unsupported JSON Logic operator {op!r}")


def select_rule(
    rules: Iterable[ApprovalRule], gate: Gate, data: dict[str, Any]
) -> ApprovalRule | None:
    """A rule whose condition matches beats an unconditional rule for the same gate."""
    candidates = [r for r in rules if r.gate is gate]
    for rule in candidates:
        if rule.condition is not None and json_logic(rule.condition, data):
            return rule
    return next((r for r in candidates if r.condition is None), None)


def gate_policy(
    profile: AgencyProfile,
    gate: Gate,
    data: dict[str, Any],
    now: datetime,
    internal_deadline: datetime | None,
) -> GatePolicy:
    default = GATES[gate]
    rule = select_rule(profile.approval_hierarchy, gate, data)
    sla_hours = rule.sla_hours if rule and rule.sla_hours else default.sla_hours
    sla = timedelta(hours=sla_hours) if sla_hours else None
    if internal_deadline is not None:
        remaining = internal_deadline - now
        if gate is Gate.GO_NO_GO:
            sla = min(sla, remaining / 5) if sla else remaining / 5
        elif gate is Gate.SUBMISSION_AUTHORIZATION:
            sla = remaining
    return GatePolicy(
        roles=tuple(rule.approver_roles) if rule else default.roles,
        min_approvals=rule.min_approvals if rule else 1,
        sla=sla if sla is None or sla > timedelta(0) else None,
        escalate_to=(rule.escalate_to_role if rule else None) or default.escalate_to,
    )


AREA_STATE: dict[ProfileArea, S] = {
    ProfileArea.ELIGIBILITY: S.NORMALIZED,
    ProfileArea.BUDGET: S.PLANNING,
    ProfileArea.REQUIRED_SECTIONS: S.DRAFTING,
}
"""Earliest lifecycle state to re-run when an area changes. Other areas only reload context."""

PROFILE_PATH_AREAS: dict[str, tuple[ProfileArea, ...]] = {
    "legal": (ProfileArea.ELIGIBILITY,),
    "financials": (ProfileArea.BUDGET,),
    "approval_hierarchy": (ProfileArea.APPROVALS,),
}

_ORDER = list(S)


def rank(state: S) -> int:
    return _ORDER.index(state)


def areas_for_paths(paths: Iterable[str]) -> set[ProfileArea]:
    return {a for p in paths for a in PROFILE_PATH_AREAS.get(p.split(".")[0], ())}


def rollback_target(current: S, areas: Iterable[ProfileArea]) -> S | None:
    """Earliest affected state strictly before `current`, or None if nothing to roll back."""
    targets = [AREA_STATE[a] for a in areas if a in AREA_STATE]
    earliest = min(targets, key=rank, default=None)
    if earliest is None or current not in PRE_SUBMISSION_ACTIVE or rank(earliest) >= rank(current):
        return None
    return earliest


def assert_rollback(current: S, target: S) -> None:
    """Rollbacks are a global guard, not edges in the lifecycle table: validate them here."""
    if (
        current not in PRE_SUBMISSION_ACTIVE
        or target not in AREA_STATE.values()
        or rank(target) >= rank(current)
    ):
        raise InvalidTransitionError(f"rollback {current} -> {target} is not allowed")


def invalidated_gates(target: S) -> list[Gate]:
    """Approvals collected at or after `target` no longer hold once we roll back to it."""
    return [g for g, d in GATES.items() if rank(d.state) >= rank(target)]
