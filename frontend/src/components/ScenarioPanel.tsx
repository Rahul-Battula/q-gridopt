import { usePresets } from "../api/hooks";
import { useState } from "react";
import type { ForecastCase, Reserve, Scenario, UnitCommitment } from "../types/api";
import { useScenario } from "./ScenarioContext";
import { Button, Chip, ErrorBox, Loading, Panel } from "./ui";

function NumberCell({ value, onChange, step = 1, wide = false }: { value: number; onChange: (v: number) => void; step?: number; wide?: boolean }) {
  return (
    <input
      type="number"
      value={value}
      step={step}
      min={0}
      onChange={(e) => onChange(Number(e.target.value))}
      className={`${wide ? "w-full max-w-[9rem]" : "w-24"} text-right`}
    />
  );
}


type Field = readonly [string, string, (s: Scenario) => number, (s: Scenario, v: number) => void, number];
const GROUPS: { title: string; dot: string; fields: Field[] }[] = [
  { title: "Gas plant", dot: "bg-gas", fields: [
    ["Max output", "MW", (s) => s.gas_max, (s, v) => { s.gas_max = v; }, 1],
    ["Fuel cost", "$/MWh", (s) => s.costs.gas_price, (s, v) => { s.costs.gas_price = v; }, 1],
    ["CO₂ price", "$/t", (s) => s.costs.carbon_price, (s, v) => { s.costs.carbon_price = v; }, 1],
    ["CO₂ emitted", "t/MWh", (s) => s.costs.emission_factor, (s, v) => { s.costs.emission_factor = v; }, 0.01],
  ] },
  { title: "Battery", dot: "bg-battery", fields: [
    ["Capacity", "MWh", (s) => s.battery.capacity, (s, v) => { s.battery.capacity = v; }, 1],
    ["Max rate", "MW", (s) => s.battery.max_rate, (s, v) => { s.battery.max_rate = v; }, 1],
    ["Starts with", "MWh", (s) => s.battery.initial_soc, (s, v) => { s.battery.initial_soc = v; }, 1],
    ["Efficiency", "0 – 1", (s) => s.battery.efficiency, (s, v) => { s.battery.efficiency = v; }, 0.01],
    ["Wear cost", "$/MWh", (s) => s.costs.discharge_wear, (s, v) => { s.costs.discharge_wear = v; }, 1],
  ] },
  { title: "Penalties", dot: "bg-bad", fields: [
    ["Curtailment", "$/MWh", (s) => s.costs.curtailment_penalty, (s, v) => { s.costs.curtailment_penalty = v; }, 1],
    ["Unserved", "$/MWh", (s) => s.costs.unserved_penalty, (s, v) => { s.costs.unserved_penalty = v; }, 10],
  ] },
];

const DEFAULT_UNIT: UnitCommitment = { min_output: 40, startup_cost: 800, initial_on: false };
const DEFAULT_CASES: ForecastCase[] = [
  { name: "cloudy and calm", probability: 0.3, solar_factor: 0.7, wind_factor: 0.8 },
  { name: "as forecast", probability: 0.5, solar_factor: 1.0, wind_factor: 1.0 },
  { name: "sunny and windy", probability: 0.2, solar_factor: 1.1, wind_factor: 1.2 },
];
const DEFAULT_RESERVE: Reserve = { required_fraction: 0.1, shortfall_penalty: 50 };

