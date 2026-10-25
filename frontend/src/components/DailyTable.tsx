import { formatDateTime, formatGw, formatIsoDate, formatPercent, formatSigned } from "../lib";
import type { DailyAccuracy } from "../types";

export function DailyTable({
  daily,
  selected,
  onSelect,
}: {
  daily: DailyAccuracy[];
  selected: string | null;
  onSelect: (decisionDate: string) => void;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">Decision day</th>
            <th scope="col">Delivery day</th>
            <th scope="col">Forecast used (published)</th>
            <th scope="col" className="num">Forecast energy</th>
            <th scope="col" className="num">MAE</th>
            <th scope="col" className="num">Bias</th>
            <th scope="col" className="num">nMAE</th>
            <th scope="col" className="num">Hours</th>
          </tr>
        </thead>
        <tbody>
          {daily.map((row) => (
            <tr
              key={row.decision_date}
              className={row.decision_date === selected ? "selected" : undefined}
            >
              <td>
                <button type="button" className="link" onClick={() => onSelect(row.decision_date)}>
                  {formatIsoDate(row.decision_date)}
                </button>
              </td>
              <td>{formatIsoDate(row.delivery_date)}</td>
              <td>{row.latest_publish_time ? formatDateTime(row.latest_publish_time) : "–"}</td>
              <td className="num">{(row.forecast_energy_mwh / 1000).toFixed(0)} GWh</td>
              <td className="num">{formatGw(row.mae_mw)}</td>
              <td className="num">{formatSigned(row.mean_error_mw)}</td>
              <td className="num">{formatPercent(row.nmae_percent)}</td>
              <td className="num">
                {row.paired_intervals}/{row.forecast_hours}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
