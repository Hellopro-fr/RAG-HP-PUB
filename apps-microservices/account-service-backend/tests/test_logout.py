async def test_logout_redirects_to_post_logout(client, monkeypatch):
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", "Z" * 44)
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "k")
    r = await client.get(
        "/logout?post_logout_redirect_uri=https://svc.hellopro.eu/",
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "https://svc.hellopro.eu/" in r.text
