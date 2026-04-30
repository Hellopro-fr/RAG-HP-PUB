import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.database import close_db, init_db
from main import app


@pytest_asyncio.fixture(autouse=True)
async def _db():
    await init_db("sqlite://:memory:")
    yield
    await close_db()


@pytest_asyncio.fixture
async def client():
    """Async test client running the FastAPI app via ASGITransport in the
    current asyncio event loop. Tests must ``await client.get(...)`` etc.

    Plan deviation: the plan uses sync ``TestClient``; switched to
    ``httpx.AsyncClient`` because TestClient spawns a separate portal/loop
    that breaks Tortoise's loop-bound DB connection."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
