import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { HistogramRow } from "../types/api";
import { fmtOnOff, fmtPath, fmtUsd } from "../components/ui";
import { C, axisProps, tooltipProps } from "./theme";

/** Measured bitstrings (decoded by the backend). Green = optimal plan, blue = valid, red = invalid/rule-breaking. */
export function Histogram({ rows, accent = C.quantum, height = 240 }: { rows: HistogramRow[]; accent?: string; height?: number }) {
  const data = rows.map((r) => ({ ...r, pct: r.probability * 100 }));
  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 40 }}>
          <CartesianGrid stroke={C.grid} vertical={false} strokeDasharray="3 6" />
          <XAxis dataKey="bitstring" {...axisProps} angle={-50} textAnchor="end" interval={0} height={50} />
          <YAxis {...axisProps} unit="%" width={52} />
          <Tooltip
            {...tooltipProps}
            formatter={(v) => [`${Number(v).toFixed(2)}%`, "shots"]}
            labelFormatter={(label, payload) => {
              const r = payload?.[0]?.payload as HistogramRow | undefined;
              if (!r) return String(label);
              const plan = r.path
                ? `battery ${fmtPath(r.path)} MWh${r.commits ? ` · gas ${fmtOnOff(r.commits)}` : ""} · ${fmtUsd(r.objective)}`
                : "invalid (not exactly one state per hour)";
              return `${label} → ${plan}${r.optimal ? " · OPTIMAL" : r.path && !r.feasible ? " · breaks a rule" : ""}`;
            }}
          />
          <Bar dataKey="pct" radius={[5, 5, 0, 0]}>
            {data.map((r) => (
              <Cell key={r.bitstring} fill={r.optimal ? C.ok : r.feasible ? accent : C.bad} fillOpacity={r.optimal ? 1 : 0.7} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="num mt-1 flex gap-4 text-[0.7rem] text-dim">
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: C.ok }} />optimal plan</span>
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: accent }} />valid plan</span>
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: C.bad }} />invalid / breaks a rule</span>
        <span className="ml-auto">bitstring: qubit 0 is the rightmost bit (Qiskit order)</span>
      </div>
    </div>
  );
}
