import { useState } from "react";
import { Link } from "react-router";
import { useRuns } from "../api/hooks";
import { Chip, ErrorBox, Loading, PageHeader, Panel, SourceBadge, StatusLight, fmtUsd } from "../components/ui";

const KIND_LABEL = { classical: "Classical", quantum_simulator: "QAOA · simulator", quantum_ibm: "QAOA · IBM" };

export function Runs() {
  const [kind, setKind] = useState<string | undefined>(undefined);
  const runs = useRuns(kind);
  const FILTERS: { id: string | undefined; label: string }[] = [
    { id: undefined, label: "All runs" },
    { id: "classical", label: "Classical" },
    { id: "quantum_simulator", label: "QAOA · simulator" },
    { id: "quantum_ibm", label: "IBM hardware" },
  ];
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="04 · run log" title="Every run, with its" accent="provenance"
        subtitle="Each result records where it came from: source, backend, job id, shots and library versions. Simulator results can never be labelled as hardware." />
      <div className="inline-flex flex-wrap rounded-lg tabs p-1">
        {FILTERS.map((f) => (
          <button key={f.label} onClick={() => setKind(f.id)}
            className={`rounded-md px-4 py-1.5 text-xs font-medium transition ${kind === f.id ? "tab-active" : "text-dim hover:text-ink"}`}>
            {f.label}
          </button>
        ))}
      </div>
      <Panel>
        <ErrorBox error={runs.error} />
        {runs.isLoading && <Loading />}
        {runs.data?.length === 0 && <div className="text-sm text-dim">No runs yet.</div>}
        {runs.data && runs.data.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="label">
                <th className="pb-2 pr-6 text-left font-normal">Started (UTC)</th>
                <th className="pb-2 pr-6 text-left font-normal">Kind</th>
                <th className="pb-2 pr-6 text-left font-normal">Scenario</th>
                <th className="pb-2 pr-6 text-left font-normal">Status</th>
                <th className="pb-2 pr-6 text-left font-normal">Sources</th>
                <th className="pb-2 text-right font-normal">Best cost</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((r) => (
                <tr key={r.run_id} className="border-t border-line hover:bg-panel-2">
                  <td className="num whitespace-nowrap py-2 pr-6 text-dim">
                    <Link to={`/runs/${r.run_id}`} className="hover:text-quantum">{r.created_at.replace("T", " ").slice(0, 19)}</Link>
                  </td>
                  <td className="whitespace-nowrap py-2 pr-6"><Link to={`/runs/${r.run_id}`}><Chip tone={r.kind === "quantum_ibm" ? "ibm" : r.kind === "quantum_simulator" ? "quantum" : "ink"}>{KIND_LABEL[r.kind]}</Chip></Link></td>
                  <td className="whitespace-nowrap py-2 pr-6 text-dim">{r.scenario_name}</td>
                  <td className="whitespace-nowrap py-2 pr-6"><StatusLight status={r.status} /></td>
                  <td className="py-2">
                    <div className="flex flex-wrap gap-1">
                      {r.sources.map((s) => <SourceBadge key={s} source={s} jobId={s === "ibm_hardware" ? r.job_id : null} />)}
                    </div>
                  </td>
                  <td className="num py-2 text-right">{fmtUsd(r.best_objective)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
