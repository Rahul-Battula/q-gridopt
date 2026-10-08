import numpy as np
import pytest
from qiskit import QuantumCircuit

from app.grid.presets import load_preset
from app.quantum import decoder
from app.quantum.qubo import build_qubo
from app.quantum.simulate import run_noisy_simulation, run_qaoa_simulation
from app.quantum.transpile import circuit_stats, fake_backend


@pytest.fixture(scope="module")
def q3_table():
    model = build_qubo(load_preset("scenario_b"), "Q3")
    return model, decoder.path_table(load_preset("scenario_b"), model)


@pytest.fixture(scope="module")
def q3_runs():
    ideal, _ = run_qaoa_simulation(load_preset("scenario_b"), "Q3", reps=1, shots=4096, seed=21)
    noisy = run_noisy_simulation(load_preset("scenario_b"), ideal, backend_name="FakeFez")
    return ideal, noisy


# ---------- approximation ratio (user-approved: bad shots count as the worst feasible plan) ----------

def test_ar_uniform_q3_by_hand(q3_table):
    _, table = q3_table
    costs = [9175, 10725, 10925, 11025, 12575, 12875, 30925, 32875]  # Stage 3 ranking, all feasible
    expected = (32875 - np.mean(costs)) / (32875 - 9175)
    stats = decoder.distribution_stats(np.full(8, 1 / 8), table)
    assert stats["approximation_ratio"] == pytest.approx(expected)
    assert stats["approximation_ratio_feasible"] == pytest.approx(expected)  # no bad shots in Q3


def test_ar_extremes(q3_table):
    model, table = q3_table
    best_k = decoder.index_of(model.encode([0, 20, 0]))
    worst_k = decoder.index_of(model.encode([20, 0, 20]))
    p = np.zeros(8)
    p[best_k] = 1
    assert decoder.distribution_stats(p, table)["approximation_ratio"] == pytest.approx(1.0)
    p = np.zeros(8)
    p[worst_k] = 1
    assert decoder.distribution_stats(p, table)["approximation_ratio"] == pytest.approx(0.0)


def test_ar_counts_invalid_shots_as_worst():
    sc = load_preset("scenario_b")
    model = build_qubo(sc, "Q9")
    table = decoder.path_table(sc, model)
    p = np.zeros(512)
    p[decoder.index_of(model.encode([0, 20, 0]))] = 0.5
    p[0] = 0.5  # all-zero bitstring: no level chosen in any hour -> invalid
    stats = decoder.distribution_stats(p, table)
    assert stats["approximation_ratio"] == pytest.approx(0.5)  # half optimal, half worst
    assert stats["approximation_ratio_feasible"] == pytest.approx(1.0)
    p = np.zeros(512)
    p[0] = 1.0
    stats = decoder.distribution_stats(p, table)
    assert stats["approximation_ratio"] == pytest.approx(0.0)
    assert stats["approximation_ratio_feasible"] is None


# ---------- transpilation helpers ----------

def test_circuit_stats():
    qc = QuantumCircuit(3)
    qc.h(0)
    qc.cz(0, 1)
    qc.cz(1, 2)
    qc.rz(0.1, 2)
    s = circuit_stats(qc)
    assert s["two_qubit_gates"] == 2
    assert s["two_qubit_depth"] == 2
    assert s["total_gates"] == 4
    assert s["active_qubits"] == 3


def test_unknown_backend():
    with pytest.raises(ValueError):
        fake_backend("ibm_real_device")


# ---------- noisy runs ----------

def test_noisy_uses_fixed_trained_angles(q3_runs):
    ideal, noisy = q3_runs
    assert noisy.source == "aer_noisy"
    assert noisy.details["gammas"] == ideal.details["gammas"]
    assert noisy.details["betas"] == ideal.details["betas"]
    assert noisy.provenance.backend == "AerSimulator.from_backend(FakeFez)"
    assert "qiskit-ibm-runtime" in noisy.provenance.library_versions


def test_transpiling_preserves_the_distribution(q3_runs):
    """Same transpiled circuit WITHOUT noise reproduces the ideal answer: proves the chip mapping
    and the logical bit order survive transpilation."""
    ideal, noisy = q3_runs
    exact = ideal.details["qaoa_exact"]["p_optimal"]
    assert noisy.details["transpiled_noiseless_sampled"]["p_optimal"] == pytest.approx(exact, abs=0.03)


def test_q3_fits_chip_without_extra_two_qubit_gates(q3_runs):
    ideal, noisy = q3_runs
    assert ideal.details["circuit"]["logical"]["two_qubit_gates"] == \
        noisy.details["circuit"]["transpiled"]["two_qubit_gates"]  # chain couplings: no SWAPs


def test_noisy_still_beats_random_on_q3(q3_runs):
    _, noisy = q3_runs
    d = noisy.details
    assert d["qaoa_sampled"]["p_optimal"] > d["random_exact"]["p_optimal"]
    assert noisy.evaluation.objective == pytest.approx(d["best_found"]["objective"])


def test_noisy_requires_ideal_result(q3_runs):
    _, noisy = q3_runs
    with pytest.raises(ValueError):
        run_noisy_simulation(load_preset("scenario_b"), noisy)
