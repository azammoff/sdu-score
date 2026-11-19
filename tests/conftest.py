"""Tests run against a real PostgreSQL database.

Set TEST_DATABASE_URL to an empty database you don't mind wiping, for example
postgresql+psycopg://sdu:sdu@localhost:5432/sdu_score_test
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.repositories.sql import SqlStore
from app.seed import seed

ADMIN = {"X-API-Key": "sdu-admin-key"}
TEST_DATABASE_URL = settings.test_database_url  # from the environment or .env


@pytest.fixture(scope="session", autouse=True)
def _require_test_database():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set (see .env.example)")


@pytest.fixture(scope="session")
def engine(_require_test_database):
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        seed(SqlStore(session))
    return factory


@pytest.fixture
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
