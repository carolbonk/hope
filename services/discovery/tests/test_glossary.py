"""Funder jargon in plain language: found by code, explained from a vetted list or the funder."""

from __future__ import annotations

from datetime import date

from hope_core.schemas.agency_profile import SamRegistration
from hope_core.testing.factories import agency_profile
from hope_discovery.glossary import BY_KEY, explain, find_terms, glossary_term

NOFO = (
    "Applicants must have an active SAM.gov registration and a UEI. Submit the SF-424 and SF-424A"
    " through Grants.gov. Organizations without a NICRA may use the de minimis rate. Include"
    " letters of support from partners."
)


def test_finds_terms_with_the_funders_sentence() -> None:
    uses = {u.key: u for u in find_terms(NOFO, "https://agency.example.gov/nofo")}
    assert {"sam", "uei", "sf424", "sf424a", "nicra", "de_minimis", "letters_support"} <= set(uses)
    assert uses["sf424a"].quote.startswith("Submit the SF-424 and SF-424A")
    assert uses["sf424a"].url == "https://agency.example.gov/nofo"
    assert glossary_term("Unique Entity ID") is BY_KEY["uei"]
    assert glossary_term("Organizational Snapshot") is None
    assert find_terms("Our neighbors deserve care.", "u") == []


def test_explains_with_official_source_and_profile_status() -> None:
    profile = agency_profile()
    profile.legal.uei = None
    profile.legal.sam_registration = SamRegistration(status="active", expires_on=date(2027, 1, 1))
    uses = find_terms(NOFO, "https://agency.example.gov/nofo")
    terms = {t.key: t for t in explain(uses, profile, date(2027, 3, 1), date(2026, 11, 8))}
    sam = terms["sam"]
    assert sam.explained_by == "official" and sam.source_url and "sam.gov" in sam.source_url
    assert sam.status == "action_needed" and "renew" in (sam.detail or "")
    assert terms["uei"].status == "action_needed"
    assert terms["sf424a"].status == "info" and "budget" in terms["sf424a"].plain
    support = explain(uses, profile, date(2026, 11, 15), date(2026, 11, 8))
    assert support[0].status == "at_risk"
    assert next(t for t in support if t.key == "letters_support").status == "at_risk"


def test_quote_keeps_dotted_names_whole() -> None:
    text = "Applicants need an active SAM.gov registration and a Unique Entity ID (UEI). Next."
    uei = next(t for t in find_terms(text, "pasted") if t.key == "uei")
    assert (
        uei.quote == "Applicants need an active SAM.gov registration and a Unique Entity ID (UEI)."
    )
