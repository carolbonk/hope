"""H6 step 3: answering each grant's own questions (offline)."""

from __future__ import annotations

from datetime import date
from typing import Any

from hope_core.model_gateway import Message, MockProvider, ModelGateway
from hope_core.testing.factories import agency_profile
from hope_discovery.answers import (
    Answer,
    AnswerDraft,
    AnswerDrafter,
    GrantContext,
    build_answer_digest,
    build_checklist,
    classify_question,
    dossier_item,
    export_markdown,
    guard_figures,
    limit_label,
    measure,
    mock_answer,
    owner_for,
    same_need,
    standard_questions,
    strip_refs,
    unsupported_figures,
)
from hope_discovery.requirements import (
    Attachment,
    Limit,
    Question,
    Requirements,
    Sourced,
    Submission,
    question_key,
)

GRANT = GrantContext(title="Health Access Grant", funder="CCF", url="https://ccf.example.org/g")


def q(prompt: str, limit: Limit | None = None) -> Question:
    return Question(key=question_key(prompt), prompt=prompt, url=GRANT.url, limit=limit)


def drafter(responder: Any = mock_answer) -> AnswerDrafter:
    provider = MockProvider()
    provider.register(AnswerDraft, responder)
    return AnswerDrafter(ModelGateway([provider]))


def test_different_funder_wording_maps_to_the_same_topic() -> None:
    for prompt in (
        "Statement of Need",
        "What community problem will this grant address?",
        "Why is this work urgent right now?",
        "Describe the gap in services in your area.",
    ):
        assert classify_question(prompt)[0] == "need", prompt
    assert classify_question("How will you measure success?")[0] == "outcomes"
    assert classify_question("Describe your staff qualifications and track record")[0] == "capacity"
    assert classify_question("Tell us something")[0] == "organization"


def test_measure_counts_like_the_funder() -> None:
    assert measure("one two  three", Limit(unit="words", max=5)) == 3
    assert measure("a b", Limit(unit="characters", max=5, includes_spaces=True)) == 3
    assert measure("a b", Limit(unit="characters", max=5, includes_spaces=False)) == 2
    assert measure("word " * 501, Limit(unit="pages", max=1)) == 2


def test_figures_not_in_the_sources_become_to_confirm() -> None:
    text, bad = guard_figures(
        "We served 1,200 people, 85% finished, and we request $25,000 over 3 years in 2026.",
        "Served 1200 people a year. Organizations may request up to $25,000.",
    )
    assert bad == ["85%", "2026"]
    assert "[TO CONFIRM: 85%]" in text and "[TO CONFIRM: 2026]" in text
    assert "1,200" in text and "$25,000" in text and "3 years" in text


def test_draft_cites_profile_and_flags_missing_facts() -> None:
    profile = agency_profile()
    result = drafter().draft(profile, GRANT, Requirements(), q("Describe the community need."))
    assert profile.mission.mission_statement.split()[0] in result.text
    assert {c["kind"] for c in result.citations} <= {"profile", "unsourced"}
    assert any(c["kind"] == "profile" for c in result.citations)
    assert "local data on need" in result.to_confirm
    assert not result.over_limit


