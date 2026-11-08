"""H6 step 2: reading a grant's application requirements (offline)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from hope_core.model_gateway import Message, MockProvider, ModelGateway
from hope_core.web import FetchError, Link, Page
from hope_discovery.requirements import (
    Limit,
    Requirements,
    RequirementsExtraction,
    RequirementsReader,
    is_question,
    mock_responder,
    parse_limit,
    pick_links,
    question_key,
)

GRANT = "https://ccf.example.org/grants/health-access"
GUIDE = "https://ccf.example.org/grants/health-access/guidelines"
PDF = "https://ccf.example.org/files/application-instructions.pdf"

PAGES = {
    GRANT: Page(
        url=GRANT,
        final_url=GRANT,
        title="Health Access Grant",
        text="The Health Access Grant supports rural clinics. Applications are due March 1, 2027."
        " Organizations may request up to $25,000.",
        links=[
            Link(url=GUIDE, text="Application guidelines"),
            Link(url=PDF, text="Instructions (PDF)"),
            Link(url="https://ccf.example.org/about", text="About us"),
            Link(url="https://otherfunder.org/apply", text="Apply elsewhere"),
        ],
    ),
    GUIDE: Page(
        url=GUIDE,
        final_url=GUIDE,
        title="Guidelines",
        text="Describe the community need your program addresses? (500 words)"
        " How will you measure success? (2,500 characters including spaces)"
        " Upload your IRS determination letter. Attach a board of directors list.",
    ),
}


class FakeWeb:
    def __init__(self) -> None:
        self.fetched: list[str] = []

    def search(self, query: str, max_results: int = 8) -> list[Any]:
        return []

    def fetch(self, url: str) -> Page:
        self.fetched.append(url)
        if url not in PAGES:
            raise FetchError("http_403", url)
        return PAGES[url]


def reader(responder: Any = mock_responder) -> tuple[RequirementsReader, FakeWeb]:
    provider = MockProvider()
    provider.register(RequirementsExtraction, responder)
    web = FakeWeb()
    return RequirementsReader(ModelGateway([provider]), web, today=lambda: date(2026, 11, 7)), web


def test_parse_limit() -> None:
    assert parse_limit("500 words") == Limit(unit="words", max=500)
    assert parse_limit("Maximum 2,500 characters including spaces") == Limit(
        unit="characters", max=2500, includes_spaces=True
    )
    assert parse_limit("no more than two pages") == Limit(unit="pages", max=2)
    assert parse_limit("250-500 words") == Limit(unit="words", max=500)
    assert parse_limit("1,000 characters without spaces") == Limit(
        unit="characters", max=1000, includes_spaces=False
    )
    assert parse_limit("Be concise.") is None and parse_limit(None) is None


def test_question_key_ignores_case_and_punctuation() -> None:
    assert question_key("How will you measure success?") == question_key(
        "how will you  measure success"
    )


def test_pick_links_keeps_same_site_guidance_pdf_first() -> None:
    assert pick_links(PAGES[GRANT], GRANT, {GRANT}) == [PDF, GUIDE]


def test_reads_questions_limits_attachments_and_budget() -> None:
    r, web = reader()
    req = r.read(GRANT)
    assert web.fetched == [GRANT, PDF, GUIDE]
    assert [(p.url, p.status) for p in req.pages] == [
        (GRANT, "read"),
        (PDF, "failed"),
        (GUIDE, "read"),
    ]
    need, success = req.questions
    assert need.limit == Limit(unit="words", max=500) and need.url == GUIDE
    assert success.limit == Limit(unit="characters", max=2500, includes_spaces=True)
    assert [a.name for a in req.attachments] == [
        "IRS determination letter",
        "board of directors list",
    ]
    assert req.submission.deadline_date == date(2027, 3, 1)
    assert req.budget.max_request_amount is not None
    assert req.budget.max_request_amount.amount_minor == 2_500_000


def test_quotes_not_on_the_page_are_dropped() -> None:
    def invented(messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "is_application_info": True,
            "questions": [{"prompt": {"text": "What is your theory of change?"}}],
            "attachments": [{"name": "Audit", "quote": {"text": "Attach your latest audit."}}],
            "deadline": {"text": "Due April 30, 2027."},
        }

    r, _ = reader(invented)
    req = r.read(GRANT)
    assert req.questions == [] and req.attachments == [] and req.submission.deadline is None
    assert {p.status for p in req.pages if p.status != "failed"} == {"no_info"}


def test_model_failure_marks_the_page_failed() -> None:
    def broken(messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
        return {"is_application_info": "maybe"}

    r, _ = reader(broken)
    req = r.read(GRANT)
    assert all(p.status == "failed" for p in req.pages)


def test_plain_string_quotes_and_bad_items_are_tolerated() -> None:
    ext = RequirementsExtraction.model_validate(
        {
            "is_application_info": True,
            "questions": [{"prompt": "How will you measure success?"}, {"prompt": ""}],
            "attachments": [
                {"name": "Board list", "quote": ""},
                {"name": "Audit", "quote": {"text": "Attach your latest audit."}},
            ],
            "deadline": "",
            "submission_method": [],
            "max_request": ["Request up to $25,000."],
            "eligibility": None,
        }
    )
    assert ext.submission_method is None and ext.max_request == "Request up to $25,000."
    assert [q.prompt for q in ext.questions] == ["How will you measure success?"]
    assert [a.name for a in ext.attachments] == ["Audit"]
    assert ext.deadline is None and ext.eligibility == []


def test_notes_to_the_reader_are_not_questions() -> None:
    from hope_discovery.requirements import asks_for_document, is_question

    assert is_question("Describe the community need your program addresses.")
    assert is_question("1. What outcomes will you track")
    assert is_question("Who does the program serve?")
    assert is_question(
        "Organization Snapshot*  In 100 words or fewer, introduce your organization."
    )
    assert is_question("Project Design* Walk us through the activities and the timeline.")
    assert not is_question("Need help? Email grants@rhef.example.org.")
    assert not is_question("Please carefully read the eligibility criteria before applying.")
    assert not is_question("Please contact the Foundation before proceeding with an application.")
    assert not is_question("Organizations are limited to one grant proposal per cycle.")
    assert asks_for_document("Upload your IRS determination letter.")
    assert not asks_for_document("A nonprofit must have current tax-exempt status under 501(c)(3).")


def test_budget_format_must_talk_about_the_budget() -> None:
    def noisy(messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "is_application_info": True,
            "budget_format": "The Health Access Grant supports rural clinics.",
        }

    r, _ = reader(noisy)
    assert r.read(GRANT).budget.format is None


@pytest.mark.parametrize(
    ("text", "unit", "most", "spaces"),
    [  # verbatim from real nonprofit forms (Foundant, NEA, Metro, VSUW, Tower, ...)
        ("Character Limit: 3000", "characters", 3000, None),
        ("Character Limit: 1000 | File Size Limit: 2 MB", "characters", 1000, None),
        ("(200-word limit)", "words", 200, None),
        ("word limit: 250", "words", 250, None),
        ("500-character limit, including spaces", "characters", 500, True),
        ("limit 2,500 including spaces", "characters", 2500, True),
        ("This section allows for population - limited to 3000-character spaces.",
         "characters", 3000, True),
        ("Responses include 2,000 character limits (spaces included).", "characters", 2000, True),
        ("not to exceed five pages, min. 11-point font", "pages", 5, None),
    ],
)  # fmt: skip
def test_real_form_limits(text: str, unit: str, most: int, spaces: bool | None) -> None:
    assert parse_limit(text) == Limit(unit=unit, max=most, includes_spaces=spaces)  # type: ignore[arg-type]


@pytest.mark.parametrize("text", ["File Size Limit: 5 MB", "500", "$100,000 MAX"])
def test_not_text_limits(text: str) -> None:
    assert parse_limit(text) is None


@pytest.mark.parametrize(
    "prompt",
    [  # field labels real forms use instead of questions
        "Project description:",
        "Organizational Capability",
        "Planned project evaluation:",
        "A detailed description of the project and why it's needed.",
        "(280 characters) Discuss how the money will be spent.",
        "If serving additional geographies beyond the target geographies selected above, please"
        " describe, including specific states/counties.",
        "Purpose and description of project (include rationale, target population;"
        " word limit: 400)",
    ],
)
def test_field_labels_are_questions(prompt: str) -> None:
    assert is_question(prompt)


@pytest.mark.parametrize(
    "prompt",
    ["Enter N/A. This field will be used if you are awarded a grant.", "Eligibility", "Deadlines:"],
)
def test_portal_placeholders_are_not_questions(prompt: str) -> None:
    assert not is_question(prompt)


def test_funder_terms_are_verified_and_labelled() -> None:
    from hope_discovery.requirements import RequirementsExtraction, RequirementsReader

    page = (
        "Thrive Grants support Neighborhood Anchors. A Neighborhood Anchor is a group rooted in one"
        " zip code for at least five years. Applicants must have a UEI."
    )
    ext = RequirementsExtraction.model_validate(
        {
            "is_application_info": True,
            "terms": [
                {
                    "term": "Neighborhood Anchor",
                    "quote": "Thrive Grants support Neighborhood Anchors.",
                    "funder_definition": "A Neighborhood Anchor is a group rooted in one zip code"
                    " for at least five years.",
                },
                {"term": "Thrive", "quote": "Thrive Grants support", "meaning": "The program."},
                {"term": "Ghost", "quote": "Not on the page.", "meaning": "Invented."},
            ],
        }
    )
    out = Requirements()
    reader = RequirementsReader(ModelGateway([MockProvider()]), None)  # type: ignore[arg-type]
    reader._merge(out, ext, page, "https://f.example.org")
    by = {t.term: t for t in out.terms}
    assert by["UEI"].key == "uei" and by["UEI"].source == "glossary"
    assert by["Neighborhood Anchor"].source == "funder"
    assert by["Thrive"].source == "ai" and "Ghost" not in by


def test_label_only_quotes_take_the_rest_of_the_question() -> None:
    from hope_discovery.requirements import asks_for_document, full_prompt

    form = (
        "Narrative questions:\n"
        "1. Statement of Need (500 words): Describe the health access gap in your service area.\n"
        "Project Description*\n"
        "What is the challenge or opportunity you are trying to address?\n"
    )
    need = full_prompt("Statement of Need", form)
    assert need.startswith("Statement of Need (500 words): Describe the health access gap")
    assert parse_limit(need) == Limit(unit="words", max=500)
    assert full_prompt("Project Description", form).endswith("trying to address?")
    assert full_prompt("Why now?", form) == "Why now?"
    assert is_question(need)
    assert asks_for_document("Attachments: Logic model; budget justification.")
