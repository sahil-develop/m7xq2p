import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TooltipProps } from "recharts";

import { formatDateTime, formatDay, formatMw, type ChartRow } from "../lib";

function ChartTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as ChartRow;
  return (
    <div className="tooltip">
      <div className="tooltip-title">{formatDateTime(row.time)}</div>
      <div><span className="swatch forecast" />Forecast {formatMw(row.forecast)}</div>
      <div><span className="swatch actual" />Actual {formatMw(row.actual)}</div>
      {row.band && (
        <div className="muted">
          Likely range {formatMw(row.band[0])} – {formatMw(row.band[1])}
        </div>
      )}
      {row.actual !== null && (
        <div className="muted">Error {formatMw(row.forecast - row.actual)}</div>
      )}
    </div>
  );
}

export function ForecastChart({ rows, singleDay }: { rows: ChartRow[]; singleDay: boolean }) {
  // Whole-GW gridlines: every 5 GW across the month, every 2 GW for a single day.
  const step = singleDay ? 2000 : 5000;
  const peak = Math.max(1, ...rows.flatMap((r) => [r.forecast, r.actual ?? 0, r.band?.[1] ?? 0]));
  const yTicks = Array.from({ length: Math.ceil(peak / step) + 1 }, (_, i) => i * step);
  return (
    <ResponsiveContainer width="100%" height={340}>
      <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis
          dataKey="time"
          type="number"
          scale="time"
          domain={["dataMin", "dataMax"]}
          tickFormatter={(value: number) =>
            singleDay ? formatDateTime(value).split(", ")[1] ?? "" : formatDay(value)
          }
          stroke="var(--axis)"
          tick={{ fill: "var(--text-muted)", fontSize: 12 }}
          minTickGap={24}
        />
        <YAxis
          ticks={yTicks}
          domain={[0, yTicks[yTicks.length - 1]]}
          tickFormatter={(value: number) => `${value / 1000}`}
          stroke="var(--axis)"
          tick={{ fill: "var(--text-muted)", fontSize: 12 }}
          label={{
            value: "GW",
            angle: -90,
            position: "insideLeft",
            fill: "var(--text-muted)",
            fontSize: 12,
          }}
          width={44}
        />
        <Tooltip content={<ChartTooltip />} />
        <Legend wrapperStyle={{ fontSize: 13, color: "var(--text-secondary)" }} />
        <Area
          dataKey="band"
          name="Likely range"
          stroke="none"
          fill="var(--series-1)"
          fillOpacity={0.14}
          isAnimationActive={false}
        />
        <Line
          dataKey="forecast"
          name="Forecast"
          stroke="var(--series-1)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
        <Line
          dataKey="actual"
          name="Actual"
          stroke="var(--series-2)"
          strokeWidth={2}
          dot={false}
          connectNulls={false}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
