import math

import numpy as np
import pytest

from app.grid.presets import load_preset
from app.quantum import grover
from app.quantum.qubo import build_qubo


@pytest.fixture(scope="module")
def energies():
    return {t: build_qubo(load_preset("scenario_b"), t).energies_all() for t in ("Q3", "Q9")}


@pytest.mark.parametrize("tier,qubits", [("Q3", 3), ("Q9", 9)])
@pytest.mark.parametrize("rounds", [0, 1, 2, 3, 5])
def test_closed_form_matches_qiskit_circuit(energies, tier, qubits, rounds):
    """The sin^2((2j+1) theta) law, with uniform probability inside the marked / unmarked sets, equals the
    exact outcome distribution of the Qiskit Grover circuit."""
    e = energies[tier]
    marked = np.flatnonzero(e < np.median(e))  # a sizeable marked set
    probs = grover.circuit_probabilities(qubits, marked, rounds)
    n, m = len(e), len(marked)
    p_marked = grover.marked_set_probability(n, m, rounds)
    expected = np.full(n, (1 - p_marked) / (n - m))
    expected[marked] = p_marked / m
    assert np.allclose(probs, expected, atol=1e-9)


@pytest.mark.parametrize("tier,qubits", [("Q3", 3), ("Q9", 9)])
def test_single_optimum_amplified_to_near_certainty(energies, tier, qubits):
    e = energies[tier]
    marked = np.array([int(np.argmin(e))])
    rounds = grover.optimal_rounds(len(e), 1)
    probs = grover.circuit_probabilities(qubits, marked, rounds)
    assert probs[marked[0]] == pytest.approx(grover.marked_set_probability(len(e), 1, rounds), abs=1e-9)
    assert probs[marked[0]] > 0.94
    assert rounds == {3: 2, 9: 17}[qubits]  # about pi/4 sqrt(N) - 1/2: 1.7 -> 2 for N=8, 17.3 -> 17 for N=512


def test_optimal_rounds_scale_as_sqrt():
    assert grover.optimal_rounds(2 ** 10, 1) == 25
    assert grover.optimal_rounds(2 ** 20, 1) == 804
    assert grover.optimal_rounds(2 ** 20, 4) == pytest.approx(402, abs=1)


def test_gas_finds_the_exact_minimum(energies):
    for tier, qubits in (("Q3", 3), ("Q9", 9)):
        e = energies[tier]
        for seed in range(5):
            res = grover.grover_adaptive_search(e, np.random.default_rng(seed), grover.budget_for(len(e)))
            assert res.found
            assert res.trace[-1][1] == pytest.approx(float(e.min()))
            assert res.queries == res.oracle_calls + res.evaluations  # nothing is counted for free


def test_gas_with_qiskit_circuits_agrees_with_closed_form(energies):
    e = energies["Q3"]
    for seed in range(3):
        a = grover.grover_adaptive_search(e, np.random.default_rng(seed), 500, "qiskit", 3)
        assert a.found and a.trace[-1][1] == pytest.approx(float(e.min()))


def test_trial_statistics_are_sane(energies):
    stats = grover.run_trials(energies["Q9"], valid_plans=27, trials=40, seed=7)
    assert stats["gas_success_rate"] == 1.0
    assert stats["optimal_states"] == 1
    # unstructured search over 512 bitstrings needs ~256 queries on average without replacement
    assert 150 < stats["random_unstructured_without_replacement_mean"] < 380
    # a classical search that only tries the 27 valid plans is much cheaper than any search of 512 bitstrings
    assert stats["classical_structured_mean"] < 20
    assert math.isfinite(stats["speedup_vs_unstructured"])


def test_hardware_experiment_local_run_amplifies():
    """The hardware circuits on a local FakeFez noise model: amplification survives realistic noise."""
    from app.quantum import grover_ibm as gi
    from app.quantum.ibm_runner import HardwareOptions
    from app.quantum.transpile import circuit_stats, fake_backend

    exp = gi.experiment()
    assert exp["ideal"] == pytest.approx([0.125, 0.78125, 0.9453125], abs=1e-6)
    backend, opts = fake_backend("FakeFez"), HardwareOptions(shots=2048)
    pubs = gi.prepare(exp, backend, opts)
    job = gi.submit(pubs, backend, opts)  # fake backend: runs locally, no approval needed, nothing recorded
    res = gi.collect(exp, [circuit_stats(p["circuit"]) for p in pubs], job, backend.name, opts, fake=True)
    assert res["kind"] == "grover_simulation"
    p = [r["p_optimum_measured"] for r in res["rows"]]
    assert p[0] < 0.2 and p[1] > 0.6 and p[2] > p[1]


def test_real_backend_needs_approval():
    from app.quantum import grover_ibm as gi
    from app.quantum.ibm_runner import HardwareOptions, NotApproved

    class RealLooking:  # not a FakeBackendV2, so it counts as a real device
        name = "ibm_fake_real"

    with pytest.raises(NotApproved):
        gi.submit([], RealLooking(), HardwareOptions(), confirm=False)
