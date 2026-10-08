// Shapes returned by the FastAPI backend (backend/app/models, backend/app/api/schemas.py).
// The dashboard only DISPLAYS these; every number is computed by the backend.

export interface Period {
  name: string;
  demand: number;
  solar: number;
  wind: number;
}

export interface Battery {
  capacity: number;
  max_rate: number;
  initial_soc: number;
  efficiency: number;
}

export interface CostWeights {
  gas_price: number;
  carbon_price: number;
  emission_factor: number;
  curtailment_penalty: number;
  discharge_wear: number;
  unserved_penalty: number;
}

export interface UnitCommitment {
  min_output: number;
  startup_cost: number;
  initial_on: boolean;
}

export interface ForecastCase {
  name: string;
  probability: number;
  solar_factor: number;
  wind_factor: number;
}

export interface Reserve {
  required_fraction: number;
  shortfall_penalty: number;
}

export interface Scenario {
  name: string;
  description: string;
  periods: Period[];
  gas_max: number;
  battery: Battery;
  costs: CostWeights;
  /** Optional model features; absent/null = off. */
  unit_commitment?: UnitCommitment | null;
  uncertainty?: { cases: ForecastCase[] } | null;
  reserve?: Reserve | null;
}

export interface Preset {
  id: string;
  default: boolean;
  scenario: Scenario;
}

/** Either a preset id or a full scenario. */
export type ScenarioInput = { preset: string } | { scenario: Scenario };

export interface PeriodDispatch {
  solar: number;
  wind: number;
  gas: number;
  charge: number;
  discharge: number;
  unserved: number;
  gas_on?: boolean | null;
}

export interface PeriodMetrics {
  name: string;
  soc_end: number;
  curtailment: number;
  co2_tonnes: number;
  total_cost: number;
  startup_cost?: number;
  reserve_cost?: number;
  reserve_shortfall_mw?: number;
  gas_on?: boolean | null;
}

export interface CaseOutcome {
  name: string;
  probability: number;
  objective: number;
  unserved_mwh: number;
  curtailment_mwh: number;
}

export interface Violation {
  period: string | null;
  kind: string;
  amount: number;
  detail: string;
}

export interface Evaluation {
  objective: number;
  gas_cost: number;
  co2_cost: number;
  curtailment_cost: number;
  wear_cost: number;
  unserved_cost: number;
  startup_cost?: number;
  reserve_cost?: number;
  gas_mwh: number;
  co2_tonnes: number;
  curtailment_mwh: number;
  unserved_mwh: number;
  renewable_utilization: number;
  soc_trajectory: number[];
  periods: PeriodMetrics[];
  violations: Violation[];
  reserve_shortfall_mwh?: number;
  startups?: number;
  cases?: CaseOutcome[];
  worst_case_objective?: number | null;
  feasible: boolean;
}

export type Source =
  | "classical_lp"
  | "classical_exact"
  | "classical_no_battery"
  | "classical_annealing"
  | "aer_statevector"
  | "aer_noisy"
  | "ibm_hardware";

export interface Provenance {
  method: string;
  backend: string | null;
  job_id: string | null;
  shots: number | null;
  timestamp: string;
  solve_time_s: number | null;
  library_versions: Record<string, string>;
}

export interface DistStats {
  p_valid: number;
  p_feasible: number;
  p_optimal: number;
  approximation_ratio: number;
  approximation_ratio_feasible: number | null;
  expected_cost_if_feasible: number | null;
  top_paths: { path: number[]; commits?: boolean[]; probability: number; objective: number; feasible: boolean }[];
}

export interface CircuitStats {
  depth: number;
  two_qubit_gates: number;
  two_qubit_depth: number;
  total_gates: number;
  active_qubits: number;
  ops: Record<string, number>;
}

export interface HistogramRow {
  bitstring: string;
  count: number;
  probability: number;
  path: number[] | null;
  commits?: boolean[];
  objective: number | null;
  feasible: boolean;
  optimal: boolean;
}

/** details{} differ per source; quantum fields are optional. */
export interface ResultDetails {
  tier?: string | null;
  reps?: number;
  num_qubits?: number;
  penalty?: number;
  levels?: number[];
  best_commits?: boolean[] | null;
  best_path?: number[];
  optimal_paths?: number[][];
  n_paths?: number;
  n_feasible?: number;
  optimal_objective?: number;
  worst_feasible_objective?: number;
  best_found?: { path: number[]; commits?: boolean[]; objective: number } | null;
  qaoa_exact?: DistStats;
  ideal_exact?: DistStats;
  qaoa_sampled?: DistStats;
  random_exact?: DistStats;
  random_sampled?: DistStats;
  histogram?: HistogramRow[];
  circuit?: { backend: string; logical: CircuitStats | null; transpiled: CircuitStats };
  noise_backend?: string;
  gammas?: number[];
  betas?: number[];
  training?: { expected_energy_dollars: number; evaluations: number; seconds: number };
  hardware_options?: Record<string, unknown>;
  qpu_usage_seconds_whole_job?: number | null;
  [key: string]: unknown;
}

