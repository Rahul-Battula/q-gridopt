# QISKIT INTEGRATION: end-to-end QAOA on the Aer simulator: QUBO (qiskit_optimization) ->
# SparsePauliOp -> qaoa_ansatz -> Aer EstimatorV2 training -> Aer SamplerV2 sampling, ideal and
# with an IBM device noise model (AerSimulator.from_backend + generate_preset_pass_manager).
"""Run QAOA for one tier and depth on the simulator and compare with random sampling.

aer_statevector: train angles, sample the ideal circuit.
aer_noisy:       take the SAME trained angles (no retraining, exactly as for hardware), transpile
                 for an IBM chip, sample with that chip's noise model.

The reported schedule is the cheapest FEASIBLE battery path that was actually sampled,
completed by merit-order dispatch and scored by the shared evaluator.
"""

import numpy as np

from app.grid.evaluator import evaluate
from app.models.grid import Scenario
from app.models.result import Provenance, SolverResult, Source
from app.provenance import library_versions, utc_now
from app.quantum import aer_runner, decoder
from app.quantum.ising import qubo_to_ising
from app.quantum.qaoa import (
    CostOperator,
    TrainResult,
    build_ansatz,
    make_cost_operator,
    parameter_values,
    qaoa_circuit,
    train,
)
from app.quantum.qubo import QuboModel, build_qubo
from app.quantum.transpile import (
    DEFAULT_FAKE_BACKEND,
    circuit_stats,
    fake_backend,
    logical_circuit,
    transpile_for_backend,
)

DEFAULT_SHOTS = 4096
DEFAULT_SEED = 1234
QISKIT_PACKAGES = ("qiskit", "qiskit-aer", "qiskit-optimization", "qiskit-ibm-runtime", "scipy")


def cost_for(scenario: Scenario, tier: str, penalty: float | None,
             mixer: str = "x") -> tuple[QuboModel, CostOperator]:
    """mixer "x" = standard X mixer; "xy" = ring XY mixer inside each hour's one-hot block."""
    if mixer not in ("x", "xy"):
        raise ValueError(f"unknown mixer {mixer!r}")
    model = build_qubo(scenario, tier, penalty)
    op, offset = qubo_to_ising(model)
    cost = make_cost_operator(op, offset)
    if mixer == "xy":
        if not model.one_hot:
            raise ValueError(f"the XY mixer needs a one-hot tier (Q9 or Q18), not {tier}")
        width = len(model.states)
        cost.xy_blocks = [list(range(t * width, (t + 1) * width)) for t in range(model.num_periods)]
    return model, cost


def circuit_report(cost: CostOperator, reps: int, backend_name: str = DEFAULT_FAKE_BACKEND,
                   seed: int = 1) -> dict:
    """Circuit size before (native gates, no routing) and after transpiling for an IBM chip."""
    backend = fake_backend(backend_name)
    circuit = qaoa_circuit(cost, reps)
    circuit.measure_all()  # same circuit the noisy / hardware run executes
    return {
        "backend": backend_name,
        "logical": circuit_stats(logical_circuit(circuit, backend, seed)),
        "transpiled": circuit_stats(transpile_for_backend(circuit, backend, seed)),
    }


