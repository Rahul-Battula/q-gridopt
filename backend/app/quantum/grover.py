# QISKIT INTEGRATION: Grover adaptive minimum search on the battery QUBO. The oracle is a Qiskit
# DiagonalGate (phase -1 on every bitstring cheaper than the current threshold), the amplification
# step is qiskit.circuit.library.grover_operator, states come from qiskit.quantum_info.Statevector.
"""Grover Adaptive Search (Durr-Hoyer / Boyer-Brassard-Hoyer-Tapp) for the battery-plan QUBO.

Plain English: picture every bit pattern as a door; the cheapest battery plan is behind one of them.
A classical computer opens doors one at a time. Grover's algorithm opens ALL doors at once in
superposition, and each round makes the "better than my best so far" doors a little more likely
(oracle = flip their sign, diffuser = boost whatever was flipped). After about sqrt(N / M) rounds
(N doors, M of them better) measuring gives one of the better doors almost surely. We then lower the
bar to that door's cost and repeat, so the search finds the MINIMUM without ever being told where it is.

Technical: oracle O_y|x> = -|x> if E(x) < y else |x>; Grover operator Q = D O_y with D the reflection
about the uniform state. After j rounds the marked set has total probability sin^2((2j+1) theta),
sin(theta) = sqrt(M / N), spread uniformly inside the marked set (and the unmarked set). That closed form
is exact, so the search can be simulated for any size; it is checked against the Qiskit circuit in the tests.
Unknown M is handled with the BBHT schedule: j uniform in [0, m), m grows by 6/5 up to sqrt(N), and
resets to 1 after each improvement.

QUERY COUNTING (what the speedup is measured in): one oracle call = one coherent evaluation of the cost
function against the threshold. After measuring, the candidate's cost is evaluated classically, which
costs one more query. A classical unstructured search pays one query per bitstring it tries.

Qubit i = bit i of the basis-state index k (same convention as qubo.py / decoder.py).
"""

import math
from dataclasses import dataclass, field

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import DiagonalGate, grover_operator
from qiskit.quantum_info import Statevector

TIE_TOL = 1e-6
GROWTH = 6 / 5  # BBHT schedule growth factor


# ---------------------------------------------------------------- Qiskit circuits

def oracle_gate(num_qubits: int, marked: np.ndarray) -> DiagonalGate:
    """Phase oracle: -1 on the marked basis states, +1 elsewhere (qubit i = bit i of k)."""
    phases = np.ones(2 ** num_qubits)
    phases[marked] = -1.0
    return DiagonalGate(phases.tolist())


def grover_circuit(num_qubits: int, marked: np.ndarray, rounds: int) -> QuantumCircuit:
    """H on every qubit, then `rounds` x (oracle, diffuser)."""
    qc = QuantumCircuit(num_qubits, name=f"grover_{rounds}")
    qc.h(range(num_qubits))
    if rounds > 0:
        step = grover_operator(oracle_gate(num_qubits, marked))
        for _ in range(rounds):
            qc.compose(step, inplace=True)
    return qc


def circuit_probabilities(num_qubits: int, marked: np.ndarray, rounds: int) -> np.ndarray:
    """Outcome probabilities of the Qiskit Grover circuit (exact statevector)."""
    return Statevector(grover_circuit(num_qubits, marked, rounds)).probabilities()


# ---------------------------------------------------------------- closed form

def marked_set_probability(num_states: int, num_marked: int, rounds: int) -> float:
    """Total probability of measuring a marked state after `rounds` Grover rounds."""
    if num_marked <= 0:
        return 0.0
    if num_marked >= num_states:
        return 1.0
    theta = math.asin(math.sqrt(num_marked / num_states))
    return math.sin((2 * rounds + 1) * theta) ** 2


def optimal_rounds(num_states: int, num_marked: int) -> int:
    """Rounds that maximise the success probability when M is known: round(pi / (4 theta) - 1/2)."""
    theta = math.asin(math.sqrt(num_marked / num_states))
    return max(0, round(math.pi / (4 * theta) - 0.5))


def sample_candidate(rng: np.random.Generator, num_states: int, marked: np.ndarray, rounds: int,
                     engine: str = "closed_form", num_qubits: int | None = None) -> int:
    """One measurement of the Grover state. "closed_form" and "qiskit" give the same distribution."""
    if engine == "qiskit":
        probs = circuit_probabilities(num_qubits, marked, rounds)
        return int(rng.choice(num_states, p=probs / probs.sum()))
    if rng.random() < marked_set_probability(num_states, len(marked), rounds):
        return int(marked[rng.integers(len(marked))])
    # unmarked state, uniform: redraw until it is not marked (marked is a small set, or M = N never gets here)
    while True:
        k = int(rng.integers(num_states))
        if len(marked) == num_states or not _in_sorted(marked, k):
            return k


