import httpx
import pytest
from factories import forecast, utc
from fastapi.testclient import TestClient

from app import main
from app.config import get_settings
from app.startup import initialise_database


def _initialise(engine, session_factory, sync, migrate=lambda: None):
    initialise_database(bind=engine, session_factory=session_factory, migrate=migrate, sync=sync)


def test_empty_database_is_migrated_then_seeded(engine, session_factory):
    calls = []

    def sync(session_factory):
        calls.append("sync")
        return {"forecasts": 1, "actuals": 1}

    _initialise(engine, session_factory, sync, migrate=lambda: calls.append("migrate"))
    assert calls == ["migrate", "sync"]


def test_existing_data_is_never_reimported(engine, session_factory, db_session):
    db_session.add(forecast(utc(2026, 1, 2), utc(2026, 1, 1, 9), 500))
    db_session.commit()

    def sync(session_factory):
        raise AssertionError("must not re-import over existing data")

    _initialise(engine, session_factory, sync)


def test_elexon_failure_does_not_stop_startup(engine, session_factory, caplog):
    def sync(session_factory):
        raise httpx.ConnectError("Elexon unreachable")

    _initialise(engine, session_factory, sync)
    assert "Elexon import failed" in caplog.text


def test_migration_failure_aborts_startup(engine, session_factory):
    def migrate():
        raise RuntimeError("database unreachable")

    with pytest.raises(RuntimeError, match="database unreachable"):
        _initialise(engine, session_factory, sync=lambda **_: {}, migrate=migrate)


def test_lifespan_initialises_database_before_serving(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "initialise_database", lambda: calls.append("init"))
    monkeypatch.setattr(get_settings(), "init_db_on_startup", True)
    with TestClient(main.app) as client:
        assert calls == ["init"]
        assert client.get("/api/v1/health/live").status_code == 200