function Toggle({ on, label, onChange }: { on: boolean; label: string; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm text-ink">
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

/** Pick a preset or edit any value. Edits are sent to the backend as a custom scenario. */
export function ScenarioPanel() {
  const presets = usePresets();
  const { presetId, custom, setPreset, setCustom } = useScenario();
  const [open, setOpen] = useState(false);
  if (presets.isLoading) return <Loading what="Loading scenarios" />;
  if (presets.error) return <ErrorBox error={presets.error} />;
  const base = presets.data!.find((p) => p.id === presetId)!.scenario;
  const sc: Scenario = custom ?? base;

  const edit = (fn: (s: Scenario) => void) => {
    const next: Scenario = structuredClone(sc);
    fn(next);
    if (!custom) next.name = `${base.name} (edited)`;
    setCustom(next);
  };

  return (
    <Panel
      tag="input"
      title="Grid scenario"
      right={
        <div className="flex items-center gap-3">
          <select value={presetId} onChange={(e) => setPreset(e.target.value)}>
            {presets.data!.map((p) => (
              <option key={p.id} value={p.id}>
                {p.scenario.name}
                {p.default ? " (default)" : ""}
              </option>
            ))}
          </select>
          {custom && <Button onClick={() => setCustom(null)}>Reset edits</Button>}
        </div>
      }
    >
      <p className="max-w-3xl text-sm leading-relaxed text-dim">{sc.description}</p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Chip tone="ink">{sc.periods.length} hours</Chip>
        <Chip tone="battery">battery {sc.battery.capacity} MWh · {sc.battery.max_rate} MW</Chip>
        <Chip tone="gas">gas ≤ {sc.gas_max} MW</Chip>
        {sc.unit_commitment && <Chip tone="ok" dot>unit commitment</Chip>}
        {sc.uncertainty && <Chip tone="ok" dot>{sc.uncertainty.cases.length} forecast cases</Chip>}
        {sc.reserve && <Chip tone="ok" dot>reserve {Math.round(sc.reserve.required_fraction * 100)}%</Chip>}
        <button onClick={() => setOpen((v) => !v)}
          className="ml-auto rounded-md border border-line px-3.5 py-1.5 text-xs font-medium text-dim transition hover:border-line-bright hover:text-ink">
          {open ? "Hide values ▴" : "Edit values ▾"}
        </button>
      </div>
      {open && (<div className="mt-6 space-y-7">
      <div>
        <div className="mb-2 text-sm font-semibold text-ink">Hourly forecast</div>
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-sm">
            <thead>
              <tr className="label text-left">
                <th className="px-4 py-2.5 font-medium">Hour</th>
                <th className="px-4 py-2.5 font-medium">City demand <span className="text-faint">MW</span></th>
                <th className="px-4 py-2.5 font-medium text-solar">Solar available <span className="text-faint">MW</span></th>
                <th className="px-4 py-2.5 font-medium text-wind">Wind available <span className="text-faint">MW</span></th>
              </tr>
            </thead>
            <tbody>
              {sc.periods.map((p, i) => (
                <tr key={p.name} className="border-t border-line">
                  <td className="px-4 py-2 font-medium text-ink">{p.name}</td>
                  <td className="px-4 py-2"><NumberCell wide value={p.demand} onChange={(v) => edit((s) => { s.periods[i].demand = v; })} /></td>
                  <td className="px-4 py-2"><NumberCell wide value={p.solar} onChange={(v) => edit((s) => { s.periods[i].solar = v; })} /></td>
                  <td className="px-4 py-2"><NumberCell wide value={p.wind} onChange={(v) => edit((s) => { s.periods[i].wind = v; })} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid gap-x-8 gap-y-7 md:grid-cols-3">
        {GROUPS.map((g) => (
          <div key={g.title}>
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
              <span className={`h-2 w-2 rounded-full ${g.dot}`} />{g.title}
            </div>
            <div className="space-y-3 rounded-lg border border-line bg-panel-2 p-4">
              {g.fields.map(([label, unit, get, set, step]) => (
                <label key={label} className="flex items-center justify-between gap-3">
                  <span className="text-sm text-dim">{label}</span>
                  <span className="flex items-center gap-2">
                    <NumberCell value={get(sc)} step={step} onChange={(v) => edit((x) => set(x, v))} />
                    <span className="num w-12 text-xs text-faint">{unit}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 border-t border-line pt-4">
        <div className="label mb-3">Extended model (optional)</div>
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="space-y-2">
            <Toggle on={Boolean(sc.unit_commitment)} label="Gas on/off (unit commitment)"
              onChange={(v) => edit((s) => { s.unit_commitment = v ? { ...DEFAULT_UNIT } : null; })} />
            {sc.unit_commitment && (
              <div className="space-y-2 text-sm">
                <label className="flex items-center justify-between gap-2">
                  <span className="label">Min output MW</span>
                  <NumberCell value={sc.unit_commitment.min_output} onChange={(v) => edit((s) => { s.unit_commitment!.min_output = v; })} />
                </label>
                <label className="flex items-center justify-between gap-2">
                  <span className="label">Start-up $</span>
                  <NumberCell value={sc.unit_commitment.startup_cost} step={50} onChange={(v) => edit((s) => { s.unit_commitment!.startup_cost = v; })} />
                </label>
                <Toggle on={sc.unit_commitment.initial_on} label="already on before hour 1"
                  onChange={(v) => edit((s) => { s.unit_commitment!.initial_on = v; })} />
              </div>
            )}
          </div>
          <div className="space-y-2">
            <Toggle on={Boolean(sc.uncertainty)} label="Forecast uncertainty"
              onChange={(v) => edit((s) => { s.uncertainty = v ? { cases: structuredClone(DEFAULT_CASES) } : null; })} />
            {sc.uncertainty && (
              <table className="num text-xs text-dim">
                <tbody>
                  {sc.uncertainty.cases.map((c) => (
                    <tr key={c.name}>
                      <td className="pr-3">{c.name}</td>
                      <td className="pr-3 text-right">{Math.round(c.probability * 100)}%</td>
                      <td className="text-right">sun ×{c.solar_factor} · wind ×{c.wind_factor}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="space-y-2">
            <Toggle on={Boolean(sc.reserve)} label="Reserve margin"
              onChange={(v) => edit((s) => { s.reserve = v ? { ...DEFAULT_RESERVE } : null; })} />
            {sc.reserve && (
              <div className="space-y-2 text-sm">
                <label className="flex items-center justify-between gap-2">
                  <span className="label">Required % of demand</span>
                  <NumberCell value={Math.round(sc.reserve.required_fraction * 100)} onChange={(v) => edit((s) => { s.reserve!.required_fraction = v / 100; })} />
                </label>
                <label className="flex items-center justify-between gap-2">
                  <span className="label">Shortfall $/MW</span>
                  <NumberCell value={sc.reserve.shortfall_penalty} onChange={(v) => edit((s) => { s.reserve!.shortfall_penalty = v; })} />
                </label>
              </div>
            )}
          </div>
        </div>
      </div>
      </div>)}
    </Panel>
  );
}

/** The scenario object currently selected (preset or edited copy), or undefined while loading. */
export function useCurrentScenario(): Scenario | undefined {
  const presets = usePresets();
  const { presetId, custom } = useScenario();
  return custom ?? presets.data?.find((p) => p.id === presetId)?.scenario;
}
