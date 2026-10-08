import { Link, useParams } from "react-router";
import { usePresets, useRun } from "../api/hooks";
import { ClassicalSummary } from "../components/ClassicalSummary";
import { QuantumResults } from "../components/QuantumResults";
import { ErrorBox, Loading, PageHeader, Panel, StatusLight } from "../components/ui";
import type { Run, Scenario } from "../types/api";

/** The scenario a run was made with: its custom scenario, or the preset it named. */
function useRunScenario(run: Run | undefined): Scenario | undefined {
  const presets = usePresets();
  if (!run) return undefined;
  const req = run.request as { scenario?: Scenario; preset?: string | null };
  if (req.scenario) return req.scenario;
  const id = req.preset ?? presets.data?.find((p) => p.default)?.id;
  return presets.data?.find((p) => p.id === id)?.scenario;
}

export function RunDetail() {
  const { runId } = useParams();
  const run = useRun(runId);
  const scenario = useRunScenario(run.data);
  if (run.isLoading) return <Loading />;
  if (run.error || !run.data) return <ErrorBox error={run.error ?? "run not found"} />;
  const r = run.data;

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <Link to="/runs" className="inline-flex items-center gap-2 rounded-md border border-line px-3.5 py-1.5 text-xs text-dim transition hover:border-line-bright hover:text-ink">← run log</Link>
        <PageHeader eyebrow="run details" title={r.kind.replace("_", " ")} accent={r.scenario_name} />
        <div className="flex flex-wrap items-center gap-4">
          <StatusLight status={r.status} progress={r.progress} />
          <span className="num text-xs text-faint">run {r.run_id}</span>
          {r.job_id && <span className="num text-xs text-ibm">IBM job {r.job_id}</span>}
        </div>
      </div>
      {r.error && <ErrorBox error={r.error} />}
      {r.kind === "classical" && scenario && <ClassicalSummary scenario={scenario} results={r.results} />}
      {r.kind !== "classical" && r.results.length > 0 && <QuantumResults results={r.results} />}
      <Panel tag="request" title="Request sent to the API">
        <pre className="num max-h-72 overflow-auto text-xs text-dim">{JSON.stringify(r.request, null, 2)}</pre>
      </Panel>
    </div>
  );
}
