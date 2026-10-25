"""Forecast selection and accuracy metrics for day-ahead purchase decisions.

For every hourly delivery target we pick the forecast a trader would actually have
seen: the most recent WINDFOR value published at or before the decision cutoff on the
previous day. That forecast is compared with the FUELHH outturn averaged over the
same hour (two half-hourly settlement periods), because WINDFOR is hourly.
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from math import sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ImportState, WindActual, WindForecast
from app.period import (
    DECISION_END,
    DECISION_START,
    LONDON,
    cutoff_for,
    decision_date_for,
    decision_dates,
    delivery_window,
)
from app.schemas import (
    AccuracyMetrics,
    DailyAccuracy,
    DashboardResponse,
    GroupAccuracy,
    IntervalPoint,
)

HORIZON_BUCKET_HOURS = 6
HALF_HOUR = timedelta(minutes=30)


def _quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated quantile (same definition as numpy's default)."""
    position = (len(sorted_values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def compute_metrics(points: Iterable[IntervalPoint]) -> AccuracyMetrics:
    paired = [p for p in points if p.error_mw is not None and p.actual_mw is not None]
    if not paired:
        return AccuracyMetrics(paired_intervals=0)
    errors = [p.error_mw for p in paired]
    actuals = [p.actual_mw for p in paired]
    abs_errors = sorted(abs(e) for e in errors)
    signed = sorted(errors)
    mean_actual = sum(actuals) / len(actuals)
    mae = sum(abs_errors) / len(abs_errors)
    percentage_errors = [abs(e) / a * 100 for e, a in zip(errors, actuals, strict=True) if a > 0]
    return AccuracyMetrics(
        paired_intervals=len(paired),
        mae_mw=mae,
        rmse_mw=sqrt(sum(e * e for e in errors) / len(errors)),
        mean_error_mw=sum(errors) / len(errors),
        mape_percent=(
            sum(percentage_errors) / len(percentage_errors) if percentage_errors else None
        ),
        nmae_percent=mae / mean_actual * 100 if mean_actual > 0 else None,
        error_p10_mw=_quantile(signed, 0.10),
        error_p50_mw=_quantile(signed, 0.50),
        error_p90_mw=_quantile(signed, 0.90),
        abs_error_p90_mw=_quantile(abs_errors, 0.90),
    )


def hourly_actuals(actuals: Iterable[WindActual]) -> dict[datetime, float]:
    """Average half-hourly outturn into hours; hours missing either half are dropped."""
    halves: dict[datetime, list[float]] = defaultdict(list)
    for actual in actuals:
        start = actual.start_time
        hour = start.replace(minute=0, second=0, microsecond=0)
        if start - hour not in (timedelta(0), HALF_HOUR):
            continue
        halves[hour].append(actual.generation_mw)
    return {hour: sum(values) / 2 for hour, values in halves.items() if len(values) == 2}


def select_forecasts(
    forecasts: Iterable[WindForecast], cutoff: time
) -> dict[datetime, WindForecast]:
    """Latest forecast per target time that was published before its decision cutoff.

    `forecasts` must be ordered by (start_time, publish_time) so later rows win.
    """
    chosen: dict[datetime, WindForecast] = {}
    for forecast in forecasts:
        decision_date = decision_date_for(forecast.start_time)
        if not DECISION_START <= decision_date <= DECISION_END:
            continue
        if forecast.publish_time > cutoff_for(decision_date, cutoff):
            continue
        chosen[forecast.start_time] = forecast
    return chosen


def _group(points: list[IntervalPoint], key, labels: dict[int, str]) -> list[GroupAccuracy]:
    grouped: dict[int, list[IntervalPoint]] = defaultdict(list)
    for point in points:
        grouped[key(point)].append(point)
    return [
        GroupAccuracy(
            key=k, label=labels.get(k, str(k)), **compute_metrics(grouped[k]).model_dump()
        )
        for k in sorted(grouped)
    ]


def build_dashboard(session: Session, cutoff: time) -> DashboardResponse:
    window_start, window_end = delivery_window()
    latest_cutoff = cutoff_for(DECISION_END, cutoff)
    forecasts = session.scalars(
        select(WindForecast)
        .where(
            WindForecast.start_time >= window_start,
            WindForecast.start_time < window_end,
            WindForecast.publish_time <= latest_cutoff,
        )
        .order_by(WindForecast.start_time, WindForecast.publish_time)
    ).all()
    actuals = session.scalars(
        select(WindActual).where(
            WindActual.start_time >= window_start, WindActual.start_time < window_end
        )
    ).all()
    actual_by_hour = hourly_actuals(actuals)

    points: list[IntervalPoint] = []
    for start_time, forecast in sorted(select_forecasts(forecasts, cutoff).items()):
        actual_mw = actual_by_hour.get(start_time)
        points.append(
            IntervalPoint(
                decision_date=decision_date_for(start_time),
                start_time=start_time,
                publish_time=forecast.publish_time,
                horizon_hours=(start_time - forecast.publish_time).total_seconds() / 3600,
                forecast_mw=forecast.generation_mw,
                actual_mw=actual_mw,
                error_mw=forecast.generation_mw - actual_mw if actual_mw is not None else None,
            )
        )

    by_decision: dict[date, list[IntervalPoint]] = defaultdict(list)
    for point in points:
        by_decision[point.decision_date].append(point)
    daily = [
        DailyAccuracy(
            decision_date=day,
            delivery_date=day + timedelta(days=1),
            forecast_hours=len(by_decision[day]),
            forecast_energy_mwh=sum(p.forecast_mw for p in by_decision[day]),
            latest_publish_time=max((p.publish_time for p in by_decision[day]), default=None),
            **compute_metrics(by_decision[day]).model_dump(),
        )
        for day in decision_dates()
    ]

    state = session.get(ImportState, 1)
    return DashboardResponse(
        period_start=DECISION_START,
        period_end=DECISION_END,
        decision_cutoff_local=cutoff.strftime("%H:%M"),
        last_synced_at=state.last_synced_at if state else None,
        points=points,
        daily=daily,
        **_breakdowns(points),
    )


def _breakdowns(points: list[IntervalPoint]) -> dict:
    return {
        "summary": compute_metrics(points),
        "by_hour_of_day": _group(
            points,
            lambda p: p.start_time.astimezone(LONDON).hour,
            {h: f"{h:02d}:00" for h in range(24)},
        ),
        "by_horizon": _group(
            points,
            lambda p: int(p.horizon_hours // HORIZON_BUCKET_HOURS),
            {
                b: f"{b * HORIZON_BUCKET_HOURS}–{(b + 1) * HORIZON_BUCKET_HOURS} h"
                for b in range(20)
            },
        ),
    }


def filter_by_decision_date(dashboard: DashboardResponse, day: date) -> DashboardResponse:
    """Restrict a month-wide dashboard to one decision date, recomputing its metrics."""
    points = [p for p in dashboard.points if p.decision_date == day]
    return dashboard.model_copy(
        update={
            "points": points,
            "daily": [row for row in dashboard.daily if row.decision_date == day],
            **_breakdowns(points),
        }
    )
