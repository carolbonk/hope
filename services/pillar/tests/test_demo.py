from __future__ import annotations

from pathlib import Path

from hope_pillar.demo import ensure_invite_code, run_service_seeds


def test_invite_code_is_written_once(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("HOPE_INVITE_CODE=\nOTHER=1")
    code = ensure_invite_code(env)
    assert code and len(code) >= 16
    assert env.read_text() == f"OTHER=1\nHOPE_INVITE_CODE={code}\n"
    assert ensure_invite_code(env) is None


def test_service_seeds_skip_missing_modules() -> None:
    assert "hope_discovery.demo" in run_service_seeds()
