import { DispatchChart } from "../charts/DispatchChart";
import { SocChart } from "../charts/SocChart";
import type { Scenario, SolverResult } from "../types/api";
import { GridFlow } from "./GridFlow";
import { IconBattery, IconBolt, IconCheck, IconFlame, IconSun } from "./icons";
import { Panel, SourceBadge, Stat, fmtNum, fmtOnOff, fmtPath, fmtPct, fmtUsd } from "./ui";

const COST_ROWS = [
  ["Gas fuel", "gas_cost"],
  ["CO₂", "co2_cost"],
  ["Curtailment", "curtailment_cost"],
  ["Battery wear", "wear_cost"],
  ["Unserved demand", "unserved_cost"],
] as const;
const EXTRA_COST_ROWS = [
  ["Gas start-up", "startup_cost"],
  ["Reserve shortfall", "reserve_cost"],
] as const;

/** LP optimum vs no-battery baseline, plus the exact enumerator per quantum tier. */
export function ClassicalSummary({ scenario, results }: { scenario: Scenario; results: SolverResult[] }) {
  const lp = results.find((r) => r.source === "classical_lp");
  const nb = results.find((r) => r.source === "classical_no_battery");
  const exact = results.filter((r) => r.source === "classical_exact");
  if (!lp?.evaluation || !nb?.evaluation) return null;
  const L = lp.evaluation;
  const N = nb.evaluation;
  const saving = N.objective - L.objective;
  const costRows = [...COST_ROWS, ...EXTRA_COST_ROWS.filter(([, key]) => (L[key] ?? 0) !== 0 || (N[key] ?? 0) !== 0)];
  const extended = Boolean(scenario.unit_commitment || scenario.uncertainty || scenario.reserve);

  return (
    <div className="stagger space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Optimal cost" value={fmtUsd(L.objective)} tone="ok" sub="best plan, with battery" icon={<IconCheck size={16} />} />
        <Stat label="No battery" value={fmtUsd(N.objective)} tone="gas" sub="greedy merit order" icon={<IconFlame size={16} />} />
        <Stat label="Battery saves" value={fmtUsd(saving)} tone="battery" sub={fmtPct(saving / N.objective) + " of cost"} icon={<IconBattery size={16} />} />
        <Stat label="CO₂" value={`${fmtNum(L.co2_tonnes, 1)} t`} tone="wind" sub={`vs ${fmtNum(N.co2_tonnes, 1)} t without battery`} icon={<IconBolt size={16} />} />
        <Stat label="Curtailed" value={`${fmtNum(L.curtailment_mwh)} MWh`} tone="warn" sub={`vs ${fmtNum(N.curtailment_mwh)} MWh`} icon={<IconSun size={16} />} />
        <Stat label="Renewables used" value={fmtPct(L.renewable_utilization)} tone="solar" sub={`vs ${fmtPct(N.renewable_utilization)}`} icon={<IconSun size={16} />} />
      </div>

      <GridFlow scenario={scenario} variants={[
        { id: "opt", label: "Optimal plan", result: lp },
        { id: "nb", label: "No battery", result: nb },
      ]} />

      {extended && (
        <div className="grid grid-cols-2 gap-5 md:grid-cols-4">
          {scenario.unit_commitment && (
            <Stat label="Gas start-ups" value={`${L.startups ?? 0}`} sub={`optimal plan · ${fmtUsd(L.startup_cost)} · ${N.startups ?? 0} without battery`} />
          )}
          {scenario.reserve && (
            <Stat label="Reserve missing" value={`${fmtNum(L.reserve_shortfall_mwh ?? 0, 1)} MWh`}
              sub={`${fmtUsd(L.reserve_cost)} penalty · ${fmtNum(N.reserve_shortfall_mwh ?? 0, 1)} MWh without battery`} />
          )}
          {scenario.uncertainty && L.worst_case_objective != null && (
            <Stat label="Worst forecast case" value={fmtUsd(L.worst_case_objective)}
              sub={`expected cost ${fmtUsd(L.objective)}`} />
          )}
        </div>
      )}

      {(L.cases?.length ?? 0) > 0 && (
        <Panel tag="uncertainty" title="Forecast cases · costs below are probability-weighted expectations">
          <table className="num w-full text-sm">
            <thead>
              <tr className="label">
                <th className="pb-2 text-left font-normal">Case</th>
                <th className="pb-2 text-right font-normal">Probability</th>
                <th className="pb-2 text-right font-normal">Cost, optimal plan</th>
                <th className="pb-2 text-right font-normal">Cost, no battery</th>
                <th className="pb-2 text-right font-normal">Unserved MWh (optimal)</th>
              </tr>
            </thead>
            <tbody>
              {L.cases!.map((c, i) => (
                <tr key={c.name} className="border-t border-line">
                  <td className="py-1.5 text-dim">{c.name}</td>
                  <td className="py-1.5 text-right">{fmtPct(c.probability)}</td>
                  <td className="py-1.5 text-right">{fmtUsd(c.objective)}</td>
                  <td className="py-1.5 text-right">{fmtUsd(N.cases?.[i]?.objective)}</td>
                  <td className="py-1.5 text-right">{fmtNum(c.unserved_mwh, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 max-w-3xl text-xs text-dim">
            The battery plan and the gas on/off decision are fixed before the weather is known; solar, wind and gas output
            then adjust to the case that happens.
          </p>
        </Panel>
      )}

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel tag="dispatch" title="Optimal schedule (LP, with battery)" right={<SourceBadge source="classical_lp" />}>
          <DispatchChart scenario={scenario} result={lp} />
        </Panel>
        <Panel tag="dispatch" title="Baseline (no battery)" right={<SourceBadge source="classical_no_battery" />}>
          <DispatchChart scenario={scenario} result={nb} />
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <Panel tag="storage" title="Battery state of charge">
          <SocChart scenario={scenario} series={[{ name: "LP optimum", result: lp }, { name: "no battery", result: nb }]} />
        </Panel>
        <Panel tag="ledger" title="Cost breakdown">
          <table className="num w-full text-sm">
            <thead>
              <tr className="label">
                <th className="pb-2 text-left font-normal">Item</th>
                <th className="pb-2 text-right font-normal">LP optimum</th>
                <th className="pb-2 text-right font-normal">No battery</th>
              </tr>
            </thead>
            <tbody>
              {costRows.map(([label, key]) => (
                <tr key={key} className="border-t border-line">
                  <td className="py-1.5 text-dim">{label}</td>
                  <td className="py-1.5 text-right">{fmtUsd(L[key] ?? 0)}</td>
                  <td className="py-1.5 text-right">{fmtUsd(N[key] ?? 0)}</td>
                </tr>
              ))}
              <tr className="border-t border-line-bright font-semibold">
                <td className="py-1.5">Total</td>
                <td className="py-1.5 text-right text-ok">{fmtUsd(L.objective)}</td>
                <td className="py-1.5 text-right text-gas">{fmtUsd(N.objective)}</td>
              </tr>
            </tbody>
          </table>
        </Panel>
      </div>

      {exact.length > 0 && (
        <Panel tag="benchmark" title="Exact enumeration of the discrete problem QAOA solves"
          right={<SourceBadge source="classical_exact" />}>
          <table className="num w-full text-sm">
            <thead>
              <tr className="label">
                <th className="pb-2 text-left font-normal">Tier</th>
                <th className="pb-2 text-left font-normal">Battery levels MWh</th>
                <th className="pb-2 text-right font-normal">Paths</th>
                <th className="pb-2 text-right font-normal">Feasible</th>
                <th className="pb-2 text-left font-normal pl-6">Best SOC path</th>
                {scenario.unit_commitment && <th className="pb-2 text-left font-normal pl-6">Gas unit</th>}
                <th className="pb-2 text-right font-normal">Cost</th>
                <th className="pb-2 text-right font-normal">Gap to LP</th>
                <th className="pb-2 text-right font-normal">Time</th>
              </tr>
            </thead>
            <tbody>
              {exact.map((r) => (
                <tr key={String(r.details.tier)} className="border-t border-line">
                  <td className="py-1.5 text-quantum">{String(r.details.tier)}</td>
                  <td className="py-1.5 text-dim">{fmtPath(r.details.levels)}</td>
                  <td className="py-1.5 text-right">{fmtNum(r.details.n_paths)}</td>
                  <td className="py-1.5 text-right">{fmtNum(r.details.n_feasible)}</td>
                  <td className="py-1.5 pl-6">{fmtPath(r.details.best_path)}</td>
                  {scenario.unit_commitment && <td className="py-1.5 pl-6">{fmtOnOff(r.details.best_commits)}</td>}
                  <td className="py-1.5 text-right">{fmtUsd(r.evaluation?.objective)}</td>
                  <td className="py-1.5 text-right">{fmtUsd((r.evaluation?.objective ?? 0) - L.objective)}</td>
                  <td className="py-1.5 text-right text-dim">{((r.provenance.solve_time_s ?? 0) * 1000).toFixed(1)} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </div>
  );
}
