"""H6 step 2: reading a grant's application requirements (offline)."""

from __future__ import annotations

from datetime import date
from typing import Any

from hope_core.model_gateway import Message, MockProvider, ModelGateway
from hope_core.web import FetchError, Link, Page
from hope_discovery.requirements import (
    Limit,
    RequirementsExtraction,
    RequirementsReader,
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
            "eligibility": None,
        }
    )
    assert [q.prompt for q in ext.questions] == ["How will you measure success?"]
    assert [a.name for a in ext.attachments] == ["Audit"]
    assert ext.deadline is None and ext.eligibility == []
