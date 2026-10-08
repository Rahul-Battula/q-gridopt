import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import { useHealth, useRun, useRuns } from "../api/hooks";
import { QuantumResults } from "../components/QuantumResults";
import { useScenario } from "../components/ScenarioContext";
import { useCurrentScenario } from "../components/ScenarioPanel";
import { HardwareHero } from "../components/HardwareHero";
import { Button, ErrorBox, PageHeader, Panel, SourceBadge, StatusLight, fmtUsd } from "../components/ui";
import type { Tier } from "../types/api";

export function Hardware() {
  const { input } = useScenario();
  const scenario = useCurrentScenario();
  const unsupported = Boolean(scenario?.unit_commitment); // Q3U / Q9U circuits are far too deep for hardware
  const health = useHealth();
  const configured = health.data?.ibm_credentials_configured ?? false;
  const [tier, setTier] = useState<Tier>("Q3");
  const [reps, setReps] = useState(3);
  const [shots, setShots] = useState(4096);
  const [backend, setBackend] = useState("");
  const [approved, setApproved] = useState(false);
  const [runId, setRunId] = useState<string>();
  const run = useRun(runId);
  const realRuns = (useRuns("quantum_ibm").data ?? []).filter((r) => r.sources.includes("ibm_hardware"));

  const start = useMutation({
    mutationFn: (mode: "local" | "real") =>
      api.runIbm(input, {
        tier,
        max_reps: reps,
        shots,
        backend: mode === "local" ? "FakeFez" : backend.trim() || null,
        confirm: mode === "real" && approved,
      }),
    onSuccess: (r) => {
      setRunId(r.run_id);
      setApproved(false); // approval covers exactly one submission
    },
  });
  const busy = unsupported || start.isPending || ["queued", "running", "submitted"].includes(run.data?.status ?? "");

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="03 · IBM Quantum hardware" title="Same circuit," accent="real qubits"
        subtitle="The angles trained on the simulator are kept fixed; the circuit is transpiled for the chosen IBM backend and run once in job mode (Open Plan: no sessions). Dynamical decoupling and Pauli twirling are enabled on real hardware." />

      {realRuns[0] && <HardwareHero latest={realRuns[0]} />}

      {unsupported && (
        <div className="rounded-lg border border-warn/40 bg-warn/10 px-5 py-4 text-sm leading-relaxed text-warn">
          The selected scenario uses unit commitment. Its circuits (12+ qubits, 640+ two-qubit gates) are too deep for
          current hardware, so they run on the simulator only (Quantum workflow, tier Q3U or Q9U). Choose Scenario A or
          B on the first page to use this page.
        </div>
      )}

      <Panel tag="setup" title="Run settings">
        <div className="flex flex-wrap items-end gap-5">
          <label className="flex flex-col gap-1">
            <span className="label">Tier</span>
            <select value={tier} onChange={(e) => setTier(e.target.value as Tier)}>
              <option value="Q3">Q3 · 3 qubits (recommended)</option>
              <option value="Q9">Q9 · 9 qubits (stretch)</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="label">Depth p = 1…</span>
            <select value={reps} onChange={(e) => setReps(Number(e.target.value))}>
              {[1, 2, 3].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="label">Shots per circuit</span>
            <input type="number" value={shots} min={100} step={1024} onChange={(e) => setShots(Number(e.target.value))} className="w-28" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="label">IBM backend (blank = least busy)</span>
            <input type="text" value={backend} placeholder="e.g. ibm_fez" onChange={(e) => setBackend(e.target.value)} className="w-48" />
          </label>
        </div>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel tag="rehearsal" title="Local test · no QPU time">
          <p className="mb-4 text-sm text-dim">
            Runs the exact hardware code path on this computer with the FakeFez model of an IBM Heron chip
            (qiskit-ibm-runtime local testing mode). Results are labelled <span className="text-noisy">Qiskit Aer · noisy</span>,
            never as hardware.
          </p>
          <Button onClick={() => start.mutate("local")} disabled={busy}>Run local test</Button>
        </Panel>

        <Panel tag="qpu" title="Real IBM Quantum run · uses QPU time">
          {!configured ? (
            <div className="space-y-2 text-sm text-dim">
              <p className="text-warn">IBM credentials are not configured on the backend.</p>
              <p>Put your API key and instance CRN in <span className="num text-ink">backend\.env</span>, then check them with:</p>
              <pre className="num bg-console px-3 py-2 text-xs text-ink">python backend\scripts\check_ibm.py</pre>
            </div>
          ) : (
            <div className="space-y-3 text-sm">
              <p className="text-dim">
                Each job is capped at <span className="num text-ink">60 s</span> of QPU time (IBM cancels it beyond
                that), out of the Open Plan's 600 s per 28 days. Check what is left with:
              </p>
              <pre className="num bg-console px-3 py-2 text-xs text-ink">python backend\scripts\check_ibm.py</pre>
              <label className="flex items-start gap-2 text-dim">
                <input type="checkbox" className="mt-1" checked={approved} onChange={(e) => setApproved(e.target.checked)} />
                <span>
                  I approve using QPU time from my IBM Quantum allowance for one {tier} run (p = 1…{reps}, {shots} shots
                  each).
                </span>
              </label>
              <Button tone="danger" onClick={() => start.mutate("real")} disabled={!approved || busy}>
                Submit to IBM hardware
              </Button>
            </div>
          )}
        </Panel>
      </div>

      <Panel tag="history" title="Previous real hardware runs">
        {realRuns.length === 0 ? (
          <div className="text-sm text-dim">No real hardware run yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="label">
                <th className="pb-2 text-left font-normal">Started (UTC)</th>
                <th className="pb-2 text-left font-normal">Scenario</th>
                <th className="pb-2 text-left font-normal">Source</th>
                <th className="pb-2 text-right font-normal">Best cost</th>
              </tr>
            </thead>
            <tbody>
              {realRuns.map((r) => (
                <tr key={r.run_id} className="border-t border-line hover:bg-panel-2">
                  <td className="num py-2">
                    <Link to={`/runs/${r.run_id}`} className="text-dim hover:text-quantum">{r.created_at.replace("T", " ").slice(0, 19)}</Link>
                  </td>
                  <td className="py-2 text-dim">{r.scenario_name}</td>
                  <td className="py-2"><SourceBadge source="ibm_hardware" jobId={r.job_id} /></td>
                  <td className="num py-2 text-right">{fmtUsd(r.best_objective)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <ErrorBox error={start.error ?? run.error} />
      {run.data && (
        <Panel tag="status" title="Current run" right={<StatusLight status={run.data.status} progress={run.data.progress} />}>
          <div className="num grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs text-dim">
            <span>run id</span><span className="text-ink">{run.data.run_id}</span>
            <span>IBM job id</span><span className="text-ink">{run.data.job_id ?? "—"}</span>
          </div>
          {run.data.status === "failed" && <div className="mt-3"><ErrorBox error={run.data.error} /></div>}
          {run.data.status === "submitted" && (
            <p className="mt-3 text-xs text-dim">
              Waiting in the IBM queue. You can close this page: the run log will pick the result up when the job finishes.
            </p>
          )}
        </Panel>
      )}
      {run.data && run.data.results.length > 0 && <QuantumResults results={run.data.results} />}
    </div>
  );
}
