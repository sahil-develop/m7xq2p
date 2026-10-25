import { useEffect, useMemo, useState } from "react";

import { fetchDashboard } from "./api";
import { BiasByHourChart, DailyMaeChart, HorizonChart } from "./components/BarCharts";
import { DailyTable } from "./components/DailyTable";
import { ForecastChart } from "./components/ForecastChart";
import { Kpis } from "./components/Kpis";
import { formatDateTime, formatIsoDate, formatSigned, toChartRows } from "./lib";
import type { AccuracyMetrics, Dashboard } from "./types";

// WINDFOR runs are published ~02:30, 04:30, 07:30, 09:30, 11:30 UK time in January.
const CUTOFFS = [
  { value: "06:00", label: "06:00 – early desk" },
  { value: "09:00", label: "09:00 – before auction gate closure" },
  { value: "11:00", label: "11:00 – late morning" },
  { value: "13:00", label: "13:00 – after midday run" },
];

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: Dashboard };

function initialParam(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name);
}

export default function App() {
  const [cutoff, setCutoff] = useState(() => {
    const fromUrl = initialParam("cutoff");
    return CUTOFFS.some((option) => option.value === fromUrl) ? fromUrl! : "09:00";
  });
  const [selected, setSelected] = useState<string | null>(() => initialParam("day"));
  const [state, setState] = useState<LoadState>({ status: "loading" });

  // Keep the view in the URL so a specific day/cutoff can be shared.
  useEffect(() => {
    const params = new URLSearchParams({ cutoff });
    if (selected) params.set("day", selected);
    window.history.replaceState(null, "", `?${params}`);
  }, [cutoff, selected]);

  useEffect(() => {
    const controller = new AbortController();
    setState((previous) => (previous.status === "ready" ? previous : { status: "loading" }));
    fetchDashboard(cutoff, controller.signal)
      .then((data) => setState({ status: "ready", data }))
      .catch((error: Error) => {
        if (error.name !== "AbortError") setState({ status: "error", message: error.message });
      });
    return () => controller.abort();
  }, [cutoff]);

  const data = state.status === "ready" ? state.data : null;
  const view = useMemo(() => {
    if (!data) return null;
    const day = selected ? data.daily.find((row) => row.decision_date === selected) : undefined;
    const points = day ? data.points.filter((p) => p.decision_date === day.decision_date) : data.points;
    const metrics: AccuracyMetrics = day ?? data.summary;
    // The likely-range band always uses the month's error distribution: one day is too few hours.
    return { day, metrics, rows: toChartRows(points, data.summary) };
  }, [data, selected]);

  const toggleDay = (decisionDate: string) =>
    setSelected((current) => (current === decisionDate ? null : decisionDate));

  return (
    <div className="page">
      <header className="header">
        <div>
          <p className="eyebrow">GB day-ahead wind · January 2026 purchase decisions</p>
          <h1>Wind Forecast Insights</h1>
          <p className="lede">
            The national wind forecast your desk could see at decision time, compared with what
            the wind actually delivered the next day.
          </p>
        </div>
        {data && (
          <p className="freshness">
            Source: Elexon BMRS WINDFOR &amp; FUELHH
            <br />
            Synced {data.last_synced_at ? formatDateTime(data.last_synced_at) : "never"}
          </p>
        )}
      </header>

      <section className="controls card" aria-label="Filters">
        <label>
          Decision cutoff (UK time)
          <select value={cutoff} onChange={(event) => setCutoff(event.target.value)}>
            {CUTOFFS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Decision day
          <select
            value={selected ?? ""}
            onChange={(event) => setSelected(event.target.value || null)}
            disabled={!data}
          >
            <option value="">All of January</option>
            {data?.daily.map((row) => (
              <option key={row.decision_date} value={row.decision_date}>
                {formatIsoDate(row.decision_date)} → delivery {formatIsoDate(row.delivery_date)}
              </option>
            ))}
          </select>
        </label>
      </section>

      {state.status === "loading" && <p className="status">Loading forecasts…</p>}
      {state.status === "error" && (
        <p className="status error" role="alert">
          Could not load the dashboard. {state.message}
        </p>
      )}

      {data && view && (
        <>
          <Kpis metrics={view.metrics} />

          <section className="card">
            <div className="card-head">
              <h2>
                {view.day
                  ? `Delivery ${formatIsoDate(view.day.delivery_date)}: forecast vs actual`
                  : "Forecast vs actual, every delivery hour"}
              </h2>
              {view.day && (
                <button type="button" className="ghost" onClick={() => setSelected(null)}>
                  Show all of January
                </button>
              )}
            </div>
            <p className="caption">
              {view.day?.latest_publish_time
                ? `Forecast published ${formatDateTime(view.day.latest_publish_time)}, the latest available before ${data.decision_cutoff_local} on ${formatIsoDate(view.day.decision_date)}. `
                : `Each hour shows the latest forecast published before ${data.decision_cutoff_local} UK time on the day before delivery. `}
              The shaded band is where actual wind fell in 80% of January hours relative to the
              forecast: plan for between{" "}
              <strong>{formatSigned(-(data.summary.error_p90_mw ?? 0))}</strong> and{" "}
              <strong>{formatSigned(-(data.summary.error_p10_mw ?? 0))}</strong> versus the forecast.
            </p>
            <ForecastChart rows={view.rows} singleDay={Boolean(view.day)} />
          </section>

          <div className="grid-2">
            <section className="card">
              <h2>Daily mean absolute error</h2>
              <p className="caption">By delivery day. Select a bar to inspect that day.</p>
              <DailyMaeChart daily={data.daily} selected={selected} onSelect={toggleDay} />
            </section>
            <section className="card">
              <h2>Bias by delivery hour</h2>
              <p className="caption">
                <span className="swatch over" /> over-forecast &nbsp;
                <span className="swatch under" /> under-forecast. Mean of forecast − actual.
              </p>
              <BiasByHourChart groups={data.by_hour_of_day} />
            </section>
          </div>

          <section className="card">
            <h2>Error by forecast horizon</h2>
            <p className="caption">
              Hours between forecast publication and delivery. Earlier cutoffs push decisions to
              longer horizons.
            </p>
            <HorizonChart groups={data.by_horizon} />
          </section>

          <section className="card">
            <h2>Daily accuracy table</h2>
            <DailyTable daily={data.daily} selected={selected} onSelect={toggleDay} />
          </section>

          <footer className="footer">
            Error = forecast − actual. Actual is the mean of the two half-hourly FUELHH WIND
            values in each hour, to match hourly WINDFOR forecasts. API docs at{" "}
            <a href="/docs">/docs</a>.
          </footer>
        </>
      )}
    </div>
  );
}
