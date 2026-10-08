import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { Scenario, ScenarioInput } from "../types/api";

interface ScenarioState {
  presetId: string;
  /** A user-edited copy of the preset, or null while the preset is used unchanged. */
  custom: Scenario | null;
  setPreset: (id: string) => void;
  setCustom: (s: Scenario | null) => void;
  /** What every API call sends: the preset id, or the full edited scenario. */
  input: ScenarioInput;
}

const Ctx = createContext<ScenarioState | null>(null);

export function ScenarioProvider({ children }: { children: ReactNode }) {
  const [presetId, setPresetId] = useState("scenario_b");
  const [custom, setCustom] = useState<Scenario | null>(null);
  const value = useMemo<ScenarioState>(
    () => ({
      presetId,
      custom,
      setPreset: (id) => {
        setPresetId(id);
        setCustom(null);
      },
      setCustom,
      input: custom ? { scenario: custom } : { preset: presetId },
    }),
    [presetId, custom],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useScenario(): ScenarioState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useScenario outside ScenarioProvider");
  return v;
}
