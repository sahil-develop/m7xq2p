import { useEffect, useMemo, useState } from "react";

import { fetchDashboard } from "./api";
import { BiasByHourChart, DailyMaeChart, HorizonChart } from "./components/BarCharts";
import { DailyTable } from "./components/DailyTable";
import { ForecastChart } from "./components/ForecastChart";
import { Kpis } from "./components/Kpis";
import { formatDateTime, formatGw, formatIsoDate, formatSigned, resolveView } from "./lib";
import type { Dashboard } from "./types";

// WINDFOR runs are published ~02:30, 04:30, 07:30, 09:30, 11:30 UK time in January.
const CUTOFFS = [
  { value: "06:00", label: "06:00 – early desk" },
  { value: "09:00", label: "09:00 – before auction gate closure" },
  { value: "11:00", label: "11:00 – late morning" },
  { value: "13:00", label: "13:00 – after midday run" },
];

function initialParam(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name);
}

export default function App() {
  const [cutoff, setCutoff] = useState(() => {
    const fromUrl = initialParam("cutoff");
    return CUTOFFS.some((option) => option.value === fromUrl) ? fromUrl! : "09:00";
  });
  const [selected, setSelected] = useState<string | null>(() => initialParam("day"));
  // The last good payload stays on screen while a new cutoff loads or after a failed refresh.
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Keep the view in the URL so a specific day/cutoff can be shared.
  useEffect(() => {
    const params = new URLSearchParams({ cutoff });
    if (selected) params.set("day", selected);
    window.history.replaceState(null, "", `?${params}`);
  }, [cutoff, selected]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchDashboard(cutoff, controller.signal)
      .then((payload) => {
        setData(payload);
        setLoading(false);
      })
      .catch((reason: Error) => {
        if (reason.name === "AbortError") return;
        setError(reason.message);
        setLoading(false);
      });
    return () => controller.abort();
  }, [cutoff, attempt]);

  // A shared link may name a day outside the window; fall back to the whole month.
  useEffect(() => {
    if (data && selected && !data.daily.some((row) => row.decision_date === selected)) {
      setSelected(null);
    }
  }, [data, selected]);

  const view = useMemo(() => (data ? resolveView(data, selected) : null), [data, selected]);
  const stale = data !== null && data.decision_cutoff_local !== cutoff;
  const hasData = data !== null && data.points.length > 0;

  const toggleDay = (decisionDate: string) =>
    setSelected((current) => (current === decisionDate ? null : decisionDate));
  const retry = () => setAttempt((n) => n + 1);

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
            Last synced{" "}
            {data.last_synced_at ? `${formatDateTime(data.last_synced_at)} UK` : "never"}
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
            value={view?.day ? view.day.decision_date : ""}
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
        <p className="controls-note">
          Only forecasts published at or before the cutoff on the decision day are used. A
          decision on day D buys power for delivery on D+1.
        </p>
      </section>

      <div aria-live="polite">
        {loading && (
          <p className="status">
            <span className="spinner" aria-hidden="true" />
            {data ? `Loading the ${cutoff} cutoff…` : "Loading forecasts…"}
          </p>
        )}
        {error && (
          <div className="status error" role="alert">
            <span>
              {stale
                ? `Could not load the ${cutoff} cutoff, so the ${data!.decision_cutoff_local} view is still shown. `
                : "Could not load the dashboard. "}
              {error}
            </span>
            <button type="button" className="ghost" onClick={retry}>
              Retry
            </button>
          </div>
        )}
      </div>

      {data && !hasData && (
        <section className="card empty">
          <h2>No forecast data loaded yet</h2>
          <p className="caption">
            The database has no WINDFOR forecasts for the January 2026 window. Load them with{" "}
            <code>python -m app.ingestion</code> (Docker Compose does this on first start), then
            reload this page.
          </p>
        </section>
      )}

      {data && hasData && view && (
        <div className={stale && loading ? "content is-updating" : "content"} aria-busy={loading}>
          <Kpis metrics={view.metrics} scope={view.day ? "day" : "month"} />

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
                ? `Forecast published ${formatDateTime(view.day.latest_publish_time)} UK, the latest available before ${data.decision_cutoff_local} on ${formatIsoDate(view.day.decision_date)}. `
                : `Each hour shows the latest forecast published before ${data.decision_cutoff_local} UK time on the day before delivery. `}
              The shaded band is where actual wind fell in 80% of January hours relative to the
              forecast: plan for between{" "}
              <strong>{formatSigned(-(data.summary.error_p90_mw ?? 0))}</strong> and{" "}
              <strong>{formatSigned(-(data.summary.error_p10_mw ?? 0))}</strong> versus the forecast.
              The band is measured on January itself, so it describes this month's error rather
              than a validated out-of-sample prediction.
            </p>
            {view.day && view.day.forecast_hours > 0 && (
              <dl className="day-facts">
                <div>
                  <dt>Forecast energy</dt>
                  <dd>{(view.day.forecast_energy_mwh / 1000).toFixed(0)} GWh</dd>
                </div>
                <div>
                  <dt>Peak forecast hour</dt>
                  <dd>{formatGw(Math.max(...view.points.map((p) => p.forecast_mw)))}</dd>
                </div>
                <div>
                  <dt>Lowest forecast hour</dt>
                  <dd>{formatGw(Math.min(...view.points.map((p) => p.forecast_mw)))}</dd>
                </div>
                <div>
                  <dt>Hours compared with outturn</dt>
                  <dd>
                    {view.day.paired_intervals} of {view.day.forecast_hours}
                  </dd>
                </div>
              </dl>
            )}
            {view.rows.length > 0 ? (
              <ForecastChart rows={view.rows} singleDay={Boolean(view.day)} />
            ) : (
              <p className="empty-note">
                No forecast was published before {data.decision_cutoff_local} for this delivery
                day.
              </p>
            )}
          </section>

          <div className="grid-2">
            <section className="card">
              <h2>Daily mean absolute error</h2>
              <p className="caption">
                By delivery day, all of January. Select a bar to inspect that day.
              </p>
              <DailyMaeChart daily={data.daily} selected={view.day?.decision_date ?? null} onSelect={toggleDay} />
            </section>
            <section className="card">
              <h2>Bias by delivery hour</h2>
              <p className="caption">
                <span className="swatch over" /> over-forecast &nbsp;
                <span className="swatch under" /> under-forecast. Mean of forecast − actual across
                all of January.
              </p>
              <BiasByHourChart groups={data.by_hour_of_day} />
            </section>
          </div>

          <section className="card">
            <h2>Error by forecast horizon</h2>
            <p className="caption">
              Mean absolute error by hours between forecast publication and delivery, all of
              January. Earlier cutoffs push decisions to longer horizons.
            </p>
            <HorizonChart groups={data.by_horizon} />
          </section>

          <section className="card">
            <h2>Daily accuracy table</h2>
            <p className="caption">Select a decision day to inspect it above.</p>
            <DailyTable daily={data.daily} selected={view.day?.decision_date ?? null} onSelect={toggleDay} />
          </section>
        </div>
      )}

      {data && (
        <footer className="footer">
          Error = forecast − actual, so positive means the forecast was too high. Actual is the
          mean of the two half-hourly FUELHH WIND values in each hour, to match hourly WINDFOR
          forecasts. API docs at <a href="/docs">/docs</a>.
        </footer>
      )}
    </div>
  );
}
