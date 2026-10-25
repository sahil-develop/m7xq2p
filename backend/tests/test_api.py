from datetime import datetime, timezone

from app.models import WindActual, WindForecast

UTC = timezone.utc


def test_dashboard_returns_metrics_and_caches_response(client, db_session):
    start = datetime(2026, 1, 2, 10, tzinfo=UTC)
    db_session.add_all(
        [
            WindForecast(
                start_time=start,
                publish_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
                generation_mw=110,
            ),
            WindActual(start_time=start, generation_mw=100),
        ]
    )
    db_session.commit()

    first = client.get("/api/v1/dashboard")
    second = client.get("/api/v1/dashboard")

    assert first.status_code == 200
    assert first.json()["summary"]["mae_mw"] == 10
    assert first.json() == second.json()


def test_dashboard_filters_valid_decision_date(client, db_session):
    first = datetime(2026, 1, 2, 10, tzinfo=UTC)
    second = datetime(2026, 1, 3, 10, tzinfo=UTC)
    db_session.add_all(
        [
            WindForecast(
                start_time=first,
                publish_time=datetime(2026, 1, 1, 10, tzinfo=UTC),
                generation_mw=100,
            ),
            WindForecast(
                start_time=second,
                publish_time=datetime(2026, 1, 2, 10, tzinfo=UTC),
                generation_mw=200,
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/dashboard?decision_date=2026-01-01")

    assert response.status_code == 200
    assert len(response.json()["points"]) == 1
    assert response.json()["points"][0]["decision_date"] == "2026-01-01"


def test_dashboard_rejects_decision_date_outside_assignment_window(client):
    response = client.get("/api/v1/dashboard?decision_date=2026-02-01")

    assert response.status_code == 422
    assert "January 2026" in response.json()["detail"]


def test_health_and_manual_ingestion_configuration(client):
    assert client.get("/api/v1/health/live").json()["status"] == "ok"
    response = client.post("/api/v1/ingestion/sync")
    assert response.status_code == 503
