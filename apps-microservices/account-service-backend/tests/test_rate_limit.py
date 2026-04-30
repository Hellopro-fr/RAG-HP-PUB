async def test_rate_limit_authorize(client, monkeypatch):
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", "Z" * 44)
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "k")
    from app.core.settings import get_settings
    get_settings.cache_clear()
    payload = {
        "username": "u@x", "password": "p", "client_id": "nope",
        "redirect_uri": "https://x", "state": "s",
        "code_challenge": "c", "code_challenge_method": "S256",
    }
    statuses = []
    for _ in range(12):
        r = await client.post("/authorize", json=payload)
        statuses.append(r.status_code)
    assert 429 in statuses
