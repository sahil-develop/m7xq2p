from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class IntervalPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision_date: date
    start_time: datetime
    publish_time: datetime
    forecast_mw: float
    actual_mw: float | None
    error_mw: float | None


class AccuracyMetrics(BaseModel):
    paired_intervals: int
    mae_mw: float | None
    rmse_mw: float | None
    mean_error_mw: float | None
    mape_percent: float | None


class DailyAccuracy(BaseModel):
    decision_date: date
    delivery_date: date
    paired_intervals: int
    mae_mw: float | None
    rmse_mw: float | None
    mean_error_mw: float | None
    mape_percent: float | None
    latest_publish_time: datetime | None


class DashboardResponse(BaseModel):
    period_start: date
    period_end: date
    decision_cutoff_local: str
    summary: AccuracyMetrics
    latest_forecast_publish_time: datetime | None
    last_synced_at: datetime | None
    points: list[IntervalPoint]
    daily: list[DailyAccuracy]


class IngestionAccepted(BaseModel):
    task_id: str
    status: str


class HealthResponse(BaseModel):
    status: str
    dependencies: dict[str, str]
