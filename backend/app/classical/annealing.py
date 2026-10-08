"""Classical heuristic baseline: simulated annealing (SA) on the SAME QUBO that QAOA solves.

Plain English: start from random yes/no settings, repeatedly flip one variable, always keep
flips that lower the cost and sometimes keep flips that raise it ("temperature"). The temperature
falls slowly, so the search settles into a low-cost plan. Each "read" is one independent run and
produces one sample, so SA with R reads is compared with QAOA using R shots.

Technical: single-spin-flip Metropolis on E(x) = c + sum_i h_i x_i + sum_{i<j} J_ij x_i x_j,
all reads vectorised with NumPy. Geometric schedule from T_hot (largest possible uphill move
accepted with probability 1/2) to T_cold = T_hot * 1e-4. Not tuned per instance.
"""

import time

import numpy as np

from app.grid.evaluator import evaluate
from app.models.grid import Scenario
from app.models.result import Provenance, SolverResult
from app.provenance import utc_now
from app.quantum import decoder
from app.quantum.qubo import QuboModel, build_qubo

DEFAULT_SWEEPS = 100
COLD_RATIO = 1e-4


def anneal(model: QuboModel, reads: int, sweeps: int = DEFAULT_SWEEPS, seed: int = 0) -> np.ndarray:
    """Return one final bitstring per read, shape (reads, n), dtype int8."""
    n = model.num_qubits
    h = np.zeros(n)
    for i, c in model.linear.items():
        h[i] = c
    J = np.zeros((n, n))
    for (i, j), c in model.quadratic.items():
        J[i, j] = J[j, i] = c

    max_delta = float(np.max(np.abs(h) + np.abs(J).sum(axis=1))) or 1.0
    t_hot = max_delta / np.log(2)
    temps = np.geomspace(t_hot, t_hot * COLD_RATIO, sweeps)

    rng = np.random.default_rng(seed)
    x = rng.integers(0, 2, size=(reads, n)).astype(np.int8)
    for T in temps:
        for i in rng.permutation(n):
            field = h[i] + x @ J[:, i]  # energy change of setting x_i = 1 vs 0, per read
            delta = (1 - 2 * x[:, i]) * field  # energy change of flipping x_i
            accept = (delta <= 0) | (rng.random(reads) < np.exp(-np.maximum(delta, 0) / T))
            x[accept, i] ^= 1
    return x


def samples_to_counts(samples: np.ndarray) -> dict[str, int]:
    """Same key format as Qiskit counts: bitstring of the index k, qubit/variable 0 rightmost."""
    weights = 1 << np.arange(samples.shape[1])
    keys, counts = np.unique(samples.astype(np.int64) @ weights, return_counts=True)
    n = samples.shape[1]
    return {format(int(k), f"0{n}b"): int(c) for k, c in zip(keys, counts)}


def solve_annealing(scenario: Scenario, tier: str, reads: int = 4096, sweeps: int = DEFAULT_SWEEPS,
                    seed: int = 0, penalty: float | None = None) -> SolverResult:
    model = build_qubo(scenario, tier, penalty)
    start = time.perf_counter()
    counts = samples_to_counts(anneal(model, reads, sweeps, seed))
    elapsed = time.perf_counter() - start

    table = decoder.path_table(scenario, model)
    probs = decoder.counts_to_probabilities(counts, model.num_qubits)
    found = decoder.best_found(probs, table)
    schedule = decoder.schedule_for(scenario, found) if found else None
    return SolverResult(
        source="classical_annealing",
        scenario_name=scenario.name,
        schedule=schedule,
        evaluation=evaluate(scenario, schedule) if schedule else None,
        provenance=Provenance(
            method=f"Simulated annealing on the {tier} QUBO, {sweeps} sweeps per read",
            backend="numpy", shots=reads, timestamp=utc_now(), solve_time_s=elapsed,
        ),
        details={
            "tier": tier, "num_qubits": model.num_qubits, "penalty": model.penalty, "seed": seed,
            "sweeps": sweeps,
            "optimal_objective": decoder.optimal_objective(table),
            "worst_feasible_objective": decoder.worst_objective(table),
            "best_found": None if found is None else {
                "path": list(found.path), "objective": found.objective,
                **({"commits": list(found.commits)} if found.commits is not None else {})},
            "qaoa_sampled": decoder.distribution_stats(probs, table),  # same stats as QAOA, same key
            "histogram": decoder.histogram(counts, table),
        },
    )
