from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from infrastructure.db.bootstrap import bootstrap
from infrastructure.db.models import Base

NOW = datetime(2026, 10, 6, 12, 0, 0)


@pytest.fixture
def engine():
    eng = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def seeded(session_factory):
    with session_factory.begin() as session:
        bootstrap(session, NOW)
    return session_factory
