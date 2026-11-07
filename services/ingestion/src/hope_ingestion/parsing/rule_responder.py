"""Deterministic stand-in for the extraction model, registered on MockProvider so A2 runs
offline (tests, local dev with HOPE_MODEL_PROVIDER=mock). It quotes lines by keyword and,
like a well-behaved model, treats the untrusted section purely as data."""

from __future__ import annotations

import re
from typing import Any

from hope_core.model_gateway import Message, MockProvider

from hope_ingestion.parsing.extraction import SectionExtraction

UNTRUSTED = re.compile(r"<untrusted[^>]*>\n(?P<body>.*)\n</untrusted>", re.S)
RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("deadlines", "loi_due", re.compile(r"letter of intent|\bLOI\b", re.I)),
    ("deadlines", "questions_due", re.compile(r"questions?\b.*\b(due|deadline|by)\b", re.I)),
    (
        "deadlines",
        "application_due",
        re.compile(r"application.*\b(due|deadline)\b|closing date", re.I),
    ),
    ("amounts", "award_ceiling", re.compile(r"award ceiling|maximum award|up to \$", re.I)),
    ("amounts", "award_floor", re.compile(r"award floor|minimum award", re.I)),
    (
        "amounts",
        "total_program_funding",
        re.compile(r"total (program )?funding|estimated total", re.I),
    ),
]
LISTS: dict[str, re.Pattern[str]] = {
    "indirect_cost": re.compile(r"indirect", re.I),
    "cost_share": re.compile(r"cost[- ]?shar|\bmatch(ing)? (funds|requirement)", re.I),
    "eligibility": re.compile(r"eligib", re.I),
    "priorities": re.compile(r"priorit", re.I),
}
SINGLES: dict[str, re.Pattern[str]] = {
    "title": re.compile(r"^(title|opportunity title|program)\s*:", re.I),
    "funder_name": re.compile(r"^(funder|agency|issued by|funding agency)\s*:", re.I),
    "summary": re.compile(r"^(summary|purpose|overview)\s*:", re.I),
    "expected_awards": re.compile(r"(expected|anticipated) (number of )?awards", re.I),
}
PAGE_LIMIT = re.compile(r"(\d+)[- ]page", re.I)


def respond(messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
    match = UNTRUSTED.search(messages[-1].content)
    lines = [ln.strip() for ln in (match.group("body") if match else "").splitlines() if ln.strip()]
    out: dict[str, Any] = {"deadlines": [], "amounts": [], **{k: [] for k in LISTS}}
    out["requirement_sections"] = []
    for line in (ln for ln in lines if not ln.isupper()):
        quote = {"quote": line[:500], "confidence": 0.9}
        rule = next(((group, kind) for group, kind, rx in RULES if rx.search(line)), None)
        if rule is not None:
            out[rule[0]].append(quote | {"kind": rule[1]})
            continue
        for name, rx in SINGLES.items():
            if name not in out and rx.search(line):
                out[name] = quote
        for name, rx in LISTS.items():
            if rx.search(line):
                out[name].append(quote)
        if PAGE_LIMIT.search(line):
            out["requirement_sections"].append(quote | {"title": line.split(":")[0][:200]})
    return out


def register(provider: MockProvider) -> MockProvider:
    provider.register(SectionExtraction, respond)
    return provider
