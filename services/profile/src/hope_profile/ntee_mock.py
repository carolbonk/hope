"""Offline NTEE suggestion responder for `MockProvider` (same keyword rules as the web fixture)."""

from __future__ import annotations

import re
from typing import Any

from hope_core.model_gateway import Message

RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "E32",
        ("clinic", "dental", "preventive care"),
        "Runs community clinics that deliver preventive and dental care.",
    ),
    ("F30", ("mental health",), "Provides mental health support."),
    ("O50", ("youth", "mentor"), "Runs programs for young people."),
    ("K31", ("food bank", "pantry", "meals"), "Distributes food to families."),
    ("L41", ("homeless", "shelter"), "Shelters people experiencing homelessness."),
)

_UNTRUSTED = re.compile(r"<untrusted[^>]*>\n(.*?)\n</untrusted>", re.DOTALL)


def untrusted_blocks(messages: list[Message]) -> list[str]:
    user = next((m.content for m in reversed(messages) if m.role == "user"), "")
    return _UNTRUSTED.findall(user)


def ntee_responder(messages: list[Message], schema: dict[str, Any]) -> dict[str, Any]:
    blocks = untrusted_blocks(messages)
    suggestions = []
    for code, words, reason in RULES:
        for block in blocks:
            lower = block.lower()
            word = next((w for w in words if w in lower), None)
            if word is None:
                continue
            at = lower.index(word)
            suggestions.append(
                {"code": code, "reason": reason, "quote": block[at : at + len(word)]}
            )
            break
    return {"suggestions": suggestions}
