import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { useRun } from "../api/hooks";
import { Pipeline } from "../components/Pipeline";
import { useCurrentScenario } from "../components/ScenarioPanel";
import { QuantumResults } from "../components/QuantumResults";
import { useScenario } from "../components/ScenarioContext";
import { Button, ErrorBox, Loading, PageHeader, Panel, Stat, StatusLight, fmtNum, fmtOnOff, fmtPath, fmtUsd } from "../components/ui";
import type { QuboPreview, Tier } from "../types/api";

const TIERS: { id: Tier; qubits: number; role: string; note: string; commitment?: boolean }[] = [
  { id: "Q3", qubits: 3, role: "Hardware target", note: "levels {0, 20} MWh · one bit per hour" },
  { id: "Q9", qubits: 9, role: "Main simulator result", note: "levels {0, 20, 40} MWh · one-hot" },
  { id: "Q18", qubits: 18, role: "Stress test (~3 min)", note: "levels 0–50 step 10 · one-hot" },
  { id: "Q3U", qubits: 12, role: "Unit commitment", note: "levels {0, 20} × gas on/off", commitment: true },
  { id: "Q9U", qubits: 18, role: "Unit commitment (~2 min)", note: "levels {0, 20, 40} × gas on/off", commitment: true },
];

/** One dot per qubit: a quick feel for the problem size. */
function QubitDots({ n, active }: { n: number; active: boolean }) {
  return (
    <div className="grid max-w-[5.5rem] grid-cols-6 gap-1">
      {Array.from({ length: n }, (_, i) => (
        <span key={i} className={`h-2 w-2 rounded-full ${active ? "bg-quantum" : "bg-faint"} transition`} style={{ opacity: active ? 0.45 + 0.55 * ((i % 6) / 5) : 0.6 }} />
      ))}
    </div>
  );
}

