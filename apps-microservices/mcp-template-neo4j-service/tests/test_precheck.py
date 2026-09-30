import asyncio

import pytest
from neo4j.exceptions import AuthError, ClientError, ConfigurationError, ServiceUnavailable

import app.precheck as precheck
from app.neo4j_env import Neo4jCredentials
from app.precheck import PrecheckError, verify_connection

CANARY = "canary-7f3a91"  # synthetic value; must never appear in messages
CREDS = Neo4jCredentials(uri="bolt://neo4j:7687", username="u", password=CANARY, database="graph")


class FakeResult:
    async def consume(self):
        return None


class FakeSession:
    def __init__(self, driver):
        self._driver = driver

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query):
        self._driver.queries.append(query)
        if self._driver.hang:
            await asyncio.sleep(10)
        if self._driver.exc is not None:
            raise self._driver.exc
        return FakeResult()


class FakeDriver:
    def __init__(self, exc=None, hang=False):
        self.exc = exc
        self.hang = hang
        self.closed = False
        self.database = None
        self.queries = []

    def session(self, database=None):
        self.database = database
        return FakeSession(self)

    async def close(self):
        self.closed = True


def _install(monkeypatch, driver=None, ctor_exc=None):
    calls = {}

    def fake_driver(uri, auth=None, **kwargs):
        calls["uri"], calls["auth"], calls["kwargs"] = uri, auth, kwargs
        if ctor_exc is not None:
            raise ctor_exc
        return driver

    monkeypatch.setattr(precheck.AsyncGraphDatabase, "driver", fake_driver)
    return calls


@pytest.mark.asyncio
async def test_success_pings_the_configured_database(monkeypatch):
    drv = FakeDriver()
    calls = _install(monkeypatch, drv)
    await verify_connection(CREDS, timeout=1.0)
    assert calls["uri"] == "bolt://neo4j:7687"
    assert calls["auth"] == ("u", CANARY)
    assert drv.database == "graph"
    assert drv.queries == ["RETURN 1"]
    assert drv.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc,code",
    [
        (AuthError("bad credentials"), "neo4j_auth_failed"),
        (ServiceUnavailable("down"), "neo4j_unreachable"),
        (OSError("connection refused"), "neo4j_unreachable"),
    ],
)
async def test_errors_are_classified(monkeypatch, exc, code):
    drv = FakeDriver(exc=exc)
    _install(monkeypatch, drv)
    with pytest.raises(PrecheckError) as info:
        await verify_connection(CREDS, timeout=1.0)
    assert info.value.code == code
    assert CANARY not in info.value.message
    assert drv.closed


@pytest.mark.asyncio
async def test_database_not_found(monkeypatch):
    exc = ClientError("missing db")
    exc._neo4j_code = "Neo.ClientError.Database.DatabaseNotFound"
    _install(monkeypatch, FakeDriver(exc=exc))
    with pytest.raises(PrecheckError) as info:
        await verify_connection(CREDS, timeout=1.0)
    assert info.value.code == "neo4j_database_not_found"
    assert "graph" in info.value.message


@pytest.mark.asyncio
async def test_other_client_error(monkeypatch):
    exc = ClientError("forbidden")
    exc._neo4j_code = "Neo.ClientError.Security.Forbidden"
    _install(monkeypatch, FakeDriver(exc=exc))
    with pytest.raises(PrecheckError) as info:
        await verify_connection(CREDS, timeout=1.0)
    assert info.value.code == "neo4j_error"


@pytest.mark.asyncio
async def test_timeout_is_unreachable(monkeypatch):
    drv = FakeDriver(hang=True)
    _install(monkeypatch, drv)
    with pytest.raises(PrecheckError) as info:
        await verify_connection(CREDS, timeout=0.05)
    assert info.value.code == "neo4j_unreachable"
    assert drv.closed


@pytest.mark.asyncio
async def test_invalid_uri(monkeypatch):
    _install(monkeypatch, ctor_exc=ConfigurationError("URI scheme 'http' is not supported"))
    with pytest.raises(PrecheckError) as info:
        await verify_connection(CREDS, timeout=1.0)
    assert info.value.code == "neo4j_invalid_uri"
    assert CANARY not in info.value.message
