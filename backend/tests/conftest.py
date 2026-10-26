import os

# Tests build their own schema; never migrate or call Elexon from the app lifespan.
os.environ["INIT_DB_ON_STARTUP"] = "false"

from collections.abc import Generator

import pytest
from factories import MemoryRedis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.cache import get_redis
from app.database import Base, get_db
from app.main import app

# Set TEST_DATABASE_URL (e.g. in CI) to run the suite against real Postgres.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def engine():
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL)
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def db_session(session_factory) -> Generator[Session, None, None]:
    with session_factory() as session:
        yield session


@pytest.fixture
def memory_redis() -> MemoryRedis:
    return MemoryRedis()


@pytest.fixture
def client(session_factory, memory_redis) -> Generator[TestClient, None, None]:
    def override_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis] = lambda: memory_redis
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
