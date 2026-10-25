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
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={2}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="delivery_date" tickFormatter={(v: string) => String(Number(v.slice(8)))} {...axisProps} interval={2} />
        <YAxis tickFormatter={gwTick} width={36} {...axisProps} />
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
  );
}

export function BiasByHourChart({ groups }: { groups: GroupAccuracy[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={groups} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={2}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="label" {...axisProps} interval={3} />
        <YAxis tickFormatter={gwTick} width={36} {...axisProps} />
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
  );
}

export function HorizonChart({ groups }: { groups: GroupAccuracy[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={groups} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={8}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="label" {...axisProps} />
        <YAxis tickFormatter={gwTick} width={36} {...axisProps} />
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
  );
}
