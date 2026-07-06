import pytest
from hellopro_auth.session import create_session_token, read_session, SESSION_COOKIE, SessionClaims


def test_cookie_name():
    assert SESSION_COOKIE == "rcf_session"


def test_round_trip(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s")
    tok = create_session_token(SessionClaims(email="alice@hp.fr", name="Alice"), 3600)
    got = read_session(tok)
    assert got == SessionClaims(email="alice@hp.fr", name="Alice")


def test_expired(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s")
    assert read_session(create_session_token(SessionClaims(email="a@hp.fr"), -1)) is None


def test_garbage(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s")
    assert read_session("nope") is None
    assert read_session(None) is None


def test_missing_secret(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        read_session("any.jwt")
