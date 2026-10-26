import { describe, expect, it } from "vitest";

import { biasHint, formatIsoDate, formatSigned, resolveView, toChartRows } from "./lib";
import type { AccuracyMetrics, DailyAccuracy, Dashboard, IntervalPoint } from "./types";

const metrics: AccuracyMetrics = {
  paired_intervals: 10,
  mae_mw: 100,
  rmse_mw: 120,
  mean_error_mw: 20,
  mape_percent: 5,
  nmae_percent: 5,
  error_p10_mw: -500,
  error_p50_mw: 0,
  error_p90_mw: 1500,
  abs_error_p90_mw: 1500,
};

const point = (forecast: number): IntervalPoint => ({
  decision_date: "2026-01-01",
  start_time: "2026-01-02T10:00:00Z",
  publish_time: "2026-01-01T07:30:00Z",
  horizon_hours: 26.5,
  forecast_mw: forecast,
  actual_mw: null,
  error_mw: null,
});

describe("toChartRows", () => {
  it("turns error quantiles into an expected-actual range around the forecast", () => {
    const [row] = toChartRows([point(10000)], metrics);
    expect(row.band).toEqual([8500, 10500]);
    expect(row.time).toBe(Date.UTC(2026, 0, 2, 10));
  });

  it("clamps the range at zero generation", () => {
    expect(toChartRows([point(1000)], metrics)[0].band).toEqual([0, 1500]);
  });

  it("omits the band when no accuracy history exists", () => {
    const empty = { ...metrics, error_p10_mw: null, error_p90_mw: null };
    expect(toChartRows([point(1000)], empty)[0].band).toBeNull();
  });
});

describe("formatters", () => {
  it("formats signed errors in GW", () => {
    expect(formatSigned(1748)).toBe("+1.75 GW");
    expect(formatSigned(-500)).toBe("-0.50 GW");
    expect(formatSigned(null)).toBe("–");
  });

  it("keeps calendar dates on the same London day", () => {
    expect(formatIsoDate("2026-01-31")).toBe("Sat 31 Jan");
  });
});

const dayRow = (decision: string, delivery: string, mae: number): DailyAccuracy => ({
  ...metrics,
  mae_mw: mae,
  decision_date: decision,
  delivery_date: delivery,
  forecast_hours: 1,
  forecast_energy_mwh: 1000,
  latest_publish_time: `${decision}T07:30:00Z`,
});

const dashboard: Dashboard = {
  period_start: "2026-01-01",
  period_end: "2026-01-31",
  decision_cutoff_local: "09:00",
  summary: metrics,
  last_synced_at: null,
  points: [point(10000), { ...point(4000), decision_date: "2026-01-02", start_time: "2026-01-03T10:00:00Z" }],
  daily: [dayRow("2026-01-01", "2026-01-02", 111), dayRow("2026-01-02", "2026-01-03", 222)],
  by_hour_of_day: [],
  by_horizon: [],
};

describe("resolveView", () => {
  it("shows the whole month when no day is selected", () => {
    const view = resolveView(dashboard, null);
    expect(view.day).toBeUndefined();
    expect(view.metrics).toBe(dashboard.summary);
    expect(view.rows).toHaveLength(2);
  });

  it("filters points and metrics to the selected decision day", () => {
    const view = resolveView(dashboard, "2026-01-02");
    expect(view.day?.delivery_date).toBe("2026-01-03");
    expect(view.metrics.mae_mw).toBe(222);
    expect(view.points.map((p) => p.forecast_mw)).toEqual([4000]);
  });

  it("keeps the month-wide error band for a single day", () => {
    const [row] = resolveView(dashboard, "2026-01-02").rows;
    expect(row.band).toEqual([2500, 4500]);
  });

  it("falls back to the month for a day outside the window", () => {
    const view = resolveView(dashboard, "2026-02-14");
    expect(view.day).toBeUndefined();
    expect(view.points).toHaveLength(2);
  });
});

describe("biasHint", () => {
  it("describes the sign of the bias, including exactly zero", () => {
    expect(biasHint(5)).toBe("Forecast above actual on average");
    expect(biasHint(-5)).toBe("Forecast below actual on average");
    expect(biasHint(0)).toBe("No average bias");
    expect(biasHint(null)).toBe("No paired hours");
  });
});