function QuboPanels({ qubo }: { qubo: QuboPreview }) {
  const terms = [...qubo.ising.terms].sort((a, b) => Math.abs(b.coef) - Math.abs(a.coef)).slice(0, 14);
  const cs = qubo.circuit_stats;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-5 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Qubits" value={qubo.num_qubits} tone="quantum" sub={`${qubo.encoding} encoding`} />
        <Stat label="Bitstrings" value={fmtNum(qubo.bitstrings_total)} sub={`${fmtNum(qubo.valid_bitstrings)} valid plans`} />
        <Stat label="Penalty A" value={fmtUsd(qubo.penalty)} sub={qubo.penalty_rule} />
        <Stat label="Ising terms" value={qubo.ising.num_terms} sub={`${qubo.ising.num_zz} ZZ couplings`} />
        <Stat label="Lowest energy" value={fmtUsd(qubo.ground_state.energy)} tone="ok"
          sub={`bitstring ${qubo.ground_state.bitstring}`} />
        <Stat label="= battery plan" value={fmtPath(qubo.ground_state.path)}
          sub={qubo.ground_state.commits ? `gas unit: ${fmtOnOff(qubo.ground_state.commits)}` : "MWh at end of each hour"} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <Panel tag="circuit" title={`QAOA circuit · p=${cs.reps}`} right={<span className="label">drawn by Qiskit</span>}>
          {qubo.circuit_svg ? (
            <div className="circuit-svg max-h-[440px] overflow-auto" dangerouslySetInnerHTML={{ __html: qubo.circuit_svg }} />
          ) : (
            <div className="text-sm text-dim">{qubo.num_qubits} qubits is too large to draw legibly; see the gate counts.</div>
          )}
        </Panel>
        <Panel tag="transpile" title={`Fitting the circuit to ${cs.backend}`}>
          <table className="num w-full text-sm">
            <thead>
              <tr className="label">
                <th className="pb-2 text-left font-normal" />
                <th className="pb-2 text-right font-normal">Native gates, no routing</th>
                <th className="pb-2 text-right font-normal">On the chip</th>
              </tr>
            </thead>
            <tbody>
              {([
                ["Depth", "depth"],
                ["2-qubit gates", "two_qubit_gates"],
                ["2-qubit depth", "two_qubit_depth"],
                ["All gates", "total_gates"],
                ["Qubits used", "active_qubits"],
              ] as const).map(([label, k]) => (
                <tr key={k} className="border-t border-line">
                  <td className="py-1.5 text-dim">{label}</td>
                  <td className="py-1.5 text-right">{fmtNum(cs.logical[k])}</td>
                  <td className="py-1.5 text-right text-quantum">{fmtNum(cs.transpiled[k])}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-dim">
            Every 2-qubit gate adds noise on real hardware. Extra gates on the chip are SWAPs needed because each qubit only
            talks to its neighbours.
          </p>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel tag="hamiltonian" title="Cost Hamiltonian H (largest terms)">
          <div className="num mb-2 text-xs text-dim">energy = ⟨H⟩ + offset {fmtNum(qubo.ising.offset, 1)} · qubit 0 is the rightmost Pauli</div>
          <table className="num w-full text-xs">
            <tbody>
              {terms.map((t) => (
                <tr key={t.pauli} className="border-t border-line">
                  <td className="py-1 text-right text-ink">{t.coef >= 0 ? "+" : ""}{fmtNum(t.coef, 2)}</td>
                  <td className="py-1 pl-4 tracking-[0.2em] text-quantum">{t.pauli}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel tag="qubo" title="QUBO as held by Qiskit Optimization">
          <pre className="num max-h-[360px] overflow-auto whitespace-pre-wrap text-xs text-dim">{qubo.qubo.text}</pre>
        </Panel>
      </div>
    </div>
  );
}

export function Quantum() {
  const { input } = useScenario();
  const scenario = useCurrentScenario();
  const [chosen, setTier] = useState<Tier>("Q3");
  // scenarios with unit commitment use the U tiers (gas on/off is part of the state), others the plain tiers
  const visibleTiers = TIERS.filter((t) => Boolean(t.commitment) === Boolean(scenario?.unit_commitment));
  const tier = visibleTiers.some((t) => t.id === chosen) ? chosen : visibleTiers[0].id;
  const [reps, setReps] = useState(3);
  const [shots, setShots] = useState(4096);
  const [noisy, setNoisy] = useState(true);
  const [runId, setRunId] = useState<string>();

  const qubo = useQuery({
    queryKey: ["qubo", input, tier],
    queryFn: () => api.quboPreview(input, tier, 1),
  });
  const start = useMutation({
    mutationFn: () => api.runSimulator(input, { tier, max_reps: reps, shots, noisy }),
    onSuccess: (r) => setRunId(r.run_id),
  });
  const run = useRun(runId);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="02 · quantum workflow" title="From battery plan to" accent="qubits and back"
        subtitle="QAOA (Quantum Approximate Optimization Algorithm) chooses the battery path; merit-order dispatch fills in solar, wind and gas for each hour. Every result is scored by the same evaluator as the classical solvers." />

      <Pipeline />

      <div>
        <div className="label mb-3">Problem size</div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {visibleTiers.map((t) => {
            const active = tier === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTier(t.id)}
                className={`rounded-lg border p-4 text-left transition duration-200 ${
                  active
                    ? "border-quantum/60 bg-quantum/[0.08] "
                    : "flat  hover:border-line-bright"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className={`display text-[1.7rem] font-semibold leading-none ${active ? "text-quantum" : "text-ink"}`}>{t.id}</div>
                    <div className="num mt-1.5 text-[0.7rem] text-dim">{t.qubits} qubits</div>
                  </div>
                  <QubitDots n={t.qubits} active={active} />
                </div>
                <div className="mt-3 text-sm font-medium text-ink">{t.role}</div>
                <div className="text-xs text-dim">{t.note}</div>
              </button>
            );
          })}
        </div>
      </div>

      <ErrorBox error={qubo.error} />
      {qubo.isLoading && <Loading what={`Building ${tier} QUBO`} />}
      {qubo.data && <QuboPanels qubo={qubo.data} />}

      <Panel tag="simulate" title={`Run QAOA on the Aer simulator · ${tier}`}
        right={run.data && <StatusLight status={run.data.status} progress={run.data.progress} />}>
        <div className="flex flex-wrap items-end gap-5">
          <label className="flex flex-col gap-1">
            <span className="label">Depth p = 1…</span>
            <select value={reps} onChange={(e) => setReps(Number(e.target.value))}>
              {[1, 2, 3].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="label">Shots</span>
            <input type="number" value={shots} min={100} step={1024} onChange={(e) => setShots(Number(e.target.value))} className="w-28" />
          </label>
          <label className="flex items-center gap-2 pb-1 text-sm text-dim">
            <input type="checkbox" checked={noisy} onChange={(e) => setNoisy(e.target.checked)} />
            also simulate IBM device noise (FakeFez)
          </label>
          <Button tone="primary" onClick={() => start.mutate()}
            disabled={start.isPending || run.data?.status === "running" || run.data?.status === "queued"}>
            Train &amp; sample
          </Button>
        </div>
        <ErrorBox error={start.error ?? run.error} />
        {run.data?.status === "failed" && <ErrorBox error={run.data.error} />}
      </Panel>

      {run.data && run.data.results.length > 0 && <QuantumResults results={run.data.results} />}
    </div>
  );
}
