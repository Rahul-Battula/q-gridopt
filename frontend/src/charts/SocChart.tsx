import { Area, AreaChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Scenario, SolverResult } from "../types/api";
import { C, axisProps, legendProps, tooltipProps } from "./theme";

const COLORS = [C.battery, C.quantum, C.noisy, C.classical, C.ibm];

/** Battery state of charge at the end of each period, one line per result. */
export function SocChart({ scenario, series, height = 220 }: {
  scenario: Scenario;
  series: { name: string; result: SolverResult }[];
  height?: number;
}) {
  const data = [
    { period: "Start", ...Object.fromEntries(series.map((s) => [s.name, scenario.battery.initial_soc])) },
    ...scenario.periods.map((p, i) => ({
      period: p.name,
      ...Object.fromEntries(series.map((s) => [s.name, s.result.evaluation?.soc_trajectory[i] ?? null])),
    })),
  ];
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 10, right: 12, left: -8, bottom: 0 }}>
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.name} id={`soc${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor={COLORS[i % COLORS.length]} stopOpacity={i === 0 ? 0.4 : 0.12} />
              <stop offset="1" stopColor={COLORS[i % COLORS.length]} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid stroke={C.grid} vertical={false} strokeDasharray="3 6" />
        <XAxis dataKey="period" {...axisProps} />
        <YAxis {...axisProps} unit=" MWh" width={70} domain={[0, scenario.battery.capacity]} />
        <ReferenceLine y={scenario.battery.capacity} stroke={C.line} strokeDasharray="2 5"
          label={{ value: "capacity", fill: C.axis, fontSize: 10, position: "insideTopRight" }} />
        <Tooltip {...tooltipProps} />
        <Legend {...legendProps} />
        {series.map((s, i) => (
          <Area key={s.name} dataKey={s.name} stroke={COLORS[i % COLORS.length]} strokeWidth={2.5}
            fill={`url(#soc${i})`} type="stepAfter"
            dot={{ r: 4, fill: C.panel, stroke: COLORS[i % COLORS.length], strokeWidth: 2 }} activeDot={{ r: 6 }} />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
