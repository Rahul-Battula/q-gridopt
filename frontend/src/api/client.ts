import type {
  Benchmark,
  GroverResults,
  Health,
  Preset,
  QuboPreview,
  Run,
  RunAccepted,
  RunSummary,
  ScenarioInput,
  Tier,
} from "../types/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* keep status text */
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/health"),
  presets: () => request<Preset[]>("/scenarios/presets"),
  quboPreview: (input: ScenarioInput, tier: Tier, reps = 1) =>
    post<QuboPreview>("/qubo/preview", { ...input, tier, reps }),
  runClassical: (input: ScenarioInput) => post<Run>("/runs/classical", input),
  runSimulator: (input: ScenarioInput, body: { tier: Tier; max_reps: number; shots: number; noisy: boolean }) =>
    post<RunAccepted>("/runs/quantum/simulator", { ...input, ...body }),
  runIbm: (
    input: ScenarioInput,
    body: { tier: Tier; max_reps: number; shots: number; backend: string | null; confirm: boolean },
  ) => post<RunAccepted>("/runs/quantum/ibm", { ...input, ...body }),
  runs: (kind?: string, limit = 200) => request<RunSummary[]>(`/runs?limit=${limit}${kind ? `&kind=${kind}` : ""}`),
  run: (id: string) => request<Run>(`/runs/${id}`),
  benchmark: () => request<Benchmark>("/benchmarks/latest"),
  grover: () => request<GroverResults>("/benchmarks/grover"),
};