export interface SolverResult {
  source: Source;
  scenario_name: string;
  schedule: { periods: PeriodDispatch[] } | null;
  evaluation: Evaluation | null;
  provenance: Provenance;
  details: ResultDetails;
}

export type RunKind = "classical" | "quantum_simulator" | "quantum_ibm";
export type RunStatus = "queued" | "running" | "submitted" | "completed" | "failed";

export interface RunSummary {
  run_id: string;
  kind: RunKind;
  status: RunStatus;
  progress: string | null;
  scenario_name: string;
  created_at: string;
  updated_at: string;
  job_id: string | null;
  sources: Source[];
  best_objective: number | null;
}

export interface Run extends RunSummary {
  request: Record<string, unknown>;
  error: string | null;
  results: SolverResult[];
}

export interface RunAccepted {
  run_id: string;
  status: RunStatus;
}

export interface Health {
  status: string;
  time: string;
  default_preset: string;
  ibm_credentials_configured: boolean;
  versions: Record<string, string>;
}

export type BenchTier = "Q3" | "Q9" | "Q18";
/** Q3U / Q9U add the gas unit's on/off commitment (scenarios with unit_commitment). */
export type Tier = BenchTier | "Q3U" | "Q9U";

export interface QuboPreview {
  tier: Tier;
  levels: number[];
  encoding: "binary" | "one-hot";
  num_qubits: number;
  penalty: number;
  penalty_rule: string;
  unit_commitment?: boolean;
  variables: { index: number; name: string; period: string; level: number; gas_on?: boolean | null }[];
  qubo: {
    constant: number;
    linear: { i: number; coef: number }[];
    quadratic: { i: number; j: number; coef: number }[];
    text: string;
  };
  ising: { offset: number; num_terms: number; num_zz: number; terms: { pauli: string; coef: number }[] };
  bitstrings_total: number;
  valid_bitstrings: number;
  ground_state: { bitstring: string; path: number[]; commits?: boolean[] | null; energy: number };
  circuit_svg: string | null;
  circuit_stats: { reps: number; backend: string; logical: CircuitStats; transpiled: CircuitStats };
}

export const FINAL_STATUSES: RunStatus[] = ["completed", "failed"];

export type BenchMethod = "exact" | "lp" | "annealing" | "no_battery" | "random" | "qaoa_ideal" | "qaoa_noisy";

export interface BenchSummaryRow {
  tier: Tier;
  method: BenchMethod;
  reps: number | null;
  instances: number;
  accuracy_top1: number;
  accuracy_best: number;
  f1_top1: number;
  f1_best: number;
  p_optimal_mean: number | null;
  p_optimal_min: number | null;
  approximation_ratio_mean: number | null;
  p_valid_mean: number | null;
  best_gap_mean: number | null;
  samples_99_median: number | null; // null = never (success rate 0)
  time_s_mean: number | null;
}

export interface Benchmark {
  created_at: string;
  config: {
    instances: number;
    tiers: Tier[];
    qaoa_instances: Record<string, number>;
    noisy_tiers: Tier[];
    shots: number;
    max_reps: number;
    first_seed: number;
    noise_backend: string;
    annealing: string;
  };
  library_versions: Record<string, string>;
  wall_time_s: number;
  instances: { instance: number; seed: number; lp_objective: number; no_battery_objective: number }[];
  summary: BenchSummaryRow[];
  headline: { tier: Tier; methods: Partial<Record<BenchMethod, { accuracy_top1: number; accuracy_best: number; f1_best: number; f1_top1: number; instances: number }>> }[];
}

export interface GroverRow {
  states: number;
  qubits: number;
  valid_plans: number;
  optimal_states: number;
  trials: number;
  gas_success_rate: number;
  gas_queries_mean: number | null;
  gas_queries_median: number | null;
  gas_queries_p90: number | null;
  random_unstructured_without_replacement_mean: number;
  classical_structured_mean: number;
  speedup_vs_unstructured: number | null;
  speedup_vs_structured: number | null;
  tier?: Tier;
  hours?: number;
  one_iteration?: { backend: string; two_qubit_gates: number; depth: number };
}

export interface GroverResults {
  created_at: string;
  trials: number;
  tiers: GroverRow[];
  chain: GroverRow[];
  exponent_gas: number;
  exponent_blind: number;
  first_hours_with_speedup: number | null;
  qiskit_circuit_check?: { tier: string; runs: number; found_optimum: number };
}
