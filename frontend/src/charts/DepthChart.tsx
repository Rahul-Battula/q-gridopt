import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { C, axisProps, legendProps, tooltipProps } from "./theme";

export interface DepthPoint {
  p: number;
  ideal?: number;
  noisy?: number;
  hardware?: number;
}

/** P(optimal) vs QAOA depth p, with uniform random guessing as a reference line. */
export function DepthChart({ points, random, height = 220, metric = "P(optimal)" }: {
  points: DepthPoint[];
  random: number;
  height?: number;
  metric?: string;
}) {
  const data = points.map((pt) => ({
    p: `p=${pt.p}`,
    ideal: pt.ideal != null ? pt.ideal * 100 : undefined,
    noisy: pt.noisy != null ? pt.noisy * 100 : undefined,
    hardware: pt.hardware != null ? pt.hardware * 100 : undefined,
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
        <CartesianGrid stroke={C.grid} vertical={false} strokeDasharray="3 6" />
        <XAxis dataKey="p" {...axisProps} />
        <YAxis {...axisProps} unit="%" width={52} domain={[0, 100]} />
        <Tooltip {...tooltipProps} formatter={(v, name) => [`${Number(v).toFixed(2)}%`, `${metric} · ${name}`]} />
        <Legend {...legendProps} />
        <ReferenceLine y={random * 100} stroke={C.axis} strokeDasharray="4 4"
          label={{ value: `random guess ${(random * 100).toFixed(2)}%`, fill: C.axis, fontSize: 10, position: "insideBottomRight" }} />
        <Line dataKey="ideal" name="Aer ideal" stroke={C.quantum} strokeWidth={2.5}
          dot={{ r: 4.5, fill: C.panel, stroke: C.quantum, strokeWidth: 2 }} activeDot={{ r: 6 }} connectNulls />
        <Line dataKey="noisy" name="Aer noisy" stroke={C.noisy} strokeWidth={2.5}
          dot={{ r: 4.5, fill: C.panel, stroke: C.noisy, strokeWidth: 2 }} activeDot={{ r: 6 }} connectNulls />
        <Line dataKey="hardware" name="IBM QPU" stroke={C.ibm} strokeWidth={3}
          dot={{ r: 5, fill: C.ibm, stroke: C.panel, strokeWidth: 2 }} activeDot={{ r: 7 }} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  );
}
