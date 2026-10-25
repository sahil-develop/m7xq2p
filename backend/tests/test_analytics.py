from datetime import date, time

import pytest
from factories import forecast, hourly_actual, utc

from app.analytics import build_dashboard, compute_metrics, filter_by_decision_date
from app.models import WindActual
from app.schemas import IntervalPoint

NINE = time(9, 0)


def test_uses_latest_forecast_published_before_cutoff(db_session):
    target = utc(2026, 1, 2, 10)
    db_session.add_all(
        [
            forecast(target, utc(2026, 1, 1, 4, 30), 100),
            forecast(target, utc(2026, 1, 1, 7, 30), 120),  # latest before 09:00
            forecast(target, utc(2026, 1, 1, 9, 30), 150),  # after cutoff: not available
            *hourly_actual(target, 100, 120),
        ]
    )
    db_session.commit()

    result = build_dashboard(db_session, NINE)

    [point] = result.points
    assert point.forecast_mw == 120
    assert point.publish_time == utc(2026, 1, 1, 7, 30)
    assert point.horizon_hours == pytest.approx(26.5)
    assert point.actual_mw == 110  # mean of the two half-hours
    assert point.error_mw == 10
    assert result.summary.mae_mw == 10
    assert result.daily[0].delivery_date == date(2026, 1, 2)
    assert result.daily[0].forecast_energy_mwh == 120


def test_later_cutoff_selects_newer_forecast(db_session):
    target = utc(2026, 1, 2, 10)
    db_session.add_all(
        [
            forecast(target, utc(2026, 1, 1, 7, 30), 120),
            forecast(target, utc(2026, 1, 1, 9, 30), 150),
        ]
    )
    db_session.commit()

    assert build_dashboard(db_session, time(11, 0)).points[0].forecast_mw == 150
    assert build_dashboard(db_session, time(9, 30)).points[0].forecast_mw == 150  # inclusive
    assert build_dashboard(db_session, time(9, 29)).points[0].forecast_mw == 120


def test_early_cutoff_falls_back_to_previous_day_forecast(db_session):
    target = utc(2026, 1, 3, 1)
    db_session.add(forecast(target, utc(2026, 1, 1, 22, 30), 300))
    db_session.commit()

    [point] = build_dashboard(db_session, time(1, 0)).points
    assert point.decision_date == date(2026, 1, 2)
    assert point.forecast_mw == 300


def test_targets_outside_delivery_window_are_ignored(db_session):
    db_session.add_all(
        [
            forecast(utc(2026, 1, 1, 23), utc(2025, 12, 31, 7, 30), 1),  # decision on Dec 31
            forecast(utc(2026, 2, 2, 0), utc(2026, 1, 31, 7, 30), 1),  # decision on Feb 1
            forecast(utc(2026, 2, 1, 23), utc(2026, 1, 31, 7, 30), 2),  # last valid hour
        ]
    )
    db_session.commit()

    result = build_dashboard(db_session, NINE)

    assert [p.start_time for p in result.points] == [utc(2026, 2, 1, 23)]
    assert len(result.daily) == 31


def test_hour_missing_a_half_hour_actual_is_not_paired(db_session):
    target = utc(2026, 1, 2, 10)
    db_session.add_all(
        [
            forecast(target, utc(2026, 1, 1, 7, 30), 120),
            WindActual(start_time=target, generation_mw=100),
        ]
    )
    db_session.commit()

    [point] = build_dashboard(db_session, NINE).points
    assert point.actual_mw is None
    assert point.error_mw is None


def test_unmatched_forecast_is_visible_but_excluded_from_accuracy(db_session):
    db_session.add(forecast(utc(2026, 1, 2, 10), utc(2026, 1, 1, 7, 30), 120))
    db_session.commit()

    result = build_dashboard(db_session, NINE)

    assert len(result.points) == 1
    assert result.summary.paired_intervals == 0
    assert result.summary.mae_mw is None


def _point(error: float, actual: float = 1000) -> IntervalPoint:
    return IntervalPoint(
        decision_date=date(2026, 1, 1),
        start_time=utc(2026, 1, 2),
        publish_time=utc(2026, 1, 1),
        horizon_hours=24,
        forecast_mw=actual + error,
        actual_mw=actual,
        error_mw=error,
    )


def test_metrics_formulae():
    metrics = compute_metrics([_point(e) for e in (-200, -100, 0, 100, 400)])

    assert metrics.paired_intervals == 5
    assert metrics.mae_mw == 160
    assert metrics.mean_error_mw == 40
    assert metrics.rmse_mw == pytest.approx((220000 / 5) ** 0.5)
    assert metrics.mape_percent == pytest.approx(16)
    assert metrics.nmae_percent == pytest.approx(16)
    assert metrics.error_p50_mw == 0
    assert metrics.error_p10_mw == pytest.approx(-160)
    assert metrics.error_p90_mw == pytest.approx(280)
    assert metrics.abs_error_p90_mw == pytest.approx(320)


def test_filter_by_decision_date_recomputes_metrics(db_session):
    db_session.add_all(
        [
            forecast(utc(2026, 1, 2, 10), utc(2026, 1, 1, 7, 30), 110),
            *hourly_actual(utc(2026, 1, 2, 10), 100),
            forecast(utc(2026, 1, 3, 10), utc(2026, 1, 2, 7, 30), 400),
            *hourly_actual(utc(2026, 1, 3, 10), 100),
        ]
    )
    db_session.commit()
    month = build_dashboard(db_session, NINE)

    day = filter_by_decision_date(month, date(2026, 1, 1))

    assert month.summary.mae_mw == 155
    assert day.summary.mae_mw == 10
    assert [p.decision_date for p in day.points] == [date(2026, 1, 1)]
    assert [row.decision_date for row in day.daily] == [date(2026, 1, 1)]
    assert [group.label for group in day.by_hour_of_day] == ["10:00"]
