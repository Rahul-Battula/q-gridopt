import { Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Scenario, SolverResult } from "../types/api";
import { C, axisProps, legendProps, tooltipProps } from "./theme";

const SERIES = [
  { key: "Solar", color: C.solar, id: "gSolar" },
  { key: "Wind", color: C.wind, id: "gWind" },
  { key: "Gas", color: C.gas, id: "gGas" },
  { key: "Battery out", color: C.battery, id: "gBatOut" },
  { key: "Unserved", color: C.unserved, id: "gUnserved" },
] as const;

/** Stacked supply per period (MW); battery charging drawn below zero; demand as a line. */
export function DispatchChart({ scenario, result, height = 280 }: { scenario: Scenario; result: SolverResult }
  & { height?: number }) {
  if (!result.schedule) return <div className="text-sm text-dim">No feasible schedule.</div>;
  const data = scenario.periods.map((p, i) => {
    const x = result.schedule!.periods[i];
    return {
      period: p.name,
      Solar: x.solar,
      Wind: x.wind,
      Gas: x.gas,
      "Battery out": x.discharge,
      Unserved: x.unserved,
      "Battery in": -x.charge,
      Demand: p.demand,
    };
  });
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} stackOffset="sign" margin={{ top: 10, right: 12, left: -8, bottom: 0 }} barCategoryGap="28%">
        <defs>
          {SERIES.map((s) => (
            <linearGradient key={s.id} id={s.id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor={s.color} stopOpacity={1} />
              <stop offset="1" stopColor={s.color} stopOpacity={0.9} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid stroke={C.grid} vertical={false} strokeDasharray="3 6" />
        <XAxis dataKey="period" {...axisProps} />
        <YAxis {...axisProps} unit=" MW" width={64} />
        <Tooltip {...tooltipProps} />
        <Legend {...legendProps} />
        <ReferenceLine y={0} stroke={C.line} />
        {SERIES.map((s) => (
          <Bar key={s.key} dataKey={s.key} stackId="s" fill={`url(#${s.id})`} radius={[4, 4, 4, 4]} />
        ))}
        <Bar dataKey="Battery in" stackId="s" fill={C.battery} fillOpacity={0.4} radius={[4, 4, 4, 4]} />
        <Line dataKey="Demand" stroke={C.demand} strokeWidth={2} strokeDasharray="5 4" type="linear"
          dot={{ r: 4, fill: C.panel, stroke: C.demand, strokeWidth: 2 }} activeDot={{ r: 6 }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
