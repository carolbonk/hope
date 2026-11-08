"""Offline NTEE suggestion responder for `MockProvider` (the keyword rules of the web fixture)."""

from __future__ import annotations

import re
from typing import Any

from hope_core.model_gateway import Message

RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("E32", ("clinic", "dental", "preventive care"), "Runs community clinics that deliver care."),
    ("F30", ("mental health",), "Provides mental health support."),
    ("O50", ("youth", "mentor"), "Runs programs for young people."),
    ("K31", ("food bank", "pantry", "meals"), "Distributes food to families."),
    ("L41", ("homeless", "shelter"), "Shelters people experiencing homelessness."),
)

_UNTRUSTED = re.compile(r"<untrusted[^>]*>\n?(.*?)\n?</untrusted>", re.DOTALL)


def ntee_responder(messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
    user = next((m.content for m in messages if m.role == "user"), "")
    blocks = _UNTRUSTED.findall(user)
    suggestions = []
    for code, words, reason in RULES:
        hit = _first_hit(blocks, words)
        if hit is not None:
            suggestions.append({"code": code, "reason": reason, "quote": hit})
    return {"suggestions": suggestions}


def _first_hit(blocks: list[str], words: tuple[str, ...]) -> str | None:
    for block in blocks:
        lower = block.lower()
        for word in words:
            at = lower.find(word)
            if at >= 0:
                return block[at : at + len(word)]
    return None
