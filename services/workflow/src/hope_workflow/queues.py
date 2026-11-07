from __future__ import annotations

from enum import StrEnum


class TaskQueue(StrEnum):
    """One task queue per agent so each scales on its own (blueprint 4.1)."""

    WORKFLOW = "q.workflow"
    ELIGIBILITY = "q.eligibility"
    ALIGNMENT = "q.align"
    RECOMMEND = "q.recommend"
    BUDGET = "q.budget"
    VERIFY = "q.verify"
    NARRATIVE = "q.draft"
    COMPLIANCE = "q.compliance"
    PACKAGE = "q.package"
    SUBMIT = "q.submit"
    NOTIFY = "q.notify"
