import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.db.database import close_db, init_db
from main import app


@pytest_asyncio.fixture(autouse=True)
async def _db():
    await init_db("sqlite://:memory:")
    yield
    await close_db()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
