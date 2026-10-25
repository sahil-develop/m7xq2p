// Mirrors backend/app/schemas.py. Timestamps are ISO-8601 UTC strings.

export interface AccuracyMetrics {
  paired_intervals: number;
  mae_mw: number | null;
  rmse_mw: number | null;
  mean_error_mw: number | null;
  mape_percent: number | null;
  nmae_percent: number | null;
  error_p10_mw: number | null;
  error_p50_mw: number | null;
  error_p90_mw: number | null;
  abs_error_p90_mw: number | null;
}

export interface IntervalPoint {
  decision_date: string;
  start_time: string;
  publish_time: string;
  horizon_hours: number;
  forecast_mw: number;
  actual_mw: number | null;
  error_mw: number | null;
}

export interface DailyAccuracy extends AccuracyMetrics {
  decision_date: string;
  delivery_date: string;
  forecast_hours: number;
  forecast_energy_mwh: number;
  latest_publish_time: string | null;
}

export interface GroupAccuracy extends AccuracyMetrics {
  key: number;
  label: string;
}

export interface Dashboard {
  period_start: string;
  period_end: string;
  decision_cutoff_local: string;
  summary: AccuracyMetrics;
  last_synced_at: string | null;
  points: IntervalPoint[];
  daily: DailyAccuracy[];
  by_hour_of_day: GroupAccuracy[];
  by_horizon: GroupAccuracy[];
}
