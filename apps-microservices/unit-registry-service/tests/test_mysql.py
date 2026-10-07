"""Runs only against a real MySQL 8 (Review Focus 1). See Task 6 Step 6 for the command."""
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from infrastructure.db.bootstrap import bootstrap
from infrastructure.db.models import Base
from infrastructure.db.repository import UnitRepository
from unit_registry.types import Unit

from .conftest import NOW

MYSQL_URL = os.environ.get("MYSQL_TEST_URL")
pytestmark = pytest.mark.skipif(not MYSQL_URL, reason="MYSQL_TEST_URL not set")


@pytest.fixture
def mysql_factory():
    engine = create_engine(MYSQL_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as s:
        bootstrap(s, NOW)
    yield factory
    Base.metadata.drop_all(engine)


def test_mysql_collation_keeps_tokens_distinct(mysql_factory):
    with mysql_factory() as s:
        repo = UnitRepository(s)
        assert repo.get_unit_by_token("Litres").token == "Litres"
        assert repo.get_unit_by_token("litres").token == "litres"
        assert repo.get_unit_by_token("décibels").token == "décibels"
        assert repo.get_unit_by_token("decibels").token == "decibels"


def test_mysql_rejects_an_exact_duplicate_token(mysql_factory):
    with pytest.raises(IntegrityError):
        with mysql_factory.begin() as s:
            UnitRepository(s).insert_unit(Unit(id="dup", token="kg", dimension="mass",
                                               created_at=NOW, updated_at=NOW))
