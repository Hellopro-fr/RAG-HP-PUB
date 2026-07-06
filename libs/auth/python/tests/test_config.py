import pytest
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


def test_parse_admin_emails():
    s = parse_admin_emails(" Alice@HP.fr , bob@hp.fr ,, ")
    assert s == {"alice@hp.fr", "bob@hp.fr"}
    assert parse_admin_emails(None) == set()


def _apply(monkeypatch, extra=None):
    env = dict(BASE)
    if extra:
        env.update(extra)
    for k in ("SESSION_TTL", "SECURE_COOKIE", "SSO_CENTRAL_LOGOUT", "ADMIN_EMAILS", "ACCOUNT_CLIENT_ID", "ACCOUNT_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_get_auth_config_defaults(monkeypatch):
    _apply(monkeypatch)
    cfg = get_auth_config()
    assert cfg.account_public_url == "http://localhost:8601"
    assert cfg.account_base_url == "http://account-service-backend:8600"
    assert cfg.client_id == "cid" and cfg.client_secret == "sec"
    assert cfg.session_ttl_seconds == 28800
    assert cfg.secure_cookie is False
    assert cfg.central_logout is False


def test_bad_session_ttl(monkeypatch):
    _apply(monkeypatch, {"SESSION_TTL": "abc"})
    with pytest.raises(RuntimeError, match="SESSION_TTL"):
        get_auth_config()


def test_custom_session_ttl(monkeypatch):
    _apply(monkeypatch, {"SESSION_TTL": "3600"})
    assert get_auth_config().session_ttl_seconds == 3600


def test_missing_required_var(monkeypatch):
    _apply(monkeypatch)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        get_auth_config()


def test_bool_trues(monkeypatch):
    _apply(monkeypatch, {"SECURE_COOKIE": "true", "SSO_CENTRAL_LOGOUT": "true", "ADMIN_EMAILS": "a@hp.fr"})
    cfg = get_auth_config()
    assert cfg.secure_cookie is True
    assert cfg.central_logout is True
    assert cfg.admin_emails == frozenset({"a@hp.fr"})
