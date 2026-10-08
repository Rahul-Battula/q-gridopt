import numpy as np
import pytest

from app.classical.annealing import anneal, samples_to_counts, solve_annealing
from app.grid.presets import load_preset
from app.quantum import decoder
from app.quantum.qubo import build_qubo


def test_counts_use_qiskit_key_order():
    samples = np.array([[0, 1, 0], [0, 1, 0], [1, 0, 0]], dtype=np.int8)  # x0 is column 0
    assert samples_to_counts(samples) == {"010": 2, "001": 1}  # x0 is the RIGHTMOST bit


def test_anneal_energies_match_model():
    model = build_qubo(load_preset("scenario_b"), "Q9")
    x = anneal(model, reads=64, sweeps=20, seed=3)
    assert x.shape == (64, 9) and set(np.unique(x)) <= {0, 1}
    e_all = model.energies_all()
    for row in x[:10]:
        assert model.energy(list(row)) == pytest.approx(e_all[decoder.index_of(list(row))])


@pytest.mark.parametrize("tier", ["Q3", "Q9", "Q18"])
def test_annealing_finds_optimum_on_scenario_b(tier):
    r = solve_annealing(load_preset("scenario_b"), tier, reads=512, seed=1)
    assert r.source == "classical_annealing"
    assert r.details["best_found"]["path"] == [0, 20, 0]
    assert r.evaluation.objective == pytest.approx(9175)
    assert sum(h["count"] for h in r.details["histogram"]) <= 512


def test_annealing_reproducible():
    a = solve_annealing(load_preset("scenario_b"), "Q9", reads=256, seed=7)
    b = solve_annealing(load_preset("scenario_b"), "Q9", reads=256, seed=7)
    assert a.details["histogram"] == b.details["histogram"]


def test_more_sweeps_do_not_hurt():
    sc = load_preset("scenario_b")
    short = solve_annealing(sc, "Q18", reads=1024, sweeps=2, seed=0).details["qaoa_sampled"]["p_optimal"]
    long = solve_annealing(sc, "Q18", reads=1024, sweeps=200, seed=0).details["qaoa_sampled"]["p_optimal"]
    assert long >= short
