import type { AccuracyMetrics, IntervalPoint } from "./types";

export const LONDON = "Europe/London";

export interface ChartRow {
  time: number;
  forecast: number;
  actual: number | null;
  /** [low, high] range the actual is expected to fall in, from historical error quantiles. */
  band: [number, number] | null;
}

/**
 * error = forecast − actual, so actual = forecast − error. With P10/P90 of the error,
 * 80% of historical hours had actual within [forecast − P90, forecast − P10].
 */
export function toChartRows(points: IntervalPoint[], metrics: AccuracyMetrics): ChartRow[] {
  const { error_p10_mw: p10, error_p90_mw: p90 } = metrics;
  return points.map((point) => ({
    time: Date.parse(point.start_time),
    forecast: point.forecast_mw,
    actual: point.actual_mw,
    band:
      p10 !== null && p90 !== null
        ? [Math.max(0, point.forecast_mw - p90), Math.max(0, point.forecast_mw - p10)]
        : null,
  }));
}

export function formatMw(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "–";
  return `${value.toLocaleString("en-GB", { maximumFractionDigits: digits })} MW`;
}

export function formatGw(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  return `${(value / 1000).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} GW`;
}

export function formatSigned(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  const gw = (value / 1000).toLocaleString("en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    signDisplay: "exceptZero",
  });
  return `${gw} GW`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  return `${value.toFixed(1)}%`;
}

const dateTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: LONDON,
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
const dayOnly = new Intl.DateTimeFormat("en-GB", { timeZone: LONDON, day: "numeric", month: "short" });
const weekdayDay = new Intl.DateTimeFormat("en-GB", {
  timeZone: LONDON,
  weekday: "short",
  day: "numeric",
  month: "short",
});

export const formatDateTime = (value: string | number) => dateTime.format(new Date(value));
export const formatDay = (value: string | number) => dayOnly.format(new Date(value));
/** ISO calendar dates (YYYY-MM-DD) are read as midday UTC so the London date never shifts. */
export const formatIsoDate = (iso: string) => weekdayDay.format(new Date(`${iso}T12:00:00Z`));
