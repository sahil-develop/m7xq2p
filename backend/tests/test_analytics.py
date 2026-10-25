from datetime import datetime, timezone

from app.analytics import build_dashboard
from app.models import WindActual, WindForecast

UTC = timezone.utc


def test_latest_forecast_before_decision_cutoff_is_compared_to_matching_actual(db_session):
    start = datetime(2026, 1, 2, 10, tzinfo=UTC)
    db_session.add_all(
        [
            WindForecast(
                start_time=start,
                publish_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
                generation_mw=100,
            ),
            WindForecast(
                start_time=start,
                publish_time=datetime(2026, 1, 1, 10, 30, tzinfo=UTC),
                generation_mw=120,
            ),
            WindForecast(
                start_time=start,
                publish_time=datetime(2026, 1, 1, 11, 30, tzinfo=UTC),
                generation_mw=150,
            ),
            WindActual(start_time=start, generation_mw=110),
        ]
    )
    db_session.commit()

    result = build_dashboard(db_session)

    point = next(point for point in result.points if point.start_time == start)
    assert point.forecast_mw == 120
    assert point.actual_mw == 110
    assert point.error_mw == 10
    assert result.summary.paired_intervals == 1
    assert result.summary.mae_mw == 10
    assert result.daily[0].delivery_date.isoformat() == "2026-01-02"


def test_unmatched_forecast_is_visible_but_excluded_from_accuracy(db_session):
    start = datetime(2026, 1, 2, 10, tzinfo=UTC)
    db_session.add(
        WindForecast(
            start_time=start,
            publish_time=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            generation_mw=120,
        )
    )
    db_session.commit()

    result = build_dashboard(db_session)

    assert len(result.points) == 1
    assert result.points[0].actual_mw is None
    assert result.summary.paired_intervals == 0
    assert result.summary.mae_mw is None
