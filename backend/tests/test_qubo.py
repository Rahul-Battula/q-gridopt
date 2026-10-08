import itertools
import random

import numpy as np
import pytest

from app.classical.exact import solve_exact
from app.grid.dispatch import dispatch_from_soc_path
from app.grid.evaluator import evaluate
from app.grid.presets import load_preset
from app.grid.tiers import TIERS
from app.models.grid import Battery, Period, Scenario
from app.quantum.ising import ising_energies, qiskit_reference_ising, qubo_to_ising
from app.quantum.qubo import PENALTY_FACTOR, build_qubo

ALL_TIERS = ["Q3", "Q9", "Q18"]


@pytest.fixture(scope="module")
def models():
    return {(p, t): build_qubo(load_preset(p), t)
            for p in ("scenario_a", "scenario_b") for t in ALL_TIERS}


@pytest.mark.parametrize("tier,qubits", [("Q3", 3), ("Q9", 9), ("Q18", 18)])
def test_qubit_counts(models, tier, qubits):
    m = models[("scenario_b", tier)]
    assert m.num_qubits == qubits
    assert m.program.get_num_vars() == qubits
    assert m.one_hot == (tier != "Q3")


# ---------- REQUIRED: exhaustive QUBO energy vs shared evaluator ----------

@pytest.mark.parametrize("preset", ["scenario_a", "scenario_b"])
@pytest.mark.parametrize("tier", ALL_TIERS)
def test_energy_equals_evaluator_for_every_valid_bitstring(models, preset, tier):
    """Every bitstring with exactly one battery level per hour:
    feasible path      -> QUBO energy == evaluator $ objective
    rule-breaking path -> QUBO energy == evaluator $ objective + A x (number of bad hours)"""
    sc, m = load_preset(preset), models[(preset, tier)]
    checked = 0
    for path in itertools.product(m.levels, repeat=m.num_periods):
        x = m.encode(path)
        assert m.decode(x) == list(path)
        ev = evaluate(sc, dispatch_from_soc_path(sc, path))
        bad_hours = len({v.period for v in ev.violations})
        expected = ev.objective + m.penalty * bad_hours
        assert m.energy(x) == pytest.approx(expected, rel=1e-12, abs=1e-6), path
        assert m.program.objective.evaluate(x) == pytest.approx(expected, rel=1e-12, abs=1e-6)
        if ev.feasible:
            assert m.energy(x) == pytest.approx(ev.objective, rel=1e-12, abs=1e-6)
        checked += 1
    assert checked == len(m.levels) ** m.num_periods  # 8, 27, 216


def test_rate_breaking_paths_are_penalised(models):
    m = models[("scenario_b", "Q9")]
    sc = load_preset("scenario_b")
    path = [40, 40, 40]  # 0 -> 40 in the first hour breaks the 30 MW rate
    ev = evaluate(sc, dispatch_from_soc_path(sc, path))
    assert {v.kind for v in ev.violations} == {"charge_rate"}
    assert m.energy(m.encode(path)) == pytest.approx(ev.objective + m.penalty)


# ---------- ground state = cheapest valid path, over ALL 2^n bitstrings ----------

@pytest.mark.parametrize("preset,best", [("scenario_b", [0, 20, 0]), ("scenario_a", [0, 0, 0])])
@pytest.mark.parametrize("tier", ALL_TIERS)
def test_ground_state_is_optimal_schedule(models, preset, best, tier):
    m = models[(preset, tier)]
    e = m.energies_all()
    exact = solve_exact(load_preset(preset), TIERS[tier], tier)
    k = int(np.argmin(e))
    x = [(k >> i) & 1 for i in range(m.num_qubits)]
    assert m.decode(x) == best
    assert e[k] == pytest.approx(exact.evaluation.objective)
    assert np.sum(np.isclose(e, e[k])) == 1  # unique ground state


@pytest.mark.parametrize("tier", ["Q9", "Q18"])
def test_invalid_one_hot_costs_at_least_penalty(models, tier):
    m = models[("scenario_b", tier)]
    e = m.energies_all()
    for k in range(len(e)):
        x = [(k >> i) & 1 for i in range(m.num_qubits)]
        if m.decode(x) is None:
            assert e[k] >= m.penalty - 1e-6


def test_default_penalty_rule(models):
    m = models[("scenario_b", "Q9")]
    sc = load_preset("scenario_b")
    worst = max(evaluate(sc, dispatch_from_soc_path(sc, p)).objective
                for p in itertools.product(m.levels, repeat=3))
    assert m.penalty == pytest.approx(PENALTY_FACTOR * worst)


def test_custom_penalty():
    m = build_qubo(load_preset("scenario_b"), "Q9", penalty=50_000)
    assert m.penalty == 50_000
    assert m.energy([0] * 9) == pytest.approx(3 * 50_000)  # no level chosen in any hour


def test_levels_outside_capacity_rejected():
    sc = load_preset("scenario_b")
    sc.battery = Battery(capacity=30)
    with pytest.raises(ValueError):
        build_qubo(sc, "Q9")  # level 40 > capacity 30


# ---------- Ising conversion ----------

@pytest.mark.parametrize("tier", ALL_TIERS)
def test_ising_matches_qiskit_optimization(models, tier):
    m = models[("scenario_b", tier)]
    op, offset = qubo_to_ising(m)
    ref_op, ref_offset = qiskit_reference_ising(m)
    diff = (op - ref_op).simplify(atol=1e-6)
    assert np.allclose(diff.coeffs, 0, atol=1e-6)
    assert offset == pytest.approx(ref_offset)


@pytest.mark.parametrize("tier", ALL_TIERS)
def test_ising_energy_equals_qubo_energy_for_all_bitstrings(models, tier):
    m = models[("scenario_b", tier)]
    op, offset = qubo_to_ising(m)
    assert op.num_qubits == m.num_qubits
    assert not op.paulis.x.any()  # diagonal: only I and Z
    assert np.allclose(ising_energies(op, offset), m.energies_all(), rtol=1e-12, atol=1e-6)


def test_q3_hamiltonian_has_chain_couplings_only(models):
    op, _ = qubo_to_ising(models[("scenario_b", "Q3")])
    pairs = {tuple(np.flatnonzero(z)) for z in op.paulis.z if z.sum() == 2}
    assert pairs <= {(0, 1), (1, 2)}  # hour 1-2 and hour 2-3 only: hardware-friendly


# ---------- random scenarios: ground state agrees with the exact enumerator ----------

@pytest.mark.parametrize("seed", range(8))
def test_random_scenarios_ground_state(seed):
    rng = random.Random(seed)
    sc = Scenario(
        name=f"random_{seed}",
        periods=[Period(name=f"t{i}", demand=rng.uniform(20, 200), solar=rng.uniform(0, 150),
                        wind=rng.uniform(0, 80)) for i in range(3)],
        gas_max=rng.uniform(50, 150),
        battery=Battery(capacity=50, max_rate=rng.uniform(10, 40),
                        efficiency=rng.choice([1.0, 0.9])),
    )
    try:
        exact = solve_exact(sc, TIERS["Q9"], "Q9")
    except ValueError:
        pytest.skip("no feasible path for this random scenario")
    m = build_qubo(sc, "Q9")
    assert m.energies_all().min() == pytest.approx(exact.evaluation.objective, abs=1e-6)
