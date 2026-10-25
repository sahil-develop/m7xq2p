import { formatGw, formatPercent, formatSigned } from "../lib";
import type { AccuracyMetrics } from "../types";

interface Tile {
  label: string;
  value: string;
  hint: string;
}

export function Kpis({ metrics }: { metrics: AccuracyMetrics }) {
  const tiles: Tile[] = [
    {
      label: "Mean absolute error",
      value: formatGw(metrics.mae_mw),
      hint: `${formatPercent(metrics.nmae_percent)} of mean outturn`,
    },
    {
      label: "Bias",
      value: formatSigned(metrics.mean_error_mw),
      hint:
        metrics.mean_error_mw === null
          ? "No paired hours"
          : metrics.mean_error_mw > 0
            ? "Forecast above actual on average"
            : "Forecast below actual on average",
    },
    {
      label: "RMSE",
      value: formatGw(metrics.rmse_mw),
      hint: "Penalises large misses",
    },
    {
      label: "90% of hours within",
      value: formatGw(metrics.abs_error_p90_mw),
      hint: "Absolute error, P90",
    },
    {
      label: "MAPE",
      value: formatPercent(metrics.mape_percent),
      hint: `${metrics.paired_intervals.toLocaleString("en-GB")} hours compared`,
    },
  ];
  return (
    <section className="kpis" aria-label="Forecast accuracy summary">
      {tiles.map((tile) => (
        <div className="kpi card" key={tile.label}>
          <div className="kpi-label">{tile.label}</div>
          <div className="kpi-value">{tile.value}</div>
          <div className="kpi-hint">{tile.hint}</div>
        </div>
      ))}
    </section>
  );
}
