import json
from types import SimpleNamespace

import pytest
from factories import broken_redis, forecast, hourly_actual, utc

from app.cache import CACHE_TTL_SECONDS, cache_key, get_redis
from app.config import get_settings
from app.ingestion import sync_january_data
from app.main import app
from app.period import DEFAULT_DECISION_CUTOFF


@pytest.fixture
def seeded(db_session):
    db_session.add_all(
        [
            forecast(utc(2026, 1, 2, 10), utc(2026, 1, 1, 7, 30), 110),
            forecast(utc(2026, 1, 2, 10), utc(2026, 1, 1, 9, 30), 130),
            *hourly_actual(utc(2026, 1, 2, 10), 100),
            forecast(utc(2026, 1, 3, 10), utc(2026, 1, 2, 7, 30), 200),
        ]
    )
    db_session.commit()


def test_dashboard_returns_metrics(client, seeded):
    body = client.get("/api/v1/dashboard").json()

    assert body["decision_cutoff_local"] == "09:00"
    assert body["summary"]["mae_mw"] == 10
    assert body["summary"]["paired_intervals"] == 1
    assert len(body["points"]) == 2
    assert len(body["daily"]) == 31


def test_cache_miss_populates_and_hit_is_served(client, seeded, memory_redis, db_session):
    key = cache_key(DEFAULT_DECISION_CUTOFF)
    assert key not in memory_redis.values

    first = client.get("/api/v1/dashboard").json()
    assert key in memory_redis.values
    assert memory_redis.ttls[key] == CACHE_TTL_SECONDS

    # Change the DB behind the cache's back: a hit must not touch Postgres.
    db_session.add(forecast(utc(2026, 1, 4, 10), utc(2026, 1, 3, 7, 30), 999))
    db_session.commit()
    assert client.get("/api/v1/dashboard").json() == first


def test_each_cutoff_has_its_own_cache_entry(client, seeded, memory_redis):
    early = client.get("/api/v1/dashboard?cutoff=09:00").json()
    late = client.get("/api/v1/dashboard?cutoff=11:00").json()

    assert early["points"][0]["forecast_mw"] == 110
    assert late["points"][0]["forecast_mw"] == 130
    assert {cache_key(DEFAULT_DECISION_CUTOFF), "wind-dashboard:v2:cutoff=1100"} <= set(
        memory_redis.values
    )


def test_sync_invalidates_cached_dashboard(client, seeded, memory_redis, session_factory):
    from test_ingestion import FakeElexon

    client.get("/api/v1/dashboard")
    sync_january_data(session_factory, FakeElexon, lambda: memory_redis)

    assert memory_redis.values == {}
    body = client.get("/api/v1/dashboard").json()
    assert any(p["start_time"] == "2026-01-02T00:00:00Z" for p in body["points"])


def test_dashboard_still_works_when_redis_is_down(client, seeded):
    app.dependency_overrides[get_redis] = broken_redis

    response = client.get("/api/v1/dashboard")

    assert response.status_code == 200
    assert response.json()["summary"]["mae_mw"] == 10


def test_filter_by_decision_date(client, seeded):
    body = client.get("/api/v1/dashboard?decision_date=2026-01-02").json()

    assert [p["decision_date"] for p in body["points"]] == ["2026-01-02"]
    assert body["summary"]["paired_intervals"] == 0
    assert [row["decision_date"] for row in body["daily"]] == ["2026-01-02"]


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("decision_date=2026-02-01", "January 2026"),
        ("decision_date=2025-12-31", "January 2026"),
        ("cutoff=09:00:30", "HH:MM"),
    ],
)
def test_dashboard_rejects_out_of_range_parameters(client, query, message):
    response = client.get(f"/api/v1/dashboard?{query}")

    assert response.status_code == 422
    assert message in response.json()["detail"]


@pytest.mark.parametrize("query", ["decision_date=not-a-date", "cutoff=25:00"])
def test_dashboard_rejects_malformed_parameters(client, query):
    assert client.get(f"/api/v1/dashboard?{query}").status_code == 422


def test_health_endpoints(client, memory_redis):
    assert client.get("/api/v1/health/live").json() == {"status": "ok", "dependencies": {}}
    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.json()["dependencies"] == {"postgres": "ok", "redis": "ok"}


def test_readiness_reports_degraded_redis(client):
    app.dependency_overrides[get_redis] = broken_redis

    ready = client.get("/api/v1/health/ready")

    assert ready.status_code == 200
    assert ready.json()["dependencies"]["redis"] == "degraded"


def test_readiness_fails_without_postgres(client):
    from app.database import get_db

    class DeadSession:
        def execute(self, *_):
            from sqlalchemy.exc import OperationalError

            raise OperationalError("SELECT 1", {}, Exception("down"))

    app.dependency_overrides[get_db] = lambda: DeadSession()

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"]["dependencies"]["postgres"] == "unavailable"


@pytest.fixture
def ingestion_enabled(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ingestion_token", "s3cret")
    monkeypatch.setattr(settings, "redis_url", "redis://example:6379/0")
    queued = []
    monkeypatch.setattr(
        "app.tasks.refresh_january_data.delay",
        lambda: queued.append(1) or SimpleNamespace(id="task-123"),
    )
    return queued


def test_manual_ingestion_disabled_without_configuration(client):
    assert client.post("/api/v1/ingestion/sync").status_code == 503


@pytest.mark.parametrize("header", [None, "Bearer wrong", "s3cret", "Basic s3cret"])
def test_manual_ingestion_rejects_bad_tokens(client, ingestion_enabled, header):
    headers = {"Authorization": header} if header else {}

    response = client.post("/api/v1/ingestion/sync", headers=headers)

    assert response.status_code == 401
    assert ingestion_enabled == []


def test_manual_ingestion_queues_task(client, ingestion_enabled):
    response = client.post("/api/v1/ingestion/sync", headers={"Authorization": "Bearer s3cret"})

    assert response.status_code == 202
    assert response.json() == {"task_id": "task-123", "status": "queued"}
    assert ingestion_enabled == [1]


def test_openapi_documents_dashboard(client):
    schema = client.get("/openapi.json").json()

    assert "/api/v1/dashboard" in schema["paths"]
    assert json.dumps(schema)  # serialisable
