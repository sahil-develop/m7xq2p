import { describe, expect, it } from "vitest";

import { formatIsoDate, formatSigned, toChartRows } from "./lib";
import type { AccuracyMetrics, IntervalPoint } from "./types";

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
