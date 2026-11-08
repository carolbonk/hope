"""`hope-create-user`: accounts created from the command line, with the password never echoed."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from hope_pillar import admin

EMAIL = "ana@riverbend.example.org"
PASSWORD = "correct-horse-battery"


def run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *argv: str,
    stdin: str = PASSWORD + "\n",
) -> tuple[str, str]:
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    admin.main(list(argv))
    out, err = capsys.readouterr()
    assert PASSWORD not in out + err and stdin.strip() not in out + err
    return out, err


def fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *argv: str,
    stdin: str = PASSWORD + "\n",
) -> str:
    with pytest.raises(SystemExit) as exit_:
        run(monkeypatch, capsys, *argv, stdin=stdin)
    assert exit_.value.code not in (0, None)
    _, err = capsys.readouterr()
    message = str(exit_.value.code) + err
    assert stdin.strip() not in message
    return message


def login(api: TestClient, email: str, password: str) -> int:
    return api.post("/v1/auth/login", json={"email": email, "password": password}).status_code


def test_creates_an_account_that_can_sign_in(
    hope_api: TestClient, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out, err = run(
        monkeypatch,
        capsys,
        "--email",
        " Ana@Riverbend.Example.org ",
        "--name",
        "Ana",
        "--password-stdin",
    )
    email, user_id = out.split()
    assert email == EMAIL and len(user_id) == 36 and err == ""
    assert login(hope_api, EMAIL, PASSWORD) == 200
    me = hope_api.get("/v1/me").json()
    assert (me["user_id"], me["email"]) == (user_id, EMAIL)


def test_prompts_for_the_password_twice(
    hope_api: TestClient, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter([PASSWORD, "something-else-entirely"])
    monkeypatch.setattr(admin, "getpass", lambda prompt: next(answers))
    assert "don't match" in fails(monkeypatch, capsys, "--email", EMAIL, "--name", "Ana")
    assert login(hope_api, EMAIL, PASSWORD) == 401

    monkeypatch.setattr(admin, "getpass", lambda prompt: PASSWORD)
    out, _ = run(monkeypatch, capsys, "--email", EMAIL, "--name", "Ana")
    assert out.startswith(EMAIL + " ")
    assert login(hope_api, EMAIL, PASSWORD) == 200


def test_an_existing_email_fails_and_reset_changes_the_password(
    hope_api: TestClient, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    created, _ = run(monkeypatch, capsys, "--email", EMAIL, "--name", "Ana", "--password-stdin")
    taken = fails(
        monkeypatch,
        capsys,
        "--email",
        EMAIL.upper(),
        "--name",
        "Ana",
        "--password-stdin",
        stdin="another-password-123\n",
    )
    assert "already has an account" in taken and "--reset-password" in taken
    assert login(hope_api, EMAIL, PASSWORD) == 200

    reset, _ = run(
        monkeypatch,
        capsys,
        "--email",
        EMAIL,
        "--reset-password",
        "--password-stdin",
        stdin="another-password-123\n",
    )
    assert reset == created
    assert login(hope_api, EMAIL, PASSWORD) == 401
    assert login(hope_api, EMAIL, "another-password-123") == 200


def test_reset_needs_an_existing_account(
    hope_api: TestClient, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    message = fails(monkeypatch, capsys, "--email", EMAIL, "--reset-password", "--password-stdin")
    assert "no account" in message
    assert login(hope_api, EMAIL, PASSWORD) == 401


@pytest.mark.parametrize(
    ("argv", "stdin", "expected"),
    [
        (["--email", "not-an-email", "--name", "Ana"], PASSWORD, "not an email address"),
        (["--email", EMAIL], PASSWORD, "--name is required"),
        (["--email", EMAIL, "--name", "Ana"], "1234567", "at least 8 characters"),
    ],
)
def test_rejects_bad_input_without_creating_anything(
    hope_api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    stdin: str,
    expected: str,
) -> None:
    assert expected in fails(monkeypatch, capsys, *argv, "--password-stdin", stdin=stdin + "\n")
    assert login(hope_api, EMAIL, stdin) == 401


def test_the_password_is_never_an_argument(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for flag in ("--password", "--password-std"):
        with pytest.raises(SystemExit) as exit_:
            admin.main(["--email", EMAIL, "--name", "Ana", flag, PASSWORD])
        assert exit_.value.code == 2
        out, err = capsys.readouterr()
        assert PASSWORD not in out + err and "never an argument" in err