def test_over_limit_retries_once_shorter() -> None:
    calls: list[str] = []

    def wordy(messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
        calls.append(messages[-1].content)
        short = "Rewrite it shorter" in messages[-1].content
        return {"text": "We help." if short else "word " * 80, "claims": [], "to_confirm": []}

    result = drafter(wordy).draft(
        agency_profile(), GRANT, Requirements(), q("Describe it.", Limit(unit="words", max=50))
    )
    assert len(calls) == 2 and result.text == "We help." and not result.over_limit


def test_still_over_limit_is_saved_flagged_not_truncated() -> None:
    def wordy(messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
        return {"text": "word " * 80, "claims": [], "to_confirm": []}

    result = drafter(wordy).draft(
        agency_profile(), GRANT, Requirements(), q("Describe it.", Limit(unit="words", max=50))
    )
    assert result.over_limit and result.count == 80


def test_invented_refs_are_dropped() -> None:
    def liar(messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
        return {"text": "We help.", "claims": [{"sentence": "We help.", "refs": ["P999", "W7"]}]}

    result = drafter(liar).draft(agency_profile(), GRANT, Requirements(), q("Describe it."))
    assert result.citations == []


def test_answer_digest_has_name_and_budget() -> None:
    paths = {line.path for line in build_answer_digest(agency_profile()).lines}
    assert {"legal.legal_name", "financials.annual_operating_budget_amount"} <= paths


def test_checklist_and_inputs_needed() -> None:
    need = q("Describe the need.", Limit(unit="words", max=5))
    plan = q("Describe the plan.")
    req = Requirements(
        questions=[need, plan],
        attachments=[
            Attachment(name="IRS determination letter", quote="Upload your IRS letter.", url="u"),
            Attachment(name="Logic model", quote="Attach a logic model.", url="u"),
        ],
        submission=Submission(
            deadline=Sourced(text="Due March 1, 2026.", url="u"), deadline_date=date(2026, 3, 1)
        ),
    )
    answers = {
        need.key: Answer(question_key=need.key, text="one two three four five six", origin="ai"),
        plan.key: Answer(
            question_key=plan.key,
            text="We will [TO CONFIRM: staff budget].",
            origin="human",
            to_confirm=["staff budget"],
        ),
    }
    c = build_checklist(req, answers, date(2026, 11, 7))
    status = {i.label: i.status for i in c.items}
    assert status == {
        "Describe the need.": "over_limit",
        "Describe the plan.": "to_confirm",
        "IRS determination letter": "in_dossier",
        "Logic model": "upload_needed",
        "Deadline": "passed",
    }
    assert [(n.owner, n.text) for n in c.inputs_needed] == [
        ("finance", "staff budget"),
        ("program", "Upload: Logic model"),
    ]
    assert not c.complete


def test_standard_questions_only_when_funder_has_none() -> None:
    c = build_checklist(None, {}, date(2026, 11, 7))
    assert len(c.items) == len(standard_questions()) == 6
    assert all(i.status == "missing" and i.detail for i in c.items)


def test_dossier_and_owner_rules() -> None:
    assert dossier_item("Copy of 501(c)(3) letter") == "irs_501c3"
    assert dossier_item("Most recent audited financial statements") == "financials"
    assert dossier_item("Board of Directors roster") == "board_list"
    assert dossier_item("Logic model") is None
    assert owner_for("Board chair signature") == "director"
    assert owner_for("number of youth served") == "program"


def test_export_lists_every_question_and_attachment() -> None:
    need = q("Describe the need.", Limit(unit="words", max=250))
    req = Requirements(
        questions=[need], attachments=[Attachment(name="Budget", quote="Attach a budget.", url="u")]
    )
    md = export_markdown(
        "Grant",
        "CCF",
        "u",
        req,
        {need.key: Answer(question_key=need.key, text="We help.", origin="ai")},
    )
    assert "## 1. Describe the need." in md and "_Limit: 250 words_" in md
    assert "We help." in md and "- [ ] Budget" in md


def test_same_figure_in_another_format_is_supported() -> None:
    sources = "Annual operating budget USD 3,120,000. Serves 3,200 a year. 12% growth."
    assert unsupported_figures("A $3.12 million budget, 3.2k people, 12 percent.", sources) == []
    assert unsupported_figures("We serve 4,650 people.", sources) == ["4,650"]


def test_inline_refs_are_kept_out_of_the_pasted_text() -> None:
    assert strip_refs("We serve 3,200 children (P1, P18). We help [P2][P11].") == (
        "We serve 3,200 children. We help."
    )
    assert strip_refs("Phase 2 (pilot) starts soon.") == "Phase 2 (pilot) starts soon."


def test_limit_label_says_how_spaces_count() -> None:
    assert limit_label(Limit(unit="characters", max=1500, includes_spaces=True)) == (
        "1,500 characters, including spaces"
    )
    assert limit_label(Limit(unit="words", max=250)) == "250 words"


def test_covid_19_is_not_a_figure() -> None:
    assert unsupported_figures("Since COVID-19, visits rose.", "") == []


def test_sentences_without_a_source_are_reported() -> None:
    def mixed(messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "text": "Our clinic serves rural families today. We will run community workshops.",
            "claims": [{"sentence": "Our clinic serves rural families today.", "refs": ["P1"]}],
            "to_confirm": ["what is needed", "[TO CONFIRM: board size]"],
        }

    result = drafter(mixed).draft(agency_profile(), GRANT, Requirements(), q("Describe it."))
    assert result.unsourced == ["We will run community workshops."]
    assert result.to_confirm == ["board size"]
    assert result.citations[-1] == {
        "ref": None,
        "kind": "unsourced",
        "text": "We will run community workshops.",
    }


def test_elements_the_profile_lacks_become_to_confirm() -> None:
    from hope_discovery.answers import missing_elements

    digest = build_answer_digest(agency_profile())
    gaps = missing_elements("Walk us through the activities and the timeline.", digest)
    assert gaps == ["timeline and milestones"]
    assert missing_elements("Tell us about your organization.", digest) == []
    result = drafter().draft(
        agency_profile(), GRANT, Requirements(), q("Describe the project timeline.")
    )
    assert "timeline and milestones" in result.to_confirm


def test_same_staff_ask_is_listed_once() -> None:
    from hope_discovery.answers import same_need

    assert same_need(
        "specific funding sources after this grant", "funding sources after this grant"
    )
    assert not same_need("timeline and milestones", "funding sources after this grant")


def test_staff_facts_fill_gaps_instead_of_to_confirm() -> None:
    facts = {"timeline and milestones": "Launch in March 2027 and finish 3 cohorts by June."}
    result = drafter().draft(
        agency_profile(), GRANT, Requirements(), q("Describe the project timeline."), facts=facts
    )
    assert "timeline and milestones" not in result.to_confirm
    assert "local data on need" in result.to_confirm


def test_plan_specifics_not_in_the_profile_become_to_confirm() -> None:
    from hope_discovery.answers import guard_specifics

    text, bad = guard_specifics(
        "We host quarterly workshops in 8-week cohorts starting March 2027, with pre- and"
        " post-surveys. Clinics run weekly.",
        "Our clinic runs weekly walk-in hours.",
    )
    assert "quarterly" not in text.replace("'quarterly'", "")
    assert "[TO CONFIRM: how often (draft said 'quarterly')]" in text
    assert {"quarterly", "8-week", "March 2027"} <= set(bad)
    assert any("pre- and post-surveys" in b for b in bad)
    assert "Clinics run weekly." in text


def test_regression_no_quarterly_workshops_from_a_thin_profile() -> None:
    def padded(messages: list[Message], schema: dict[str, object]) -> dict[str, object]:
        return {
            "text": "We will host quarterly workshops and track results with satisfaction surveys.",
            "claims": [],
            "to_confirm": [],
        }

    result = drafter(padded).draft(agency_profile(), GRANT, Requirements(), q("Describe it."))
    assert "quarterly workshops" not in result.text
    assert "satisfaction surveys" not in result.text.replace("'satisfaction surveys'", "")
    assert "quarterly" in result.unsupported


def test_certification_and_ai_questions_go_to_staff() -> None:
    calls: list[int] = []

    def never(messages: list[Message], schema: dict[str, object]) -> dict[str, object]:
        calls.append(1)
        return {"text": "Yes.", "claims": [], "to_confirm": []}

    for prompt in (
        "Did you use AI tools to prepare this application?",
        "I certify that the information in this application is true.",
    ):
        result = drafter(never).draft(agency_profile(), GRANT, Requirements(), q(prompt))
        assert result.text.startswith("[TO CONFIRM: staff must answer")
    assert calls == []
    assert (
        not drafter()
        .draft(agency_profile(), GRANT, Requirements(), q("Aid to families?"))
        .text.startswith("[TO CONFIRM: staff")
    )


def test_near_duplicate_needs_are_listed_once() -> None:
    gap = "local data showing the need"
    for item in (
        "specific local statistics on underserved youth in Ohio",
        "local data on the need for STEM education among underserved youth in Ohio",
    ):
        assert same_need(item, gap)
    assert not same_need("partner organizations and their roles", "partner letters of support")
    assert not same_need("timeline and milestones", "local data showing the need")
    assert same_need(
        "provide a detailed timeline for the program activities", "timeline and milestones"
    )


def test_certification_label_alone_goes_to_staff() -> None:
    from hope_discovery.answers import staff_only

    assert staff_only("Certification")
    assert not staff_only("Aid to families")


def test_same_missing_fact_is_asked_once_across_questions() -> None:
    need, plan = q("Describe the need."), q("Describe the plan.")
    req = Requirements(questions=[need, plan])
    gap = "how often (draft said 'annually')"
    answers = {
        k: Answer(
            question_key=k, text=f"We meet [TO CONFIRM: {gap}].", origin="ai", to_confirm=[gap]
        )
        for k in (need.key, plan.key)
    }
    c = build_checklist(req, answers, date(2026, 11, 7))
    assert [n.text for n in c.inputs_needed] == [gap]
