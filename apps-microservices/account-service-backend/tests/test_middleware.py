async def test_request_id_added_to_response(client):
    r = await client.get("/health")
    assert r.headers.get("x-request-id")


async def test_provided_request_id_echoed(client):
    r = await client.get("/health", headers={"X-Request-Id": "rid-123"})
    assert r.headers["x-request-id"] == "rid-123"
