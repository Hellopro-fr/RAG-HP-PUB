import os
import pytest

from common_utils.sso.credentials import (
    AccountCredentialsMissing,
    derive_env_keys,
    get_account_credentials,
)


def test_derive_env_keys_normalizes() -> None:
    cid, sec = derive_env_keys("api-gateway")
    assert cid == "ACCOUNT_CLIENT_ID_API_GATEWAY"
    assert sec == "ACCOUNT_CLIENT_SECRET_API_GATEWAY"


def test_get_credentials_via_prefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_NAME", "api-gateway")
    monkeypatch.setenv("ACCOUNT_CLIENT_ID_API_GATEWAY", "id-1")
    monkeypatch.setenv("ACCOUNT_CLIENT_SECRET_API_GATEWAY", "sec-1")
    cid, sec = get_account_credentials()
    assert cid == "id-1"
    assert sec == "sec-1"


def test_get_credentials_falls_back_to_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_NAME", "lonely-service")
    monkeypatch.delenv("ACCOUNT_CLIENT_ID_LONELY_SERVICE", raising=False)
    monkeypatch.delenv("ACCOUNT_CLIENT_SECRET_LONELY_SERVICE", raising=False)
    monkeypatch.setenv("ACCOUNT_CLIENT_ID", "fallback-id")
    monkeypatch.setenv("ACCOUNT_CLIENT_SECRET", "fallback-sec")
    cid, sec = get_account_credentials()
    assert cid == "fallback-id"
    assert sec == "fallback-sec"


def test_get_credentials_explicit_arg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACCOUNT_CLIENT_ID_OTHER_THING", "id-2")
    monkeypatch.setenv("ACCOUNT_CLIENT_SECRET_OTHER_THING", "sec-2")
    cid, sec = get_account_credentials("other-thing")
    assert cid == "id-2"
    assert sec == "sec-2"


def test_get_credentials_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_NAME", raising=False)
    monkeypatch.delenv("ACCOUNT_CLIENT_ID", raising=False)
    monkeypatch.delenv("ACCOUNT_CLIENT_SECRET", raising=False)
    with pytest.raises(AccountCredentialsMissing):
        get_account_credentials()
