"""Per-grant rules checked against the profile by code (no model)."""

from __future__ import annotations

from datetime import date

from hope_core.money import Money
from hope_core.schemas.agency_profile import Capacity, SamRegistration
from hope_core.testing.factories import agency_profile
from hope_discovery.requirements import (
    Attachment,
    BudgetRequirements,
    Limit,
    Question,
    Requirements,
    Sourced,
    Submission,
    diff_requirements,
    question_key,
)
from hope_discovery.rules import RuleCheck, apply_staff, check_rules

U = "pasted"


def usd(n: int) -> Money:
    return Money(amount_minor=n * 100, currency="USD")


def label(rules: list[RuleCheck], text: str) -> RuleCheck:
    return next(r for r in rules if text in r.label)


def test_eligibility_checked_against_the_profile() -> None:
    p = agency_profile()
    p = p.model_copy(
        update={
            "legal": p.legal.model_copy(
                update={"sam_registration": SamRegistration(status="expired")}
            )
        }
    )
    req = Requirements(
        eligibility=[
            Sourced(text="Applicants must be 501(c)(3) nonprofits.", url=U),
            Sourced(text="Applicants must have an active SAM.gov registration and a UEI.", url=U),
            Sourced(text="Organizations must be located in Ohio.", url=U),
            Sourced(text="Open to organizations serving the State of Texas.", url=U),
            Sourced(
                text="Applicants must have an annual operating budget under $1 million.", url=U
            ),
            Sourced(text="Applicants must have been operating for at least three years.", url=U),
            Sourced(text="Priority goes to grassroots groups.", url=U),
        ],
        submission=Submission(deadline_date=date(2027, 3, 1)),
    )
    rules = {r.quote: r for r in check_rules(req, p, None)}
    s = [r.status for r in rules.values()]
    assert s == ["met", "not_met", "met", "not_met", "not_met", "unknown", "unknown"]
    sam = rules["Applicants must have an active SAM.gov registration and a UEI."]
    assert sam.label == "SAM.gov registration, UEI"
    assert "expired" in sam.reason and "No UEI" in sam.reason and sam.todo
    budget = rules["Applicants must have an annual operating budget under $1 million."]
    assert budget.reason == "Your annual budget is $1,850,000; the funder wants at most $1,000,000."
    assert "Texas" in rules["Open to organizations serving the State of Texas."].reason


def test_budget_rules_use_the_request_amount() -> None:
    p = agency_profile(capacity=Capacity(cost_share_capacity=usd(20_000)))
    req = Requirements(
        budget=BudgetRequirements(
            max_request=Sourced(text="Maximum award: $150,000.", url=U),
            max_request_amount=usd(150_000),
            match_rule=Sourced(text="A 1:1 cost share is required.", url=U),
            indirect_rule=Sourced(text="Indirect costs may not exceed 10% of direct costs.", url=U),
        )
    )
    no_ask = check_rules(req, p, None)
    assert label(no_ask, "Maximum").todo == "Set how much you're requesting."
    assert label(no_ask, "Match").status == "unknown"

    rules = check_rules(req, p, usd(75_000))
    assert label(rules, "Maximum").status == "met"
    match = label(rules, "Match")
    assert match.status == "not_met"
    assert match.todo == (
        "Line up $75,000 in match (cash or in-kind) and document where it comes from."
    )
    indirect = label(rules, "Indirect")
    assert (indirect.status, indirect.reason) == ("not_met", "Your rate is 15%, above the 10% cap.")
    assert label(check_rules(req, p, usd(200_000)), "Maximum").status == "not_met"


def test_conditional_rules_apply_only_when_their_condition_is_true() -> None:
    p = agency_profile()
    req = Requirements(
        conditions=[
            Sourced(text="Applicants requesting more than $50,000 must submit an audit.", url=U),
            Sourced(text="If you use a fiscal sponsor, attach their letter of agreement.", url=U),
            Sourced(text="If this is your first application, call us first.", url=U),
        ],
        attachments=[
            Attachment(
                name="Board list",
                quote="Organizations with budgets over $1 million must upload a board list.",
                url=U,
            )
        ],
    )
    small = {r.quote[:12]: r.status for r in check_rules(req, p, usd(25_000))}
    big = {r.quote[:12]: r.status for r in check_rules(req, p, usd(75_000))}
    assert small == {
        "Applicants r": "not_applicable",
        "If you use a": "not_applicable",
        "If this is y": "unknown",
        "Organization": "applies",
    }
    assert big["Applicants r"] == "applies"
    audit = next(r for r in check_rules(req, p, usd(75_000)) if r.quote.startswith("Applicants"))
    assert audit.owner == "finance" and audit.todo and "audit" in audit.todo


def test_staff_settle_what_code_cannot() -> None:
    req = Requirements(eligibility=[Sourced(text="Priority goes to grassroots groups.", url=U)])
    [rule] = check_rules(req, agency_profile(), None)
    [settled] = apply_staff([rule], {rule.key: {"status": "yes", "note": "We are."}})
    assert (settled.status, settled.reason, settled.confirmed_by_staff) == (
        "met",
        "Confirmed by staff: We are.",
        True,
    )


def test_what_changed_between_reads() -> None:
    def q(prompt: str, n: int) -> Question:
        return Question(
            key=question_key(prompt), prompt=prompt, url=U, limit=Limit(unit="words", max=n)
        )

    old = Requirements(
        questions=[q("Describe the need.", 500), q("Describe your board.", 200)],
        attachments=[Attachment(name="Budget", quote="Attach a budget.", url=U)],
        submission=Submission(deadline_date=date(2027, 3, 1)),
    )
    new = Requirements(
        questions=[q("Describe the need.", 300), q("How will you sustain it?", 250)],
        attachments=[
            Attachment(name="Budget", quote="Attach a budget.", url=U),
            Attachment(name="Audit", quote="Attach an audit.", url=U),
        ],
        submission=Submission(deadline_date=date(2027, 3, 15)),
    )
    got = [(c.what, c.change, c.text, c.before) for c in diff_requirements(old, new)]
    assert got == [
        ("question", "added", "How will you sustain it?", None),
        ("question", "removed", "Describe your board.", None),
        ("limit", "changed", "Describe the need.: 300 words", "500 words"),
        ("upload", "added", "Audit", None),
        ("deadline", "changed", "March 15, 2027", "March 1, 2027"),
    ]
