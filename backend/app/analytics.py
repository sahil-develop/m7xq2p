from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from math import sqrt
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ImportState, WindActual, WindForecast
from app.schemas import AccuracyMetrics, DashboardResponse, DailyAccuracy, IntervalPoint

DECISION_START = date(2026, 1, 1)
DECISION_END = date(2026, 1, 31)
LONDON = ZoneInfo("Europe/London")
DECISION_CUTOFF = time(11, 0)


def _metrics(errors: list[float], actuals: list[float]) -> AccuracyMetrics:
    if not errors:
        return AccuracyMetrics(
            paired_intervals=0,
            mae_mw=None,
            rmse_mw=None,
            mean_error_mw=None,
            mape_percent=None,
        )
    percentage_errors = [
        abs(error) / abs(actual) * 100
        for error, actual in zip(errors, actuals, strict=True)
        if actual != 0
    ]
    return AccuracyMetrics(
        paired_intervals=len(errors),
        mae_mw=sum(abs(error) for error in errors) / len(errors),
        rmse_mw=sqrt(sum(error * error for error in errors) / len(errors)),
        mean_error_mw=sum(errors) / len(errors),
        mape_percent=(
            sum(percentage_errors) / len(percentage_errors) if percentage_errors else None
        ),
    )


def build_dashboard(session: Session) -> DashboardResponse:
    target_start = datetime(2026, 1, 2, tzinfo=timezone.utc)
    target_end = datetime(2026, 2, 2, tzinfo=timezone.utc)
    forecasts = session.scalars(
        select(WindForecast)
        .where(WindForecast.start_time >= target_start, WindForecast.start_time < target_end)
        .order_by(WindForecast.start_time, WindForecast.publish_time)
    ).all()
    actuals = session.scalars(
        select(WindActual)
        .where(WindActual.start_time >= target_start, WindActual.start_time < target_end)
        .order_by(WindActual.start_time)
    ).all()
    actual_by_time = {actual.start_time: actual.generation_mw for actual in actuals}

    latest_by_start: dict[datetime, WindForecast] = {}
    for forecast in forecasts:
        local_start = forecast.start_time.astimezone(LONDON)
        decision_date = local_start.date() - timedelta(days=1)
        if not DECISION_START <= decision_date <= DECISION_END:
            continue
        cutoff = datetime.combine(decision_date, DECISION_CUTOFF, tzinfo=LONDON)
        if forecast.publish_time.astimezone(LONDON) > cutoff:
            continue
        current = latest_by_start.get(forecast.start_time)
        if current is None or forecast.publish_time > current.publish_time:
            latest_by_start[forecast.start_time] = forecast

    daily_rows: dict[date, list[IntervalPoint]] = defaultdict(list)
    points: list[IntervalPoint] = []
    for start_time, forecast in sorted(latest_by_start.items()):
        decision_date = start_time.astimezone(LONDON).date() - timedelta(days=1)
        actual_mw = actual_by_time.get(start_time)
        error_mw = forecast.generation_mw - actual_mw if actual_mw is not None else None
        point = IntervalPoint(
            decision_date=decision_date,
            start_time=start_time,
            publish_time=forecast.publish_time,
            forecast_mw=forecast.generation_mw,
            actual_mw=actual_mw,
            error_mw=error_mw,
        )
        points.append(point)
        daily_rows[decision_date].append(point)

    all_errors = [point.error_mw for point in points if point.error_mw is not None]
    all_actuals = [point.actual_mw for point in points if point.error_mw is not None]
    daily: list[DailyAccuracy] = []
    for offset in range((DECISION_END - DECISION_START).days + 1):
        decision_date = DECISION_START + timedelta(days=offset)
        day_points = daily_rows[decision_date]
        paired = [point for point in day_points if point.error_mw is not None]
        metrics = _metrics(
            [point.error_mw for point in paired if point.error_mw is not None],
            [point.actual_mw for point in paired if point.actual_mw is not None],
        )
        daily.append(
            DailyAccuracy(
                decision_date=decision_date,
                delivery_date=decision_date + timedelta(days=1),
                **metrics.model_dump(),
                latest_publish_time=max(
                    (point.publish_time for point in day_points), default=None
                ),
            )
        )

    state = session.get(ImportState, 1)
    latest_publish = max((point.publish_time for point in points), default=None)
    return DashboardResponse(
        period_start=DECISION_START,
        period_end=DECISION_END,
        decision_cutoff_local="11:00 Europe/London (assumption documented in README)",
        summary=_metrics(all_errors, all_actuals),
        latest_forecast_publish_time=latest_publish,
        last_synced_at=state.last_synced_at if state else None,
        points=points,
        daily=daily,
    )