def _random_baseline(n: int, shots: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    uniform = np.full(2 ** n, 1 / 2 ** n)
    rng = np.random.default_rng(seed)
    return uniform, np.bincount(rng.integers(0, 2 ** n, shots), minlength=2 ** n) / shots


def _found(info: decoder.PathInfo | None) -> dict | None:
    if info is None:
        return None
    return {"path": list(info.path), "objective": info.objective,
            **({"commits": list(info.commits)} if info.commits is not None else {})}


def build_sampled_result(source: Source, scenario: Scenario, counts: dict[str, int], table,
                         provenance: Provenance, details: dict) -> SolverResult:
    """Score sampled counts with the shared evaluator + the same statistics for every source."""
    n = details["num_qubits"]
    probs = decoder.counts_to_probabilities(counts, n)
    found = decoder.best_found(probs, table)
    schedule = decoder.schedule_for(scenario, found) if found else None
    uniform, random_probs = _random_baseline(n, provenance.shots, details["seed"])
    details.update({
        "optimal_objective": decoder.optimal_objective(table),
        "worst_feasible_objective": decoder.worst_objective(table),
        "best_found": _found(found),
        "qaoa_sampled": decoder.distribution_stats(probs, table),
        "random_exact": decoder.distribution_stats(uniform, table),
        "random_sampled": decoder.distribution_stats(random_probs, table),
        "random_best_found": _found(decoder.best_found(random_probs, table)),
        "top_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])[:10]),
        "histogram": decoder.histogram(counts, table),
    })
    return SolverResult(source=source, scenario_name=scenario.name, schedule=schedule,
                        evaluation=evaluate(scenario, schedule) if schedule else None,
                        provenance=provenance, details=details)


def run_qaoa_simulation(scenario: Scenario, tier: str, reps: int, shots: int = DEFAULT_SHOTS,
                        seed: int = DEFAULT_SEED, warm_start: TrainResult | None = None,
                        penalty: float | None = None, mixer: str = "x") -> tuple[SolverResult, TrainResult]:
    model, cost = cost_for(scenario, tier, penalty, mixer)
    trained = train(cost, reps, seed=seed, warm_start=warm_start)
    circuit = build_ansatz(cost, reps)
    values = parameter_values(circuit, trained.gammas, trained.betas)
    table = decoder.path_table(scenario, model)

    details = {
        "tier": tier, "reps": reps, "mixer": mixer, "num_qubits": model.num_qubits, "penalty": model.penalty,
        "seed": seed, "gammas": trained.gammas, "betas": trained.betas,
        "training": {"expected_energy_dollars": trained.energy_dollars,
                     "evaluations": trained.evaluations, "seconds": trained.seconds,
                     "starts": trained.starts},
        "qaoa_exact": decoder.distribution_stats(aer_runner.exact_probabilities(circuit, values), table),
        "circuit": circuit_report(cost, reps, seed=seed),
    }
    provenance = Provenance(
        method=f"QAOA p={reps} on {tier} ({model.num_qubits} qubits, {mixer.upper()} mixer), angles trained on exact Aer EstimatorV2",
        backend="AerSimulator (statevector, ideal)", shots=shots, timestamp=utc_now(),
        solve_time_s=trained.seconds, library_versions=library_versions(*QISKIT_PACKAGES),
    )
    counts = aer_runner.sample_ideal(circuit, values, shots, seed)
    return build_sampled_result("aer_statevector", scenario, counts, table, provenance, details), trained


def run_depth_sweep(scenario: Scenario, tier: str, max_reps: int = 3, **kwargs) -> list[SolverResult]:
    """p = 1..max_reps, each depth warm-started from the previous one (INTERP)."""
    results, warm = [], None
    for reps in range(1, max_reps + 1):
        result, warm = run_qaoa_simulation(scenario, tier, reps, warm_start=warm, **kwargs)
        results.append(result)
    return results


def run_noisy_simulation(scenario: Scenario, ideal: SolverResult,
                         backend_name: str = DEFAULT_FAKE_BACKEND, shots: int | None = None,
                         seed: int | None = None) -> SolverResult:
    """Re-run an ideal result's circuit with its FIXED trained angles under device noise."""
    if ideal.source != "aer_statevector":
        raise ValueError("noisy simulation starts from an aer_statevector result")
    d = ideal.details
    shots = shots or ideal.provenance.shots
    seed = d["seed"] if seed is None else seed
    model, cost = cost_for(scenario, d["tier"], d["penalty"])
    table = decoder.path_table(scenario, model)

    backend = fake_backend(backend_name)
    transpiled = aer_runner.transpile_measured(qaoa_circuit(cost, d["reps"]), backend, seed)
    values = parameter_values(transpiled, d["gammas"], d["betas"])
    noisy_counts = aer_runner.sample_noisy(transpiled, values, backend, shots, seed)
    noiseless = aer_runner.sample_transpiled_ideal(transpiled, values, shots, seed)

    details = {
        "tier": d["tier"], "reps": d["reps"], "num_qubits": model.num_qubits, "penalty": model.penalty,
        "seed": seed, "gammas": d["gammas"], "betas": d["betas"],
        "noise_backend": backend_name,
        "ideal_exact": d["qaoa_exact"],
        "transpiled_noiseless_sampled": decoder.distribution_stats(
            decoder.counts_to_probabilities(noiseless, model.num_qubits), table),
        "circuit": {"backend": backend_name, "logical": d["circuit"]["logical"]
                    if d["circuit"]["backend"] == backend_name else None,
                    "transpiled": circuit_stats(transpiled)},
    }
    provenance = Provenance(
        method=f"QAOA p={d['reps']} on {d['tier']}, fixed angles from ideal training, device noise model",
        backend=f"AerSimulator.from_backend({backend_name})", shots=shots, timestamp=utc_now(),
        library_versions=library_versions(*QISKIT_PACKAGES),
    )
    return build_sampled_result("aer_noisy", scenario, noisy_counts, table, provenance, details)
