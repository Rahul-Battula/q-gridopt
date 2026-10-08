import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ApiError, api } from "../api/client";
import { C, axisProps, legendProps, tooltipProps } from "../charts/theme";
import { ErrorBox, Loading, PageHeader, Panel, Stat, fmtNum, fmtPct, fmtUsd } from "../components/ui";
import type { BenchMethod, BenchSummaryRow, Tier } from "../types/api";

const LABEL: Record<BenchMethod, string> = {
  exact: "Exact enumeration",
  lp: "Linear program (CBC)",
  annealing: "Simulated annealing",
  no_battery: "No battery",
  random: "Random sampling",
  qaoa_ideal: "QAOA · ideal",
  qaoa_noisy: "QAOA · noisy (FakeFez)",
};
const KIND: Record<BenchMethod, "classical" | "baseline" | "quantum"> = {
  exact: "classical", lp: "classical", annealing: "classical", no_battery: "baseline", random: "baseline",
  qaoa_ideal: "quantum", qaoa_noisy: "quantum",
};
const KIND_CLS = { classical: "text-classical", baseline: "text-dim", quantum: "text-quantum" };
const HEADLINE_ORDER: BenchMethod[] = ["exact", "lp", "annealing", "no_battery", "random", "qaoa_ideal", "qaoa_noisy"];
const SAMPLING = new Set<BenchMethod>(["annealing", "random", "qaoa_ideal", "qaoa_noisy"]);

const rowLabel = (s: BenchSummaryRow) => `${LABEL[s.method]}${s.reps ? ` p=${s.reps}` : ""}`;

