import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ClassicalSummary } from "../components/ClassicalSummary";
import { useScenario } from "../components/ScenarioContext";
import { ScenarioPanel, useCurrentScenario } from "../components/ScenarioPanel";
import { Button, ErrorBox, Loading, PageHeader, Skeleton } from "../components/ui";
import type { Run, Scenario } from "../types/api";

export function Overview() {
  const { input } = useScenario();
  const scenario = useCurrentScenario();
  const [done, setDone] = useState<{ run: Run; scenario: Scenario; input: typeof input } | null>(null);
  const solve = useMutation({
    mutationFn: async () => ({ run: await api.runClassical(input), scenario: scenario!, input }),
    onSuccess: setDone,
  });

  // classical solvers take milliseconds: solve on load and when the preset changes. Hand edits of the
  // values do not re-solve on every keystroke (each solve is a run in the log); the button lights up instead.
  const { presetId, custom } = useScenario();
  useEffect(() => {
    if (!scenario || custom) return;
    const timer = setTimeout(() => solve.mutate(), 250);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetId, Boolean(scenario), Boolean(custom)]);
  const stale = Boolean(done) && JSON.stringify(input) !== JSON.stringify(done?.input);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="01 · grid & classical baselines"
        title="Three hours, one battery,"
        accent="one decision"
        subtitle="When should the battery charge and discharge? The classical solvers below give the true optimum that every quantum result is measured against."
        actions={
          <Button tone="primary" onClick={() => solve.mutate()} disabled={solve.isPending || !scenario}>
            {solve.isPending ? "Solving…" : stale ? "Values changed · re-run" : "Re-run solvers"}
          </Button>
        }
      />

      <ScenarioPanel />
      <ErrorBox error={solve.error} />

      {solve.isPending && !done && (
        <div className="space-y-4">
          <Loading what="Solving LP + exact enumeration" />
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-6">
            {Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-24" />)}
          </div>
          <Skeleton className="h-[26rem]" />
        </div>
      )}
      {done && (
        <div className={`space-y-6 transition-opacity duration-200 ${solve.isPending ? "opacity-60" : "opacity-100"}`}>
          <div className="num text-xs text-faint">
            run {done.run.run_id.slice(0, 8)} · {done.run.scenario_name} · {done.run.created_at.replace("T", " ").slice(0, 19)} UTC
          </div>
          <ClassicalSummary scenario={done.scenario} results={done.run.results} />
        </div>
      )}
    </div>
  );
}
