import pytest

from app.services.code_service import (
    CodeAlreadyConsumed,
    CodeExpired,
    CodeInvalid,
    consume_code,
    issue_code,
)


async def test_issue_code_returns_raw_and_persists_hash():
    raw = await issue_code(
        client_id="svc",
        sub="u@x",
        code_challenge="ch",
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb",
        ttl_seconds=60,
        email="u@x",
        display_name="U",
    )
    assert isinstance(raw, str) and len(raw) > 16


async def test_consume_code_happy_path():
    raw = await issue_code(
        client_id="svc", sub="u@x", code_challenge="ch",
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb", ttl_seconds=60,
        email="u@x", display_name="U",
    )
    record = await consume_code(raw, expected_redirect_uri="https://svc.hellopro.eu/cb")
    assert record.sub == "u@x"


async def test_consume_code_unknown_raises():
    with pytest.raises(CodeInvalid):
        await consume_code("nope", expected_redirect_uri="x")


async def test_consume_code_replay_raises():
    raw = await issue_code(
        client_id="svc", sub="u@x", code_challenge="ch",
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb", ttl_seconds=60,
    )
    await consume_code(raw, expected_redirect_uri="https://svc.hellopro.eu/cb")
    with pytest.raises(CodeAlreadyConsumed):
        await consume_code(raw, expected_redirect_uri="https://svc.hellopro.eu/cb")


async def test_consume_code_expired_raises():
    raw = await issue_code(
        client_id="svc", sub="u@x", code_challenge="ch",
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb", ttl_seconds=-5,
    )
    with pytest.raises(CodeExpired):
        await consume_code(raw, expected_redirect_uri="https://svc.hellopro.eu/cb")


async def test_consume_code_redirect_mismatch_raises():
    raw = await issue_code(
        client_id="svc", sub="u@x", code_challenge="ch",
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb", ttl_seconds=60,
    )
    with pytest.raises(CodeInvalid):
        await consume_code(raw, expected_redirect_uri="https://other.hellopro.eu/cb")