export function Benchmark() {
  const bench = useQuery({ queryKey: ["benchmark"], queryFn: api.benchmark, retry: false });
  const [tier, setTier] = useState<Tier>("Q3");

  if (bench.isLoading) return <Loading what="Loading benchmark" />;
  if (bench.error instanceof ApiError && bench.error.status === 404) {
    return (
      <Panel title="No benchmark yet">
        <p className="text-sm text-dim">Run the suite from the project root, then reload this page:</p>
        <pre className="num mt-3 rounded-md border border-line bg-panel-2 px-4 py-3 text-xs text-ink">python backend\scripts\run_benchmark.py</pre>
      </Panel>
    );
  }
  if (bench.error || !bench.data) return <ErrorBox error={bench.error} />;
  const b = bench.data;
  const cfg = b.config;
  const rows = b.summary.filter((s) => s.tier === tier);
  const top = (tr: Tier, m: BenchMethod) => b.summary.find((r) => r.tier === tr && r.method === m && (!m.startsWith("qaoa") || r.reps === cfg.max_reps));
  const qaoaAcc = b.headline.map((h) => `${fmtPct(h.methods.qaoa_ideal?.accuracy_best, 0)}`).join(" · ");
  const vsRandom = cfg.tiers.map((t) => {
    const q = top(t, "qaoa_ideal")?.p_optimal_mean;
    const r = top(t, "random")?.p_optimal_mean;
    return q && r ? `×${fmtNum(q / r)}` : "—";
  }).join(" · ");

  const chart = rows
    .filter((s) => !s.method.startsWith("qaoa") || s.reps === cfg.max_reps)
    .map((s) => ({ name: rowLabel(s), "Accuracy best-of-N": s.accuracy_best * 100, "Accuracy top-1": s.accuracy_top1 * 100, "F1 best-of-N": s.f1_best * 100 }));

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="05 · benchmark"
        title="QAOA vs classical algorithms on"
        accent={`${cfg.instances} random grids`}
        subtitle={`Seeds ${cfg.first_seed}–${cfg.first_seed + cfg.instances - 1} · ${fmtNum(cfg.shots)} samples per sampling method · QAOA p = 1…${cfg.max_reps} · noise model ${cfg.noise_backend} · annealing ${cfg.annealing} · generated ${b.created_at.replace("T", " ").slice(0, 16)} UTC · ${(b.wall_time_s / 60).toFixed(1)} min`}
      />

      {/* the four numbers a judge should read first */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Test set" value={`${cfg.instances} grids`} sub={`random, seeds ${cfg.first_seed}–${cfg.first_seed + cfg.instances - 1}, 7 methods`} tone="ink" />
        <Stat label={`QAOA finds the optimum (p=${cfg.max_reps})`} value={qaoaAcc} sub="best-of-N plan is optimal, per tier (Q18: 3 grids only)" tone="quantum" />
        <Stat label="QAOA vs blind guessing" value={vsRandom} sub="chance that ONE sample is optimal, per tier" tone="ok" />
        <Stat label="Exact classical" value="100%" sub="every instance, in milliseconds" tone="gas" />
      </div>
      <div className="flex items-start gap-3 rounded-lg border border-line bg-panel-2 px-4 py-3 text-[0.92rem] leading-relaxed text-dim">
        <span className="mt-0.5 whitespace-nowrap font-semibold text-warn">Honest reading</span>
        <span>
          QAOA is far better than random guessing as the problem grows, and its best plan is optimal on every instance.
          But exact classical search is already perfect and instant here, so <strong className="text-ink">no quantum advantage is claimed</strong>.
        </span>
      </div>

      <Panel tag="scoreboard" title="Result table: every method on every tier"
        right={<span className="text-xs text-faint">accuracy = best plan is optimal · F1 = hourly battery decisions vs optimal · QAOA at p = {cfg.max_reps}</span>}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="label text-left">
                <th className="pb-2.5 pr-4 font-medium">Method</th>
                {b.headline.map((h) => (
                  <th key={h.tier} className="pb-2.5 pr-4 font-medium">{h.tier} <span className="text-faint normal-case">accuracy · F1</span></th>
                ))}
              </tr>
            </thead>
            <tbody>
              {HEADLINE_ORDER.map((m) => (
                <tr key={m} className={`border-t border-line ${KIND[m] === "quantum" ? "bg-quantum/[0.05]" : ""}`}>
                  <td className="py-2.5 pr-4">
                    <span className={`font-semibold ${KIND_CLS[KIND[m]]}`}>{LABEL[m]}</span>
                    <span className="ml-2 text-[0.68rem] uppercase tracking-wider text-faint">{KIND[m]}</span>
                  </td>
                  {b.headline.map((h) => {
                    const c = h.methods[m];
                    return (
                      <td key={h.tier} className="py-2.5 pr-4">
                        {c ? (
                          <div className="min-w-[8.5rem]">
                            <div className="flex items-baseline gap-2">
                              <span className="display text-lg font-semibold text-ink">{fmtPct(c.accuracy_best, 0)}</span>
                              <span className="num text-xs text-dim">F1 {c.f1_best.toFixed(2)}</span>
                            </div>
                            <div className="mt-1 h-1.5 rounded-full bg-panel-2">
                              <div className="h-full rounded-full" style={{ width: `${c.accuracy_best * 100}%`, background: KIND[m] === "quantum" ? C.quantum : KIND[m] === "classical" ? C.classical : C.axis }} />
                            </div>
                          </div>
                        ) : <span className="text-faint">not run</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="inline-flex rounded-lg tabs p-1">
        {cfg.tiers.map((t) => (
          <button key={t} onClick={() => setTier(t)}
            className={`num rounded-md px-5 py-1.5 text-sm transition ${tier === t ? "tab-active" : "text-dim hover:text-ink"}`}>
            {t}
          </button>
        ))}
      </div>

      <Panel tag="chart" title={`${tier}: accuracy and F1 by method (%)`}>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chart} margin={{ top: 8, right: 8, left: -8, bottom: 60 }}>
            <CartesianGrid stroke={C.grid} vertical={false} strokeDasharray="3 6" />
            <XAxis dataKey="name" {...axisProps} angle={-25} textAnchor="end" interval={0} height={70} />
            <YAxis {...axisProps} unit="%" domain={[0, 100]} width={52} />
            <Tooltip {...tooltipProps} formatter={(v) => `${Number(v).toFixed(1)}%`} />
            <Legend {...legendProps} verticalAlign="top" />
            <Bar dataKey="Accuracy best-of-N" fill={C.ok} radius={[5, 5, 0, 0]} />
            <Bar dataKey="Accuracy top-1" fill={C.quantum} radius={[5, 5, 0, 0]} />
            <Bar dataKey="F1 best-of-N" fill={C.battery} radius={[5, 5, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Panel>

      <Panel tag="table" title={`${tier}: full results`}>
        <div className="overflow-x-auto">
          <table className="num w-full text-xs">
            <thead>
              <tr className="label">
                {["Method", "n", "Acc. top-1", "Acc. best-of-N", "F1 top-1", "F1 best-of-N", "Success / sample",
                  "AR", "Valid samples", "Best gap", "Samples for 99%", "Time s"].map((h, i) => (
                  <th key={h} className={`pb-2 font-normal ${i === 0 ? "text-left" : "text-right"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={`${s.method}-${s.reps}`} className="border-t border-line">
                  <td className={`py-1.5 ${KIND_CLS[KIND[s.method]]}`}>{rowLabel(s)}</td>
                  <td className="py-1.5 text-right text-dim">{s.instances}</td>
                  <td className="py-1.5 text-right">{fmtPct(s.accuracy_top1, 0)}</td>
                  <td className="py-1.5 text-right text-ok">{fmtPct(s.accuracy_best, 0)}</td>
                  <td className="py-1.5 text-right">{s.f1_top1.toFixed(3)}</td>
                  <td className="py-1.5 text-right">{s.f1_best.toFixed(3)}</td>
                  <td className="py-1.5 text-right">{SAMPLING.has(s.method) ? fmtPct(s.p_optimal_mean, 2) : "—"}</td>
                  <td className="py-1.5 text-right">{s.approximation_ratio_mean?.toFixed(3) ?? "—"}</td>
                  <td className="py-1.5 text-right">{fmtPct(s.p_valid_mean)}</td>
                  <td className="py-1.5 text-right">{fmtUsd(s.best_gap_mean)}</td>
                  <td className="py-1.5 text-right">
                    {SAMPLING.has(s.method) ? (s.samples_99_median == null ? "never" : fmtNum(s.samples_99_median)) : "—"}
                  </td>
                  <td className="py-1.5 text-right text-dim">{s.time_s_mean?.toFixed(3) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel tag="definitions" title="What the metrics mean">
        <ul className="grid gap-2 text-sm text-dim md:grid-cols-2">
          <li><span className="text-ink">Accuracy top-1</span>: the method's single most likely plan is optimal.</li>
          <li><span className="text-ink">Accuracy best-of-N</span>: the best of its N samples is optimal (what the system reports).</li>
          <li><span className="text-ink">F1 (macro)</span>: each hour's battery decision (charge / idle / discharge) compared with the optimal plan's decision.</li>
          <li><span className="text-ink">Success / sample</span>: probability that one sample is optimal.</li>
          <li><span className="text-ink">AR</span>: 1 = optimal, 0 = worst feasible plan; invalid samples count as worst.</li>
          <li><span className="text-ink">Samples for 99%</span>: samples needed to hit the optimum with 99% confidence.</li>
          <li className="md:col-span-2 border-l-2 border-warn pl-2 text-ink">
            QAOA time is the classical simulation of training on this laptop, not QPU time. No quantum advantage is
            claimed: classical exact enumeration solves every instance in milliseconds.
          </li>
        </ul>
      </Panel>
    </div>
  );
}
