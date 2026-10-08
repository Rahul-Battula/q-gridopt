import { useState } from "react";
import { DepthChart, type DepthPoint } from "../charts/DepthChart";
import { Histogram } from "../charts/Histogram";
import { C } from "../charts/theme";
import type { SolverResult, Source } from "../types/api";
import { Provenance } from "./Provenance";
import { Panel, SourceBadge, fmtNum, fmtOnOff, fmtPath, fmtPct, fmtUsd } from "./ui";

const QUANTUM: Source[] = ["aer_statevector", "aer_noisy", "ibm_hardware"];
const ACCENT: Partial<Record<Source, string>> = { aer_statevector: C.quantum, aer_noisy: C.noisy, ibm_hardware: C.ibm };

const key = (r: SolverResult) => `${r.source}:${r.details.reps}`;

/** Ideal / noisy / hardware QAOA results for one tier, compared with random guessing. */
export function QuantumResults({ results }: { results: SolverResult[] }) {
  const q = results
    .filter((r) => QUANTUM.includes(r.source))
    .sort((a, b) => QUANTUM.indexOf(a.source) - QUANTUM.indexOf(b.source) || (a.details.reps ?? 0) - (b.details.reps ?? 0));
  const [selected, setSelected] = useState<string | null>(null);
  if (q.length === 0) return null;

  const first = q[0].details;
  const random = first.random_exact!;
  const reps = [...new Set(q.map((r) => r.details.reps ?? 0))].sort();
  const find = (s: Source, p: number) => q.find((r) => r.source === s && r.details.reps === p);
  const points: DepthPoint[] = reps.map((p) => ({
    p,
    ideal: find("aer_statevector", p)?.details.qaoa_exact?.p_optimal,
    noisy: find("aer_noisy", p)?.details.qaoa_sampled?.p_optimal,
    hardware: find("ibm_hardware", p)?.details.qaoa_sampled?.p_optimal,
  }));
  const shown = q.find((r) => key(r) === selected) ?? q[q.length - 1];

  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-[1.1fr_1fr]">
        <Panel tag="quality" title={`P(optimal plan) vs circuit depth · ${first.tier} (${first.num_qubits} qubits)`}>
          <DepthChart points={points} random={random.p_optimal} />
          <p className="mt-2 text-xs text-dim">
            Ideal = exact probabilities from the statevector (no shot noise). Noisy / hardware = fraction of measured shots.
          </p>
        </Panel>
        <Panel tag="honesty" title="How to read this">
          <ul className="space-y-2 text-sm text-dim">
            <li>
              <span className="text-ink">Optimum</span> {fmtUsd(first.optimal_objective)} comes from the classical exact
              enumerator; the worst feasible plan costs {fmtUsd(first.worst_feasible_objective)}.
            </li>
            <li>
              <span className="text-ink">Random guessing</span> picks the optimal plan with probability{" "}
              {fmtPct(random.p_optimal, 3)} and scores AR {random.approximation_ratio.toFixed(3)}.
            </li>
            <li>
              <span className="text-ink">Approximation ratio (AR)</span>: 1 = always the optimal plan, 0 = as bad as the worst
              feasible plan. Shots that are invalid or break a rule count as the worst plan.
            </li>
            <li className="border-l-2 border-warn pl-2 text-ink">
              No quantum advantage is claimed: exact classical enumeration solves every tier in milliseconds. This shows a
              correct QUBO/QAOA formulation benchmarked honestly against classical solvers.
            </li>
          </ul>
        </Panel>
      </div>

      <Panel tag="results" title="Per run">
        <div className="overflow-x-auto">
          <table className="num w-full text-sm">
            <thead>
              <tr className="label">
                <th className="pb-2 text-left font-normal">Source</th>
                <th className="pb-2 text-right font-normal">p</th>
                <th className="pb-2 text-right font-normal">2q gates on chip</th>
                <th className="pb-2 text-right font-normal">Shots</th>
                <th className="pb-2 text-right font-normal">P(optimal)</th>
                <th className="pb-2 text-right font-normal">P(valid)</th>
                <th className="pb-2 text-right font-normal">P(feasible)</th>
                <th className="pb-2 text-right font-normal">AR all shots</th>
                <th className="pb-2 text-right font-normal">AR feasible</th>
                <th className="pb-2 pl-6 text-left font-normal">Best plan sampled</th>
                <th className="pb-2 text-right font-normal" />
              </tr>
            </thead>
            <tbody>
              {q.map((r) => {
                const d = r.details;
                // ideal results report exact probabilities; sampled ones report measured frequencies
                const s = r.source === "aer_statevector" ? d.qaoa_exact! : d.qaoa_sampled!;
                const active = key(r) === key(shown);
                return (
                  <tr key={key(r)} className={`border-t border-line ${active ? "bg-panel-2" : ""}`}>
                    <td className="py-1.5"><SourceBadge source={r.source} jobId={r.provenance.job_id} /></td>
                    <td className="py-1.5 text-right">{d.reps}</td>
                    <td className="py-1.5 text-right">{fmtNum(d.circuit?.transpiled.two_qubit_gates)}</td>
                    <td className="py-1.5 text-right">{fmtNum(r.provenance.shots)}</td>
                    <td className="py-1.5 text-right text-ok">{fmtPct(s.p_optimal, 2)}</td>
                    <td className="py-1.5 text-right">{fmtPct(s.p_valid)}</td>
                    <td className="py-1.5 text-right">{fmtPct(s.p_feasible)}</td>
                    <td className="py-1.5 text-right">{s.approximation_ratio.toFixed(3)}</td>
                    <td className="py-1.5 text-right text-dim">{s.approximation_ratio_feasible?.toFixed(3) ?? "—"}</td>
                    <td className="py-1.5 pl-6">
                      {d.best_found ? `${fmtPath(d.best_found.path)}${d.best_found.commits ? ` gas ${fmtOnOff(d.best_found.commits)}` : ""} ${fmtUsd(d.best_found.objective)}` : "none feasible"}
                    </td>
                    <td className="py-1.5 text-right">
                      <button className="label hover:text-quantum" onClick={() => setSelected(key(r))}>
                        {active ? "▸ shown" : "show"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-[1.6fr_1fr]">
        <Panel tag="measurement" title={`Measured bitstrings · p=${shown.details.reps}`} right={<SourceBadge source={shown.source} jobId={shown.provenance.job_id} />}>
          {shown.details.histogram ? (
            <Histogram rows={shown.details.histogram} accent={ACCENT[shown.source]} />
          ) : (
            <div className="text-sm text-dim">No histogram stored for this result.</div>
          )}
        </Panel>
        <Panel tag="provenance" title="Where this came from">
          <Provenance result={shown} />
          {shown.details.circuit && (
            <div className="num mt-3 grid grid-cols-2 gap-2 border-t border-line pt-3 text-xs text-dim">
              <div>circuit depth on chip</div><div className="text-ink">{shown.details.circuit.transpiled.depth}</div>
              <div>2-qubit gates on chip</div><div className="text-ink">{shown.details.circuit.transpiled.two_qubit_gates}</div>
              <div>2-qubit gates (no routing)</div><div className="text-ink">{shown.details.circuit.logical?.two_qubit_gates ?? "—"}</div>
              <div>angles γ</div><div className="text-ink">{shown.details.gammas?.map((g) => g.toFixed(3)).join(", ")}</div>
              <div>angles β</div><div className="text-ink">{shown.details.betas?.map((b) => b.toFixed(3)).join(", ")}</div>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
