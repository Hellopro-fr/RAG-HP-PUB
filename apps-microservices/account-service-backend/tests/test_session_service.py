import pytest

from app.services.session_service import (
    SessionExpired,
    SessionInvalid,
    consume_login_session,
    issue_login_session,
)


async def test_issue_and_consume_happy_path():
    raw = await issue_login_session(
        client_id="svc",
        sub="u@x",
        email="u@x",
        display_name="U",
        next_path="/dashboard",
    )
    assert isinstance(raw, str) and len(raw) > 16
    sess = await consume_login_session(raw, expected_client_id="svc")
    assert sess.sub == "u@x"
    assert sess.next_path == "/dashboard"


async def test_consume_unknown_raises():
    with pytest.raises(SessionInvalid):
        await consume_login_session("nope", expected_client_id="svc")


async def test_consume_replay_raises():
    raw = await issue_login_session(
        client_id="svc", sub="u@x", email=None, display_name=None
    )
    await consume_login_session(raw, expected_client_id="svc")
    with pytest.raises(SessionInvalid):
        await consume_login_session(raw, expected_client_id="svc")


async def test_consume_service_mismatch_raises():
    raw = await issue_login_session(
        client_id="svc", sub="u@x", email=None, display_name=None
    )
    with pytest.raises(SessionInvalid):
        await consume_login_session(raw, expected_client_id="other")


async def test_consume_expired_raises():
    raw = await issue_login_session(
        client_id="svc",
        sub="u@x",
        email=None,
        display_name=None,
        ttl_seconds=-5,
    )
    with pytest.raises(SessionExpired):
        await consume_login_session(raw, expected_client_id="svc")
