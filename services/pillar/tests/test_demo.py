from __future__ import annotations

from pathlib import Path

from hope_pillar.demo import ensure_env, ensure_invite_code, run_service_seeds


def test_invite_code_is_written_once(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("HOPE_INVITE_CODE=\nOTHER=1")
    code = ensure_invite_code(env)
    assert code and len(code) >= 16
    assert env.read_text() == f"OTHER=1\nHOPE_INVITE_CODE={code}\n"
    assert ensure_invite_code(env) is None


def test_session_secret_is_kept_once_written(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    assert ensure_env("HOPE_SESSION_SECRET", "first-secret-0123456789", env)
    assert ensure_env("HOPE_SESSION_SECRET", "second-secret-012345678", env) is None
    assert env.read_text() == "HOPE_SESSION_SECRET=first-secret-0123456789\n"


def test_service_seeds_skip_missing_modules() -> None:
    assert "hope_discovery.demo" in run_service_seeds()
