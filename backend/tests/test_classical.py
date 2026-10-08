import itertools
import random

import pytest

from app.classical.lp import solve_lp
from app.classical.no_battery import solve_no_battery
from app.grid.dispatch import dispatch_from_soc_path
from app.grid.evaluator import evaluate
from app.grid.presets import load_preset
from app.models.grid import Battery, Period, Scenario


def flows(result):
    return [(p.gas, p.charge, p.discharge) for p in result.schedule.periods]


# ---------- LP reproduces the CLAUDE.md targets ----------

def test_lp_scenario_b_is_9175():
    r = solve_lp(load_preset("scenario_b"))
    assert r.source == "classical_lp"
    assert r.evaluation.objective == pytest.approx(9175)
    assert r.evaluation.feasible
    assert r.evaluation.co2_tonnes == pytest.approx(49.5)
    assert r.evaluation.curtailment_mwh == pytest.approx(0, abs=1e-6)
    assert flows(r) == [
        pytest.approx((30, 0, 0), abs=1e-6),
        pytest.approx((0, 20, 0), abs=1e-6),
        pytest.approx((80, 0, 20), abs=1e-6),
    ]


def test_lp_objective_matches_shared_evaluator():
    r = solve_lp(load_preset("scenario_b"))
    assert r.details["solver_status"] == "Optimal"
    assert r.details["solver_objective"] == pytest.approx(r.evaluation.objective)


def test_lp_scenario_a_leaves_battery_idle():
    r = solve_lp(load_preset("scenario_a"))
    assert r.evaluation.objective == pytest.approx(11550)
    assert all(c == pytest.approx(0, abs=1e-6) and d == pytest.approx(0, abs=1e-6)
               for _, c, d in flows(r))


def test_no_battery_scenario_b_is_10925():
    r = solve_no_battery(load_preset("scenario_b"))
    assert r.source == "classical_no_battery"
    assert r.evaluation.objective == pytest.approx(10925)
    assert r.evaluation.curtailment_mwh == pytest.approx(20)


def test_provenance_recorded():
    r = solve_lp(load_preset("scenario_b"))
    assert r.provenance.library_versions["pulp"].startswith("4.")
    assert "CBC" in r.provenance.backend
    assert r.provenance.timestamp.endswith("+00:00")
    assert r.provenance.solve_time_s >= 0


# ---------- LP is a lower bound for every discrete battery path ----------

def test_lp_beats_or_ties_every_discrete_battery_path():
    sc = load_preset("scenario_b")
    lp = solve_lp(sc).evaluation.objective
    levels = range(0, 51, 10)
    checked = 0
    for path in itertools.product(levels, repeat=3):
        ev = evaluate(sc, dispatch_from_soc_path(sc, path))
        if ev.feasible:  # paths faster than the 30 MW rate are invalid, skip them
            assert ev.objective >= lp - 1e-6, path
            checked += 1
    assert checked > 50


# ---------- battery helps when demand exceeds supply ----------

def test_lp_uses_battery_to_cut_unserved_demand():
    sc = load_preset("scenario_b")
    sc.periods[2].demand = 200  # evening: 50 renewables + 100 gas leaves 50 MW short
    nb = solve_no_battery(sc).evaluation
    lp = solve_lp(sc).evaluation
    assert nb.unserved_mwh == pytest.approx(50)
    assert lp.unserved_mwh == pytest.approx(20)  # discharge capped at 30 MW
    assert lp.objective < nb.objective


# ---------- randomised sanity checks ----------

@pytest.mark.parametrize("seed", range(15))
def test_lp_never_worse_than_no_battery(seed):
    rng = random.Random(seed)
    sc = Scenario(
        name=f"random_{seed}",
        periods=[Period(name=f"t{i}", demand=rng.uniform(20, 200), solar=rng.uniform(0, 150),
                        wind=rng.uniform(0, 80)) for i in range(rng.randint(2, 5))],
        gas_max=rng.uniform(50, 150),
        battery=Battery(capacity=rng.uniform(0, 80), max_rate=rng.uniform(0, 40)),
    )
    lp = solve_lp(sc)
    nb = solve_no_battery(sc)
    assert lp.evaluation.feasible
    # abs tolerance: some random scenarios cost ~$0, where a relative check is meaningless
    assert lp.details["solver_objective"] == pytest.approx(lp.evaluation.objective, abs=1e-6)
    assert lp.evaluation.objective <= nb.evaluation.objective + 1e-6
