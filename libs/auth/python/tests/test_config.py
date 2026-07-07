import pytest
import hellopro_auth.config as config
from hellopro_auth.config import parse_admin_emails, get_auth_config

BASE = {
    "SERVICE_NAME": "redis-client-frontend",
    "ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND": "cid",
    "ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND": "sec",
    "ACCOUNT_PUBLIC_URL": "http://localhost:8601/",
    "ACCOUNT_BASE_URL": "http://account-service-backend:8600/",
    "ACCOUNT_REDIRECT_URI": "http://localhost:3551/auth/callback",
    "JWT_SECRET": "jwt",
}


@pytest.fixture(autouse=True)
def _clear_creds_cache():
    config._reset_cache()
    yield
    config._reset_cache()


def test_parse_admin_emails():
    s = parse_admin_emails(" Alice@HP.fr , bob@hp.fr ,, ")
    assert s == {"alice@hp.fr", "bob@hp.fr"}
    assert parse_admin_emails(None) == set()


def _apply(monkeypatch, extra=None):
    env = dict(BASE)
    if extra:
        env.update(extra)
    for k in ("SESSION_TTL", "SECURE_COOKIE", "SSO_CENTRAL_LOGOUT", "ADMIN_EMAILS",
              "ACCOUNT_CLIENT_ID", "ACCOUNT_CLIENT_SECRET", "ACCOUNT_INTERNAL_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


async def test_get_auth_config_defaults(monkeypatch):
    _apply(monkeypatch)
    cfg = await get_auth_config()
    assert cfg.account_public_url == "http://localhost:8601"
    assert cfg.account_base_url == "http://account-service-backend:8600"
    assert cfg.client_id == "cid" and cfg.client_secret == "sec"
    assert cfg.session_ttl_seconds == 28800
    assert cfg.secure_cookie is False
    assert cfg.central_logout is False


async def test_bad_session_ttl(monkeypatch):
    _apply(monkeypatch, {"SESSION_TTL": "abc"})
    with pytest.raises(RuntimeError, match="SESSION_TTL"):
        await get_auth_config()


async def test_custom_session_ttl(monkeypatch):
    _apply(monkeypatch, {"SESSION_TTL": "3600"})
    assert (await get_auth_config()).session_ttl_seconds == 3600


async def test_missing_required_var(monkeypatch):
    _apply(monkeypatch)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        await get_auth_config()


async def test_bool_trues(monkeypatch):
    _apply(monkeypatch, {"SECURE_COOKIE": "true", "SSO_CENTRAL_LOGOUT": "true", "ADMIN_EMAILS": "a@hp.fr"})
    cfg = await get_auth_config()
    assert cfg.secure_cookie is True
    assert cfg.central_logout is True
    assert cfg.admin_emails == frozenset({"a@hp.fr"})


async def test_fetch_fallback(monkeypatch):
    for k in ("ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND", "ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND",
              "ACCOUNT_CLIENT_ID", "ACCOUNT_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SERVICE_NAME", "redis-client-frontend")
    monkeypatch.setenv("ACCOUNT_INTERNAL_TOKEN", "adm")
    monkeypatch.setenv("ACCOUNT_PUBLIC_URL", "http://localhost:8601")
    monkeypatch.setenv("ACCOUNT_BASE_URL", "http://acct:8600")
    monkeypatch.setenv("ACCOUNT_REDIRECT_URI", "http://localhost:3551/auth/callback")
    monkeypatch.setenv("JWT_SECRET", "jwt")
    calls = {"n": 0}

    async def fake_api():
        calls["n"] += 1
        return ("fid", "fsec")

    monkeypatch.setattr(config, "get_account_credentials_from_api", fake_api)
    cfg = await config.get_auth_config()
    assert (cfg.client_id, cfg.client_secret) == ("fid", "fsec")
    await config.get_auth_config()          # memoized
    assert calls["n"] == 1


async def test_fetch_fallback_guard_fails_reraises(monkeypatch):
    for k in ("ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND", "ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND",
              "ACCOUNT_CLIENT_ID", "ACCOUNT_CLIENT_SECRET", "ACCOUNT_INTERNAL_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SERVICE_NAME", "redis-client-frontend")

    async def boom():
        raise AssertionError("must not be called when guard fails")

    monkeypatch.setattr(config, "get_account_credentials_from_api", boom)
    with pytest.raises(config.AccountCredentialsMissing):
        await config._resolve_credentials()


async def test_fetch_raises_not_cached(monkeypatch):
    for k in ("ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND", "ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND",
              "ACCOUNT_CLIENT_ID", "ACCOUNT_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SERVICE_NAME", "redis-client-frontend")
    monkeypatch.setenv("ACCOUNT_INTERNAL_TOKEN", "adm")

    async def flaky():
        raise config.AccountCredentialsMissing("account-service down")

    monkeypatch.setattr(config, "get_account_credentials_from_api", flaky)
    with pytest.raises(config.AccountCredentialsMissing):
        await config._resolve_credentials()
    assert "redis-client-frontend" not in config._fetched_creds
