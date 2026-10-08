import { Link } from "react-router";
import { useRun } from "../api/hooks";
import { C } from "../charts/theme";
import type { RunSummary } from "../types/api";
import { IconChip, IconShield } from "./icons";
import { Chip, SourceBadge, fmtNum, fmtPct, fmtUsd } from "./ui";

function Bar({ label, value, color, max }: { label: string; value: number; color: string; max: number }) {
  const width = Math.max((value / max) * 100, 1.5);
  return (
    <div className="grid grid-cols-[6.5rem_1fr_3.6rem] items-center gap-3">
      <span className="text-[0.72rem] text-dim">{label}</span>
      <div className="h-3 overflow-hidden rounded-md bg-panel-2">
        <div className="h-full rounded-md transition-[width] duration-1000 ease-out"
          style={{ width: `${width}%`, background: color }} />
      </div>
      <span className="num text-right text-sm text-ink">{fmtPct(value, value < 0.1 || value > 0.99 ? 1 : 0)}</span>
    </div>
  );
}

/** The latest REAL IBM hardware result next to the ideal simulator and random guessing. */
export function HardwareHero({ latest }: { latest: RunSummary }) {
  const run = useRun(latest.run_id);
  const results = (run.data?.results ?? []).filter((r) => r.source === "ibm_hardware").sort((a, b) => (a.details.reps ?? 0) - (b.details.reps ?? 0));
  if (results.length === 0) return null;
  const first = results[0];
  const d0 = first.details;
  const usage = d0.qpu_usage_seconds_whole_job;
  const best = d0.best_found;
  const bestAtP3 = results[results.length - 1].details.qaoa_sampled?.p_optimal ?? 0;

  return (
    <section className="card  relative overflow-hidden rounded-lg">
      
      <div className="relative grid gap-8 p-6 sm:p-8 xl:grid-cols-[1fr_1.15fr]">
        <div className="flex flex-col">
          <div className="flex items-center gap-2 text-ibm">
            <span className="grid h-9 w-9 place-items-center rounded-md border border-ibm/40 bg-ibm/15"><IconChip size={19} /></span>
            <span className="label text-ibm">latest real quantum run</span>
          </div>
          <h2 className="display mt-4 text-[1.9rem] font-semibold leading-[1.15]">
            <span className="text-quantum">{fmtPct(bestAtP3, 0)}</span> of measurements found the optimal battery plan
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-dim">
            on <span className="num text-ink">{first.provenance.backend}</span>, a real {d0.circuit?.transpiled.active_qubits ?? 3}-qubit
            circuit with {fmtNum(d0.circuit?.transpiled.two_qubit_gates)} two-qubit gates at p = {results[results.length - 1].details.reps}.
            Random guessing would find it {fmtPct(d0.random_exact?.p_optimal, 1)} of the time.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <SourceBadge source="ibm_hardware" jobId={first.provenance.job_id} />
            <Chip tone="ink">{fmtNum(first.provenance.shots)} shots / circuit</Chip>
            {usage != null && <Chip tone="ok" dot>{usage} s of QPU time</Chip>}
            {best && <Chip tone="ok">best plan {fmtUsd(best.objective)}</Chip>}
          </div>
          <div className="mt-auto flex items-start gap-2.5 pt-6 text-xs leading-relaxed text-dim">
            <IconShield size={16} className="mt-0.5 shrink-0 text-ok" />
            <span>
              Honest reading: real noise lowers the success rate a little compared with the ideal simulator, and a classical
              computer still solves this tiny problem exactly in milliseconds. No quantum advantage is claimed.{" "}
              <Link to={`/runs/${latest.run_id}`} className="text-quantum hover:underline">Full details →</Link>
            </span>
          </div>
        </div>

        <div className="space-y-5 rounded-lg border border-line bg-panel-2 p-5">
          <div className="flex items-center justify-between">
            <span className="label">Probability of the optimal plan</span>
            <div className="flex gap-3 text-[0.68rem] text-dim">
              <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: C.quantum }} />ideal</span>
              <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: C.ibm }} />real QPU</span>
              <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: C.axis }} />random</span>
            </div>
          </div>
          {results.map((r) => {
            const d = r.details;
            return (
              <div key={d.reps} className="space-y-2">
                <div className="flex items-center gap-2 text-sm">
                  <span className="display font-semibold text-ink">p = {d.reps}</span>
                  <span className="num text-[0.68rem] text-faint">{fmtNum(d.circuit?.transpiled.two_qubit_gates)} two-qubit gates</span>
                </div>
                <Bar label="Ideal simulator" value={d.ideal_exact?.p_optimal ?? 0} color={C.quantum} max={1} />
                <Bar label="Real QPU" value={d.qaoa_sampled?.p_optimal ?? 0} color={C.ibm} max={1} />
                <Bar label="Random guess" value={d.random_exact?.p_optimal ?? 0} color={C.axis} max={1} />
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
