import itertools
import random

import pytest

from app.classical.exact import enumerate_paths, solve_exact
from app.classical.lp import solve_lp
from app.grid.dispatch import dispatch_from_soc_path
from app.grid.evaluator import evaluate
from app.grid.presets import load_preset
from app.grid.tiers import TIERS
from app.models.grid import Battery, Period, Scenario


def count_rate_feasible(levels, periods, start, rate):
    """Independent count (no evaluator): paths whose every step is within the rate limit."""
    n = 0
    for path in itertools.product(levels, repeat=periods):
        steps = zip([start, *path[:-1]], path)
        n += all(abs(b - a) <= rate for a, b in steps)
    return n


@pytest.mark.parametrize("tier", ["Q3", "Q9", "Q18"])
def test_every_tier_finds_9175_on_scenario_b(tier):
    r = solve_exact(load_preset("scenario_b"), TIERS[tier], tier)
    assert r.source == "classical_exact"
    assert r.evaluation.objective == pytest.approx(9175)
    assert r.details["best_path"] == [0, 20, 0]
    assert r.details["optimal_paths"] == [[0, 20, 0]]  # unique optimum


@pytest.mark.parametrize("tier,n_paths", [("Q3", 8), ("Q9", 27), ("Q18", 216)])
def test_path_counts(tier, n_paths):
    sc = load_preset("scenario_b")
    r = solve_exact(sc, TIERS[tier], tier)
    assert r.details["n_paths"] == n_paths
    assert r.details["n_feasible"] == count_rate_feasible(
        TIERS[tier], 3, sc.battery.initial_soc, sc.battery.max_rate)


@pytest.mark.parametrize("tier", ["Q3", "Q9", "Q18"])
def test_scenario_a_best_is_idle_battery(tier):
    r = solve_exact(load_preset("scenario_a"), TIERS[tier], tier)
    assert r.evaluation.objective == pytest.approx(11550)
    assert r.details["optimal_paths"] == [[0, 0, 0]]


def test_ranking_is_sorted_and_consistent_with_evaluator():
    sc = load_preset("scenario_b")
    scores = enumerate_paths(sc, TIERS["Q9"])
    feasible = [s for s in scores if s.feasible]
    assert [s.objective for s in feasible] == sorted(s.objective for s in feasible)
    assert all(not s.feasible for s in scores[len(feasible):])  # infeasible at the end
    for s in scores:
        assert evaluate(sc, dispatch_from_soc_path(sc, s.path)).objective == pytest.approx(s.objective)
    # Q9 includes jumps of 40 MWh, faster than the 30 MW rate -> flagged, never chosen
    assert any("charge_rate" in s.violations or "discharge_rate" in s.violations for s in scores)


def test_ties_are_all_reported():
    sc = load_preset("scenario_a")
    sc.costs.discharge_wear = 0  # now charging from gas and discharging later costs the same
    r = solve_exact(sc, TIERS["Q3"], "Q3")
    assert len(r.details["optimal_paths"]) > 1
    assert [0, 0, 0] in r.details["optimal_paths"]


def test_summary_statistics():
    r = solve_exact(load_preset("scenario_b"), TIERS["Q3"], "Q3")
    d = r.details
    assert r.evaluation.objective <= d["mean_feasible_objective"] <= d["worst_feasible_objective"]


def test_no_feasible_path_raises():
    sc = load_preset("scenario_b")
    with pytest.raises(ValueError):
        solve_exact(sc, [40, 50])  # first step from SOC 0 always exceeds the 30 MW rate


@pytest.mark.parametrize("seed", range(10))
def test_exact_never_beats_lp(seed):
    """The LP solves the continuous problem, so a discrete answer can only tie or be worse."""
    rng = random.Random(seed)
    sc = Scenario(
        name=f"random_{seed}",
        periods=[Period(name=f"t{i}", demand=rng.uniform(20, 200), solar=rng.uniform(0, 150),
                        wind=rng.uniform(0, 80)) for i in range(3)],
        gas_max=rng.uniform(50, 150),
        battery=Battery(capacity=50, max_rate=rng.uniform(10, 40)),
    )
    exact = solve_exact(sc, TIERS["Q18"], "Q18")
    assert exact.evaluation.objective >= solve_lp(sc).evaluation.objective - 1e-6
