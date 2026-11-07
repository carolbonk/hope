"""Heuristic prompt-injection detector (blueprint 8.3). A hit sets
`parse_quality.injection_suspected` and sends the document to human review."""

from __future__ import annotations

import re

PATTERNS: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern, re.I)
    for name, pattern in {
        "ignore_instructions": r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}"
        r"\b(previous|prior|above|earlier|all|any|system)\b[^.\n]{0,20}"
        r"\b(instructions?|prompts?|rules|directions)\b",
        "role_override": r"\byou are (now|no longer)\b|\bact as (an?|the)\b|\bnew instructions?\b",
        "prompt_exfiltration": r"\b(reveal|print|repeat|show)\b[^.\n]{0,30}\b(system prompt|"
        r"instructions|api key|secret)\b",
        "role_tags": r"<\s*/?\s*(system|assistant|untrusted|instructions?)\b[^>]*>",
        "verdict_steering": r"\b(mark|rate|score|classify|treat)\b[^.\n]{0,60}"
        r"\b(eligible|approved|highest|top|pursue)\b",
    }.items()
}
ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")
BIDI = re.compile("[\u202a-\u202e\u2066-\u2069]")


def strip_invisible(text: str) -> str:
    return BIDI.sub("", ZERO_WIDTH.sub("", text))


def injection_signals(text: str, hidden_text: list[str] | None = None) -> list[str]:
    signals: list[str] = []
    if ZERO_WIDTH.search(text):
        signals.append("zero_width_chars")
    if BIDI.search(text):
        signals.append("bidi_override")
    if any(rx.search(strip_invisible(h)) for h in hidden_text or [] for rx in PATTERNS.values()):
        signals.append("hidden_text")
    scanned = strip_invisible(" ".join([text, *(hidden_text or [])]))
    signals.extend(f"pattern:{name}" for name, rx in PATTERNS.items() if rx.search(scanned))
    return signals
