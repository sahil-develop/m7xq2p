import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatGw, formatIsoDate, formatSigned } from "../lib";
import type { DailyAccuracy, GroupAccuracy } from "../types";

const axisProps = {
  stroke: "var(--axis)",
  tick: { fill: "var(--text-muted)", fontSize: 12 },
};
const tooltipStyle = {
  contentStyle: {
    background: "var(--surface-raised)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    color: "var(--text-primary)",
    fontSize: 13,
  },
  cursor: { fill: "var(--hover)" },
};
const gwTick = (value: number) => `${(value / 1000).toFixed(1)}`;
const gwLabel = {
  value: "GW",
  angle: -90,
  position: "insideLeft" as const,
  fill: "var(--text-muted)",
  fontSize: 12,
};
const xLabel = (value: string) => ({
  value,
  position: "insideBottom" as const,
  offset: -2,
  fill: "var(--text-muted)",
  fontSize: 12,
});

export function DailyMaeChart({
  daily,
  selected,
  onSelect,
}: {
  daily: DailyAccuracy[];
  selected: string | null;
  onSelect: (decisionDate: string) => void;
}) {
  const data = daily.map((row) => ({ ...row, day: Number(row.delivery_date.slice(8)) }));
  const scored = daily.filter((row) => row.mae_mw !== null);
  const worst = scored.reduce<DailyAccuracy | null>(
    (top, row) => (top === null || (row.mae_mw ?? 0) > (top.mae_mw ?? 0) ? row : top),
    null,
  );
  const summary =
    `Bar chart of mean absolute error for ${scored.length} delivery days` +
    (worst ? `; the largest was ${formatGw(worst.mae_mw)} on ${formatIsoDate(worst.delivery_date)}.` : ".");
  return (
    <div role="img" aria-label={summary}>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 12, left: 0 }} barCategoryGap={2}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis
            dataKey="delivery_date"
            tickFormatter={(v: string) => (v.slice(5, 7) === "02" ? "1 Feb" : String(Number(v.slice(8))))}
            {...axisProps}
            interval={2}
            label={xLabel("Delivery day (Jan)")}
            height={40}
          />
          <YAxis tickFormatter={gwTick} width={44} label={gwLabel} {...axisProps} />
          <Tooltip
            {...tooltipStyle}
            labelFormatter={(value: string) => `Delivery ${formatIsoDate(value)}`}
            formatter={(value: number) => [formatGw(value), "MAE"]}
          />
          <Bar
            dataKey="mae_mw"
            radius={[4, 4, 0, 0]}
            onClick={(row: DailyAccuracy) => onSelect(row.decision_date)}
            style={{ cursor: "pointer" }}
            isAnimationActive={false}
          >
            {data.map((row) => (
              <Cell
                key={row.decision_date}
                fill="var(--series-1)"
                fillOpacity={selected === null || selected === row.decision_date ? 1 : 0.3}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function BiasByHourChart({ groups }: { groups: GroupAccuracy[] }) {
  const over = groups.filter((g) => (g.mean_error_mw ?? 0) > 0).length;
  const summary = `Bar chart of mean forecast minus actual by delivery hour; ${over} of ${groups.length} hours are over-forecast on average.`;
  return (
    <div role="img" aria-label={summary}>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={groups} margin={{ top: 8, right: 8, bottom: 12, left: 0 }} barCategoryGap={2}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="label" {...axisProps} interval={3} label={xLabel("Delivery hour (UK)")} height={40} />
          <YAxis tickFormatter={gwTick} width={44} label={gwLabel} {...axisProps} />
          <ReferenceLine y={0} stroke="var(--axis)" />
          <Tooltip
            {...tooltipStyle}
            labelFormatter={(label: string) => `Delivery hour ${label} (UK)`}
            formatter={(value: number) => [formatSigned(value), "Bias"]}
          />
          <Bar dataKey="mean_error_mw" isAnimationActive={false} radius={4}>
            {groups.map((group) => (
              <Cell
                key={group.key}
                fill={(group.mean_error_mw ?? 0) >= 0 ? "var(--over)" : "var(--under)"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function HorizonChart({ groups }: { groups: GroupAccuracy[] }) {
  const summary =
    "Bar chart of mean absolute error by forecast horizon: " +
    groups.map((g) => `${g.label} ${formatGw(g.mae_mw)}`).join(", ") +
    ".";
  return (
    <div role="img" aria-label={summary}>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={groups} margin={{ top: 8, right: 8, bottom: 12, left: 0 }} barCategoryGap={8}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="label" {...axisProps} label={xLabel("Hours from publication to delivery")} height={40} />
          <YAxis tickFormatter={gwTick} width={44} label={gwLabel} {...axisProps} />
          <Tooltip
            {...tooltipStyle}
            labelFormatter={(label: string) => `${label} ahead`}
            formatter={(value: number, _name, item) => [
              `${formatGw(value)} (${item.payload.paired_intervals} hours)`,
              "MAE",
            ]}
          />
          <Bar dataKey="mae_mw" fill="var(--series-1)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