def _in_sorted(sorted_array: np.ndarray, value: int) -> bool:
    i = np.searchsorted(sorted_array, value)
    return i < len(sorted_array) and sorted_array[i] == value


# ---------------------------------------------------------------- adaptive search

@dataclass
class SearchResult:
    found: bool  # the global minimum was reached within the budget
    queries: int  # total queries when it was reached (or when the budget ran out)
    oracle_calls: int
    evaluations: int
    improvements: int
    trace: list[tuple[int, float]] = field(default_factory=list)  # (queries so far, best cost so far)


def grover_adaptive_search(energies: np.ndarray, rng: np.random.Generator, max_queries: int,
                           engine: str = "closed_form", num_qubits: int | None = None) -> SearchResult:
    """Find the minimum of `energies` (index = bitstring). Stops as soon as the global minimum has been
    reached; a real run, which does not know the minimum, would keep going to its budget (the measured
    quantity here is when the optimum is first reached)."""
    num_states = len(energies)
    optimum = float(energies.min())
    threshold_index = int(rng.integers(num_states))  # random starting door, costs one evaluation
    threshold = float(energies[threshold_index])
    queries, oracle_calls, evaluations, improvements = 1, 0, 1, 0
    trace = [(queries, threshold)]
    if threshold <= optimum + TIE_TOL:
        return SearchResult(True, queries, oracle_calls, evaluations, improvements, trace)
    marked = np.flatnonzero(energies < threshold - TIE_TOL)
    m, cap = 1.0, math.sqrt(num_states)
    while queries < max_queries:
        rounds = int(rng.integers(0, math.ceil(m)))
        candidate = sample_candidate(rng, num_states, marked, rounds, engine, num_qubits)
        oracle_calls += rounds
        evaluations += 1
        queries += rounds + 1
        cost = float(energies[candidate])
        if cost < threshold - TIE_TOL:
            threshold = cost
            improvements += 1
            trace.append((queries, threshold))
            if threshold <= optimum + TIE_TOL:
                return SearchResult(True, queries, oracle_calls, evaluations, improvements, trace)
            marked = np.flatnonzero(energies < threshold - TIE_TOL)
            m = 1.0
        else:
            m = min(GROWTH * m, cap)
    return SearchResult(False, queries, oracle_calls, evaluations, improvements, trace)


# ---------------------------------------------------------------- classical baselines (same query unit)

def random_search_queries(rng: np.random.Generator, space_size: int, num_optimal: int,
                          with_replacement: bool) -> int:
    """Queries a classical random search needs to try an optimal item for the first time."""
    if with_replacement:
        return int(rng.geometric(num_optimal / space_size))
    positions = rng.choice(space_size, size=num_optimal, replace=False)
    return int(positions.min()) + 1


def budget_for(num_states: int) -> int:
    """Query budget: ~8x the Durr-Hoyer expectation 22.5 sqrt(N), so failures are rare but counted."""
    return int(180 * math.sqrt(num_states) + 100)


def run_trials(energies: np.ndarray, valid_plans: int, trials: int, seed: int,
               engine: str = "closed_form", num_qubits: int | None = None) -> dict:
    """GAS against three classical searches, all counted in queries, over many independent runs."""
    rng = np.random.default_rng(seed)
    num_states = len(energies)
    optimum = float(energies.min())
    num_optimal = int(np.sum(energies <= optimum + TIE_TOL))
    budget = budget_for(num_states)
    gas = [grover_adaptive_search(energies, rng, budget, engine, num_qubits) for _ in range(trials)]
    won = [r.queries for r in gas if r.found]
    blind_with = [random_search_queries(rng, num_states, num_optimal, True) for _ in range(trials)]
    blind_without = [random_search_queries(rng, num_states, num_optimal, False) for _ in range(trials)]
    structured = [random_search_queries(rng, valid_plans, num_optimal, False) for _ in range(trials)]
    return {
        "states": num_states,
        "qubits": int(math.log2(num_states)),
        "valid_plans": valid_plans,
        "optimal_states": num_optimal,
        "trials": trials,
        "budget": budget,
        "gas_success_rate": len(won) / trials,
        "gas_queries_mean": float(np.mean(won)) if won else None,
        "gas_queries_median": float(np.median(won)) if won else None,
        "gas_queries_p90": float(np.percentile(won, 90)) if won else None,
        "gas_oracle_calls_mean": float(np.mean([r.oracle_calls for r in gas if r.found])) if won else None,
        "random_unstructured_with_replacement_mean": float(np.mean(blind_with)),
        "random_unstructured_without_replacement_mean": float(np.mean(blind_without)),
        "classical_structured_mean": float(np.mean(structured)),
        "classical_structured_note": "tries only the valid battery plans (exploits the problem structure)",
        "speedup_vs_unstructured": (float(np.mean(blind_without)) / float(np.mean(won))) if won else None,
        "speedup_vs_structured": (float(np.mean(structured)) / float(np.mean(won))) if won else None,
    }
