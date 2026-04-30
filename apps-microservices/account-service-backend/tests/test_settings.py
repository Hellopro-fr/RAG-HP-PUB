import os

import pytest

from app.core.settings import Settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("MYSQL_HOST", "db")
    monkeypatch.setenv("MYSQL_USER", "u")
    monkeypatch.setenv("MYSQL_PASS", "p")
    monkeypatch.setenv("MYSQL_DB", "account_db")
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", "Z" * 44)
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "admin")
    s = Settings()
    assert s.MYSQL_DB == "account_db"
    assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 15
    assert s.REFRESH_TOKEN_EXPIRE_DAYS == 30
    assert str(s.HELLOPRO_AUTH_URL).startswith("https://auth.hellopro.fr")


def test_settings_missing_required_raises(monkeypatch):
    for k in ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASS", "MYSQL_DB",
             "HELLOPRO_AUTH_URL", "JWT_KEY_ENCRYPTION_KEY", "GATEWAY_ADMIN_KEY"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(Exception):
        Settings()
