import { useQuery } from "@tanstack/react-query";
import { FINAL_STATUSES, type Run } from "../types/api";
import { api } from "./client";

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15_000 });

export const usePresets = () =>
  useQuery({ queryKey: ["presets"], queryFn: api.presets, staleTime: Infinity });

export const useRuns = (kind?: string) =>
  useQuery({ queryKey: ["runs", kind ?? "all"], queryFn: () => api.runs(kind), refetchInterval: 4_000 });

/** Polls a run every 1.5 s until it is completed or failed. */
export const useRun = (runId: string | undefined) =>
  useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.run(runId!),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const run = query.state.data as Run | undefined;
      return run && FINAL_STATUSES.includes(run.status) ? false : 1_500;
    },
  });
