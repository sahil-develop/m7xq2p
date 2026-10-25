from datetime import date, datetime

from pydantic import BaseModel, Field


class IntervalPoint(BaseModel):
    decision_date: date
    start_time: datetime = Field(description="Hourly delivery target (UTC)")
    publish_time: datetime = Field(description="When the selected forecast was published")
    horizon_hours: float = Field(description="Hours between publish time and target time")
    forecast_mw: float
    actual_mw: float | None = Field(description="Mean of the hour's two half-hourly outturns")
    error_mw: float | None = Field(description="forecast − actual; positive = over-forecast")


class AccuracyMetrics(BaseModel):
    paired_intervals: int
    mae_mw: float | None = None
    rmse_mw: float | None = None
    mean_error_mw: float | None = Field(default=None, description="Bias; positive = over-forecast")
    mape_percent: float | None = None
    nmae_percent: float | None = Field(default=None, description="MAE / mean actual × 100")
    error_p10_mw: float | None = None
    error_p50_mw: float | None = None
    error_p90_mw: float | None = None
    abs_error_p90_mw: float | None = None


class DailyAccuracy(AccuracyMetrics):
    decision_date: date
    delivery_date: date
    forecast_hours: int
    forecast_energy_mwh: float
    latest_publish_time: datetime | None


class GroupAccuracy(AccuracyMetrics):
    key: int
    label: str


class DashboardResponse(BaseModel):
    period_start: date
    period_end: date
    decision_cutoff_local: str = Field(description="HH:MM Europe/London on the decision day")
    summary: AccuracyMetrics
    last_synced_at: datetime | None
    points: list[IntervalPoint]
    daily: list[DailyAccuracy]
    by_hour_of_day: list[GroupAccuracy]
    by_horizon: list[GroupAccuracy]


class IngestionAccepted(BaseModel):
    task_id: str
    status: str


class HealthResponse(BaseModel):
    status: str
    dependencies: dict[str, str]
