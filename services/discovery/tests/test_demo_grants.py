from __future__ import annotations

from datetime import UTC, date, datetime

from hope_discovery.demo_grants import GRANTS, candidate


def test_recorded_deadline_survives_once_passed() -> None:
    spec = next(g for g in GRANTS if "Mentoring" in g["title"])
    later = candidate(spec, date(2026, 12, 1), datetime(2026, 11, 30, tzinfo=UTC))
    assert later.deadline == date(2026, 11, 16)
