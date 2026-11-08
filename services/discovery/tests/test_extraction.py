from __future__ import annotations

from typing import Any

from hope_core.model_gateway import Message
from hope_core.web import Link
from hope_discovery import mock
from hope_discovery.extract import FUNDER_NOT_CONFIRMED, scrub_summary, verify_extraction
from hope_discovery.mock import CHW_GUIDELINES, INJECT, ORAL, UNQUOTED, ScriptedWeb
from hope_discovery.models import FitAssessment, PageExtraction, Quote

PAGE = (
    "Rural Oral Health Access Grant 2027.\nFunder: Cascade Health Foundation.\n"
    "Awards: up to $75,000."
)


def test_extraction_retry_then_skip(run_agent: Any) -> None:
    calls: list[int] = []

    def broken(_messages: Any, _schema: Any) -> dict[str, Any]:
        calls.append(1)
        raise ValueError("bad json")

    web = ScriptedWeb(hits=[ORAL])
    repo, result = run_agent(web=web, overrides={PageExtraction: broken})
    assert isinstance(result, dict)
    assert len(calls) == 2
    assert repo.candidates == {}
    assert result["counts"]["failed_pages"] == 1
    assert any(e["text"] == "Couldn't read cascadehealth.example.org" for e in repo.events)


def test_unverified_quotes_dropped_and_fallbacks() -> None:
    ext = PageExtraction(
        kind="open_opportunity",
        is_grant_opportunity=True,
        confidence=0.9,
        title=Quote(text="Totally Different Grant"),
        funder=Quote(text="Someone Else Foundation"),
        amount=Quote(text="up to   $75,000"),
        deadline=Quote(text="Applications due June 1, 2027"),
        eligibility=[
            Quote(text="Funder: Cascade Health Foundation"),
            Quote(text="made up", page=2),
        ],
    )
    v = verify_extraction(ext, [PAGE], ORAL, "Rural Oral Health | Cascade", [])
    assert v.keep
    assert v.title == "Rural Oral Health | Cascade"
    assert v.funder == "example.org" or v.funder.endswith("example.org")
    assert FUNDER_NOT_CONFIRMED in v.concerns
    assert v.amount is not None and v.amount.text == "up to   $75,000"
    assert v.deadline is None
    assert [q.text for q in v.eligibility] == ["Funder: Cascade Health Foundation"]
    low = ext.model_copy(update={"confidence": 0.5})
    assert not verify_extraction(low, [PAGE], ORAL, "t", []).keep
    news = ext.model_copy(update={"kind": "news_or_blog"})
    assert not verify_extraction(news, [PAGE], ORAL, "t", []).keep


def test_summary_scrubbed() -> None:
    summary = "Funds rural dental clinics. Awards up to $50,000. Applications due March 3, 2027."
    assert scrub_summary(summary) == "Funds rural dental clinics."
    assert scrub_summary(None) == ""


def test_details_page_same_domain_once(run_agent: Any) -> None:
    ext = PageExtraction(
        kind="open_opportunity",
        is_grant_opportunity=True,
        confidence=0.9,
        needs_more_detail=True,
        detail_link_index=1,
    )
    other = [Link(url="https://elsewhere.org/guidelines", text="Guidelines")]
    same = [Link(url=f"{ORAL}/guidelines/?utm_source=x", text="Guidelines")]
    itself = [Link(url=ORAL + "#faq", text="FAQ")]
    assert verify_extraction(ext, [PAGE], ORAL, "t", other).detail_url is None
    assert verify_extraction(ext, [PAGE], ORAL, "t", itself).detail_url is None
    assert verify_extraction(ext, [PAGE], ORAL, "t", same).detail_url == f"{ORAL}/guidelines"

    web = ScriptedWeb()
    repo, _ = run_agent(web=web)
    assert web.fetched.count(CHW_GUIDELINES) == 1
    chw = next(c for c in repo.candidates.values() if c.title.startswith("Community Health"))
    assert chw.deadline_text == "Full proposals due April 15, 2027"
    assert any(c.url == CHW_GUIDELINES for c in chw.citations)

    web = ScriptedWeb()
    repo, _ = run_agent(web=web, max_detail_fetches=0)
    assert CHW_GUIDELINES not in web.fetched
    chw = next(c for c in repo.candidates.values() if c.title.startswith("Community Health"))
    assert chw.deadline is None


def test_injection_page_untrusted_and_no_effect(run_agent: Any) -> None:
    seen: dict[str, list[str]] = {"extract": [], "fit": []}

    def spy(kind: str, responder: Any) -> Any:
        def wrapped(messages: list[Message], schema: Any) -> dict[str, Any]:
            seen[kind].append(messages[-1].content)
            result: dict[str, Any] = responder(messages, schema)
            return result

        return wrapped

    overrides = {
        PageExtraction: spy("extract", mock.extract_responder),
        FitAssessment: spy("fit", mock.fit_responder),
    }
    clean, _ = run_agent(web=ScriptedWeb(hits=[ORAL]), overrides=overrides)
    injected, _ = run_agent(web=ScriptedWeb(hits=[INJECT]), overrides=overrides)
    a, b = next(iter(clean.candidates.values())), next(iter(injected.candidates.values()))
    assert a.fit_score == b.fit_score
    assert a.fit_reasons == b.fit_reasons and a.concerns == b.concerns
    prompt = seen["extract"][-1]
    start, end = prompt.index('<untrusted kind="web_page" n="1">'), prompt.index("</untrusted>")
    assert start < prompt.index("Ignore all previous instructions") < end
    assert not any("Ignore all previous" in p for p in seen["fit"])
    assert not any(u in p for p in seen["fit"] for u in UNQUOTED)
