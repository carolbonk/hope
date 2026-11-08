from __future__ import annotations

from uuid import uuid4

import pytest
from hope_core.auth import SessionSecretError, make_session_token, read_session_token
from hope_core.settings import HopeSettings


@pytest.mark.parametrize("secret", [None, "", "too-short"])
def test_sessions_need_a_configured_secret(secret: str | None) -> None:
    settings = HopeSettings(session_secret=secret)
    with pytest.raises(SessionSecretError):
        make_session_token(uuid4(), settings)


def test_tokens_round_trip_only_with_the_same_secret() -> None:
    user = uuid4()
    token = make_session_token(user, HopeSettings(session_secret="a" * 32))
    assert read_session_token(token, HopeSettings(session_secret="a" * 32)) == user
    assert read_session_token(token, HopeSettings(session_secret="b" * 32)) is None
