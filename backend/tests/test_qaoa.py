import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorEstimator

from app.grid.presets import load_preset
from app.quantum import aer_runner, decoder
from app.quantum.ising import qubo_to_ising
from app.quantum.qaoa import (
    build_ansatz,
    expectation,
    interp_init,
    make_cost_operator,
    parameter_values,
)
from app.quantum.qubo import build_qubo
from app.quantum.simulate import run_qaoa_simulation


def cost_for(tier, preset="scenario_b"):
    model = build_qubo(load_preset(preset), tier)
    op, offset = qubo_to_ising(model)
    return model, make_cost_operator(op, offset)


# ---------- the approved deviation: Aer exact estimator == Qiskit reference estimator ----------

@pytest.mark.parametrize("tier", ["Q3", "Q9"])
@pytest.mark.parametrize("reps", [1, 2])
def test_aer_exact_estimator_matches_statevector_estimator(tier, reps):
    _, cost = cost_for(tier)
    circuit = build_ansatz(cost, reps)
    vals = np.random.default_rng(0).uniform(-np.pi, np.pi, (6, circuit.num_parameters))
    ours = expectation(circuit, cost.hamiltonian, vals)
    ref = StatevectorEstimator().run([(circuit, cost.hamiltonian, vals)]).result()[0].data.evs
    assert np.allclose(ours, ref, atol=1e-10)


# ---------- circuit and parameter conventions ----------

def test_parameters_bound_by_name():
    _, cost = cost_for("Q3")
    circuit = build_ansatz(cost, 2)
    assert sorted(p.name for p in circuit.parameters) == ["β[0]", "β[1]", "γ[0]", "γ[1]"]
    vals = parameter_values(circuit, gammas=[1.0, 2.0], betas=[3.0, 4.0])
    by_name = dict(zip((p.name for p in circuit.parameters), vals))
    assert by_name == {"γ[0]": 1.0, "γ[1]": 2.0, "β[0]": 3.0, "β[1]": 4.0}


def test_scaling_preserves_energies():
    model, cost = cost_for("Q9")
    assert np.max(np.abs(cost.hamiltonian.coeffs)) == pytest.approx(1.0)
    # zero angles = uniform superposition, so <H> in $ must equal the mean over all bitstrings
    circuit = build_ansatz(cost, 1)
    e0 = expectation(circuit, cost.hamiltonian, parameter_values(circuit, [0.0], [0.0]))
    assert cost.to_dollars(float(e0)) == pytest.approx(model.energies_all().mean())


def test_interp_init():
    g, b = interp_init([1.0], [0.5])
    assert g == pytest.approx([1.0, 1.0]) and b == pytest.approx([0.5, 0.5])
    g, _ = interp_init([1.0, 3.0], [0.0, 0.0])
    assert g == pytest.approx([1.0, 2.0, 3.0])  # ends kept, middle = average of neighbours


# ---------- decoding: Qiskit bit order end to end ----------

def test_counts_key_decodes_to_right_path():
    model, _ = cost_for("Q3")
    x = model.encode([0, 20, 0])  # variable 1 set -> qubit 1
    assert x == [0, 1, 0]
    qc = QuantumCircuit(3)
    qc.x(1)
    counts = aer_runner.sample_ideal(qc, np.array([]), shots=50, seed=1)
    assert counts == {"010": 50}  # Qiskit prints qubit 0 rightmost
    probs = decoder.counts_to_probabilities(counts, 3)
    table = decoder.path_table(load_preset("scenario_b"), model)
    found = decoder.best_found(probs, table)
    assert list(found.path) == [0, 20, 0] and found.objective == pytest.approx(9175)


def test_index_of_handles_numpy_small_ints():
    x = np.zeros(18, dtype=np.int8)
    x[17] = 1
    assert decoder.index_of(list(x)) == 1 << 17


def test_histogram_decodes_bitstrings():
    sc = load_preset("scenario_b")
    model = build_qubo(sc, "Q9")
    table = decoder.path_table(sc, model)
    opt_key = format(decoder.index_of(model.encode([0, 20, 0])), "09b")
    rows = decoder.histogram({opt_key: 30, "000000000": 10}, table)
    assert rows[0] == {"bitstring": opt_key, "count": 30, "probability": 0.75, "path": [0, 20, 0],
                       "objective": pytest.approx(9175), "feasible": True, "optimal": True}
    assert rows[1]["path"] is None and not rows[1]["feasible"] and not rows[1]["optimal"]


def test_exact_probabilities_match_basis_state():
    qc = QuantumCircuit(3)
    qc.x(0)
    qc.x(2)
    probs = aer_runner.exact_probabilities(qc, np.array([]))
    assert probs[0b101] == pytest.approx(1.0)


def test_uniform_stats_are_analytic():
    model, _ = cost_for("Q9")
    table = decoder.path_table(load_preset("scenario_b"), model)
    stats = decoder.distribution_stats(np.full(512, 1 / 512), table)
    assert stats["p_valid"] == pytest.approx(27 / 512)
    assert stats["p_feasible"] == pytest.approx(12 / 512)
    assert stats["p_optimal"] == pytest.approx(1 / 512)


# ---------- end to end (small tiers; Q18 is exercised by the script) ----------

@pytest.fixture(scope="module")
def q3_run():
    return run_qaoa_simulation(load_preset("scenario_b"), "Q3", reps=1, shots=2048, seed=11)


def test_q3_end_to_end(q3_run):
    result, trained = q3_run
    d = result.details
    assert result.source == "aer_statevector"
    assert result.provenance.shots == 2048
    assert "qiskit-aer" in result.provenance.library_versions
    assert sum(d["top_counts"].values()) <= 2048
    # training can never do worse than zero angles (uniform superposition), which is in the grid
    assert trained.energy_dollars <= d["random_exact"]["expected_cost_if_feasible"] + 1e-6
    # QAOA concentrates probability on the optimum compared with random guessing
    assert d["qaoa_exact"]["p_optimal"] > d["random_exact"]["p_optimal"]
    # reported schedule is the best feasible sampled path, scored by the shared evaluator
    assert result.evaluation.objective == pytest.approx(d["best_found"]["objective"])
    assert d["best_found"]["objective"] >= d["optimal_objective"] - 1e-6


def test_sampled_close_to_exact(q3_run):
    d = q3_run[0].details
    assert d["qaoa_sampled"]["p_optimal"] == pytest.approx(d["qaoa_exact"]["p_optimal"], abs=0.05)


def test_reproducible_with_seed():
    a, _ = run_qaoa_simulation(load_preset("scenario_b"), "Q3", reps=1, shots=512, seed=5)
    b, _ = run_qaoa_simulation(load_preset("scenario_b"), "Q3", reps=1, shots=512, seed=5)
    assert a.details["top_counts"] == b.details["top_counts"]
    assert a.details["gammas"] == b.details["gammas"]
