async def _env(monkeypatch):
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", "Z" * 44)
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "admin")
    from app.core.settings import get_settings
    get_settings.cache_clear()


async def test_admin_create_client_returns_secret_once(client, monkeypatch):
    await _env(monkeypatch)
    r = await client.post(
        "/admin/clients",
        headers={"X-Admin-Key": "admin"},
        json={
            "client_id": "svc", "name": "S",
            "redirect_uris": ["https://svc.hellopro.eu/cb"],
            "post_logout_redirect_uris": ["https://svc.hellopro.eu/"],
            "skip_consent": True,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["client_id"] == "svc"
    assert body["client_secret"]


async def test_admin_create_requires_admin_key(client, monkeypatch):
    await _env(monkeypatch)
    r = await client.post("/admin/clients", json={
        "client_id": "svc", "name": "S",
        "redirect_uris": ["https://svc.hellopro.eu/cb"],
    })
    assert r.status_code == 403


async def test_admin_list_and_delete(client, monkeypatch):
    await _env(monkeypatch)
    await client.post("/admin/clients", headers={"X-Admin-Key": "admin"}, json={
        "client_id": "svc", "name": "S",
        "redirect_uris": ["https://svc.hellopro.eu/cb"],
    })
    r = await client.get("/admin/clients", headers={"X-Admin-Key": "admin"})
    assert r.status_code == 200
    assert any(c["client_id"] == "svc" for c in r.json())
    r2 = await client.delete("/admin/clients/svc", headers={"X-Admin-Key": "admin"})
    assert r2.status_code == 204
