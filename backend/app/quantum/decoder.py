# QISKIT INTEGRATION: turns Qiskit measurement results (counts keys / statevector indices) into
# battery paths and schedules, and summarises the measured distribution.
"""Bitstring -> battery path -> schedule, plus distribution statistics.

Index k of a basis state: qubit i = bit i of k (Qiskit convention), so a counts key maps to
k = int(key, 2) and variable i of the QUBO is (k >> i) & 1.

The same statistics are applied to QAOA output and to the uniform-random baseline, so the
comparison is like for like.
"""

import itertools
from dataclasses import dataclass

import numpy as np

from app.grid.dispatch import dispatch_from_soc_path
from app.grid.evaluator import evaluate
from app.models.grid import Scenario
from app.quantum.qubo import QuboModel

TIE_TOL = 1e-6


@dataclass(frozen=True)
class PathInfo:
    index: int  # basis-state index k
    path: tuple[float, ...]  # battery SOC at the end of each period
    objective: float  # $ from the shared evaluator
    feasible: bool
    commits: tuple[bool, ...] | None = None  # gas on/off per period (unit-commitment tiers only)


def bits_of(k: int, n: int) -> list[int]:
    return [(k >> i) & 1 for i in range(n)]


def index_of(x: list[int]) -> int:
    # int(b): NumPy int8 bits would overflow on b << i for i >= 7
    return sum(int(b) << i for i, b in enumerate(x))


def counts_to_probabilities(counts: dict[str, int], num_qubits: int) -> np.ndarray:
    probs = np.zeros(2 ** num_qubits)
    for key, c in counts.items():
        probs[int(key, 2)] += c
    return probs / probs.sum()


def path_table(scenario: Scenario, model: QuboModel) -> dict[int, PathInfo]:
    """Every VALID bitstring (one level per hour), scored by the shared evaluator."""
    table = {}
    for states in itertools.product(model.states, repeat=model.num_periods):
        path = tuple(level for level, _ in states)
        commits = tuple(bool(on) for _, on in states) if model.commit else None
        k = index_of(model.encode(path, commits))
        ev = evaluate(scenario, dispatch_from_soc_path(scenario, path, commits))
        table[k] = PathInfo(index=k, path=path, objective=ev.objective, feasible=ev.feasible,
                            commits=commits)
    return table


def schedule_for(scenario: Scenario, info: PathInfo):
    """The full schedule (merit-order dispatch + gas commitment) of a decoded path."""
    return dispatch_from_soc_path(scenario, list(info.path), info.commits)


def optimal_objective(table: dict[int, PathInfo]) -> float:
    return min(p.objective for p in table.values() if p.feasible)


def worst_objective(table: dict[int, PathInfo]) -> float:
    return max(p.objective for p in table.values() if p.feasible)


def approximation_ratio(mean_cost: float, best: float, worst: float) -> float:
    """1.0 = always the optimal plan, 0.0 = as bad as the worst feasible plan."""
    return 1.0 if worst - best <= TIE_TOL else (worst - mean_cost) / (worst - best)


def distribution_stats(probs: np.ndarray, table: dict[int, PathInfo], top: int = 5) -> dict:
    """Summary of a probability distribution over bitstrings (exact or sampled).

    approximation_ratio (headline, user-approved definition): over ALL shots, where a shot that
    is invalid (not one level per hour) or breaks a rule is scored as the WORST feasible plan.
    approximation_ratio_feasible: over feasible shots only (shown alongside, flatters QAOA).
    """
    best, worst = optimal_objective(table), worst_objective(table)
    valid = [(probs[k], info) for k, info in table.items()]
    p_valid = sum(p for p, _ in valid)
    p_feasible = sum(p for p, i in valid if i.feasible)
    p_optimal = sum(p for p, i in valid if i.feasible and i.objective <= best + TIE_TOL)
    feasible_mass = [(p, i) for p, i in valid if i.feasible and p > 0]
    feasible_cost = sum(p * i.objective for p, i in feasible_mass)
    expected = feasible_cost / p_feasible if p_feasible > 0 else None
    mean_all = feasible_cost + (1 - p_feasible) * worst  # probs sum to 1
    ranked = sorted(((p, i) for p, i in valid if p > 0), key=lambda t: -t[0])[:top]
    return {
        "p_valid": float(p_valid),
        "p_feasible": float(p_feasible),
        "p_optimal": float(p_optimal),
        "approximation_ratio": float(approximation_ratio(mean_all, best, worst)),
        "approximation_ratio_feasible": None if expected is None
        else float(approximation_ratio(expected, best, worst)),
        "expected_cost_if_feasible": expected,
        "top_paths": [{"path": list(i.path), "probability": float(p), "objective": i.objective,
                       "feasible": i.feasible,
                       **({"commits": list(i.commits)} if i.commits is not None else {})} for p, i in ranked],
    }


def histogram(counts: dict[str, int], table: dict[int, PathInfo], top: int = 16) -> list[dict]:
    """Most frequent measured bitstrings, decoded, ready for the dashboard to draw as-is."""
    best = optimal_objective(table)
    shots = sum(counts.values())
    rows = []
    for key, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]:
        info = table.get(int(key, 2))
        rows.append({
            "bitstring": key, "count": c, "probability": c / shots,
            "path": None if info is None else list(info.path),
            **({"commits": list(info.commits)} if info is not None and info.commits is not None else {}),
            "objective": None if info is None else info.objective,
            "feasible": bool(info and info.feasible),
            "optimal": bool(info and info.feasible and info.objective <= best + TIE_TOL),
        })
    return rows


def best_found(probs: np.ndarray, table: dict[int, PathInfo]) -> PathInfo | None:
    """Cheapest feasible path that appears at least once in the distribution."""
    seen = [i for k, i in table.items() if probs[k] > 0 and i.feasible]
    return min(seen, key=lambda i: i.objective) if seen else None
