"""Unit commitment, forecast uncertainty and reserve requirement (optional scenario features).

Hand-checked numbers use Scenario B's Morning (demand 80, solar 30, wind 20) with the default cost
weights: gas costs 60 + 50 x 0.45 = $82.5 per MWh.
"""

import itertools

import numpy as np
import pytest

from app.classical.exact import solve_exact
from app.classical.lp import solve_lp
from app.classical.no_battery import solve_no_battery
from app.grid.dispatch import dispatch_from_soc_path, dispatch_period
from app.grid.evaluator import evaluate
from app.grid.presets import load_preset
from app.grid.tiers import TIERS
from app.models.grid import (
    ForecastCase,
    Period,
    PeriodDispatch,
    Reserve,
    Schedule,
    Uncertainty,
    UnitCommitment,
)
from app.quantum import decoder
from app.quantum.qubo import build_qubo

B = load_preset("scenario_b")
C = load_preset("scenario_c")
UNIT = UnitCommitment(min_output=40, startup_cost=800, initial_on=False)
MORNING = B.periods[0]  # needs 30 MW of gas after renewables


# ---------- nothing changes when the features are off ----------

def test_legacy_scenarios_have_no_extensions_and_old_numbers():
    ev = evaluate(B, dispatch_from_soc_path(B, [0, 20, 0]))
    assert ev.objective == pytest.approx(9175)
    assert (ev.startup_cost, ev.reserve_cost, ev.startups, ev.cases) == (0.0, 0.0, 0, [])
    assert ev.worst_case_objective is None


# ---------- unit commitment ----------

def test_dispatch_derives_commitment_and_enforces_minimum_output():
    x = dispatch_period(MORNING, 100, 0, 0, UNIT)  # gas needed: 30 < min 40
    assert x.gas_on is True
    assert x.gas == 40  # runs at its minimum
    assert x.solar + x.wind == pytest.approx(40)  # 10 MW of renewables curtailed to make room
    assert x.unserved == 0


def test_off_unit_cannot_serve_load_and_unneeded_unit_stays_off():
    off = dispatch_period(MORNING, 100, 0, 0, UNIT, gas_on=False)
    assert off.gas == 0 and off.unserved == pytest.approx(30)
    afternoon = B.periods[1]  # renewables cover the load: no gas needed
    assert dispatch_period(afternoon, 100, 0, 0, UNIT).gas_on is False


def test_startup_cost_and_commitment_costs_in_evaluator():
    sc = B.model_copy(update={"unit_commitment": UNIT})
    ev = evaluate(sc, dispatch_from_soc_path(sc, [0, 0, 0], [True, True, True]))
    assert ev.startups == 1 and ev.startup_cost == 800  # started once, stays on
    assert ev.feasible
    # off in the afternoon forces a second start in the evening
    ev2 = evaluate(sc, dispatch_from_soc_path(sc, [0, 0, 0], [True, False, True]))
    assert ev2.startups == 2 and ev2.startup_cost == 1600
    # morning: gas 40 at $82.5 + 10 MW curtailed at $10
    assert ev.periods[0].gas_cost + ev.periods[0].co2_cost == pytest.approx(40 * 82.5)
    assert ev.periods[0].curtailment_cost == pytest.approx(10 * 10)


def test_initial_on_avoids_the_first_startup():
    sc = B.model_copy(update={"unit_commitment": UNIT.model_copy(update={"initial_on": True})})
    ev = evaluate(sc, dispatch_from_soc_path(sc, [0, 0, 0], [True, True, True]))
    assert ev.startups == 0 and ev.startup_cost == 0


def test_evaluator_reports_commitment_rule_breaks():
    sc = B.model_copy(update={"unit_commitment": UNIT})
    below_min = Schedule(periods=[
        PeriodDispatch(solar=30, wind=20, gas=30, gas_on=True),  # 30 < 40 minimum
        *dispatch_from_soc_path(sc, [0, 0, 0], [True, True, True]).periods[1:]])
    assert "min_output" in {v.kind for v in evaluate(sc, below_min).violations}
    off_but_producing = Schedule(periods=[
        PeriodDispatch(solar=30, wind=20, gas=30, gas_on=False),
        *dispatch_from_soc_path(sc, [0, 0, 0], [True, True, True]).periods[1:]])
    assert "gas_off" in {v.kind for v in evaluate(sc, off_but_producing).violations}


def test_minimum_output_above_net_load_is_a_balance_violation():
    sc = B.model_copy(update={"unit_commitment": UnitCommitment(min_output=100, startup_cost=0)})
    ev = evaluate(sc, dispatch_from_soc_path(sc, [0, 0, 0], [True, True, True]))  # morning load is 80
    assert "balance" in {v.kind for v in ev.violations}


def test_min_output_cannot_exceed_gas_max():
    with pytest.raises(ValueError, match="min_output"):
        B.model_copy(update={"unit_commitment": UnitCommitment(min_output=150)}).model_validate(
            {**B.model_dump(), "unit_commitment": {"min_output": 150}})


# ---------- forecast uncertainty ----------

def test_expected_cost_is_the_probability_weighted_average():
    cases = [ForecastCase(name="low", probability=0.25, solar_factor=0.5),
             ForecastCase(name="mid", probability=0.75)]
    sc = B.model_copy(update={"uncertainty": Uncertainty(cases=cases)})
    schedule = dispatch_from_soc_path(sc, [0, 20, 0])
    ev = evaluate(sc, schedule)
    by_name = {c.name: c for c in ev.cases}
    assert by_name["mid"].objective == pytest.approx(9175)  # factor 1 = the forecast itself
    assert ev.objective == pytest.approx(0.25 * by_name["low"].objective + 0.75 * by_name["mid"].objective)
    assert by_name["low"].objective > 9175  # less sun -> more gas
    assert ev.worst_case_objective == pytest.approx(by_name["low"].objective)


def test_unserved_energy_appears_when_the_commitment_was_wrong():
    cases = [ForecastCase(name="calm", probability=0.5, solar_factor=0.5, wind_factor=0.5),
             ForecastCase(name="ok", probability=0.5)]
    sc = B.model_copy(update={"unit_commitment": UNIT, "uncertainty": Uncertainty(cases=cases)})
    afternoon_off = evaluate(sc, dispatch_from_soc_path(sc, [0, 0, 0], [True, False, True]))
    afternoon_on = evaluate(sc, dispatch_from_soc_path(sc, [0, 0, 0], [True, True, True]))
    calm_off = {c.name: c for c in afternoon_off.cases}["calm"]
    calm_on = {c.name: c for c in afternoon_on.cases}["calm"]
    # keeping the unit on through the afternoon covers the shortfall (the evening is short either way)
    assert calm_off.unserved_mwh == pytest.approx(calm_on.unserved_mwh + 50)  # afternoon: 120 demand - 70 renewable


def test_probabilities_must_sum_to_one():
    with pytest.raises(ValueError, match="sum to 1"):
        Uncertainty(cases=[ForecastCase(name="a", probability=0.4), ForecastCase(name="b", probability=0.4)])


# ---------- reserve requirement ----------

def test_reserve_shortfall_when_no_spare_capacity():
    sc = B.model_copy(update={"reserve": Reserve(required_fraction=0.1, shortfall_penalty=50)})
    ev = evaluate(sc, dispatch_from_soc_path(sc, [0, 0, 0]))
    # gas headroom: morning 100-30=70, afternoon 100-0, evening 100-100=0 and battery empty
    assert [round(p.reserve_shortfall_mw, 6) for p in ev.periods] == [0, 0, 15]
    assert ev.reserve_cost == pytest.approx(15 * 50)
    assert ev.reserve_shortfall_mwh == pytest.approx(15)
    # the battery's discharge headroom closes the gap: SOC 20 at the end of the evening period
    ev2 = evaluate(sc, dispatch_from_soc_path(sc, [0, 20, 20]))
    assert ev2.periods[2].reserve_shortfall_mw == pytest.approx(0)


# ---------- QUBO <-> evaluator, exhaustive (the required test, extended) ----------

@pytest.fixture(scope="module")
def commit_models():
    return {t: build_qubo(C, t) for t in ("Q3U", "Q9U")}


def test_commit_tier_qubit_counts(commit_models):
    assert commit_models["Q3U"].num_qubits == 12  # 3 hours x 2 levels x on/off
    assert commit_models["Q9U"].num_qubits == 18  # 3 hours x 3 levels x on/off
    assert commit_models["Q3U"].commit and commit_models["Q3U"].one_hot


@pytest.mark.parametrize("tier", ["Q3U", "Q9U"])
def test_energy_equals_evaluator_for_every_valid_state_path(commit_models, tier):
    """Unit commitment + 3 forecast cases + reserve all active (Scenario C)."""
    m = commit_models[tier]
    checked = 0
    for states in itertools.product(m.states, repeat=m.num_periods):
        path = [level for level, _ in states]
        commits = [on for _, on in states]
        x = m.encode(path, commits)
        assert m.decode_states(x) == list(states)
        ev = evaluate(C, dispatch_from_soc_path(C, path, commits))
        bad_hours = len({v.period for v in ev.violations})
        expected = ev.objective + m.penalty * bad_hours
        assert m.energy(x) == pytest.approx(expected, rel=1e-12, abs=1e-6), states
        checked += 1
    assert checked == (2 * len(m.levels)) ** m.num_periods  # 64, 216


@pytest.mark.parametrize("tier", ["Q3U", "Q9U"])
def test_ground_state_is_the_exact_optimum(commit_models, tier):
    m = commit_models[tier]
    e = m.energies_all()
    k = int(np.argmin(e))
    exact = solve_exact(C, TIERS[tier], tier)
    assert e[k] == pytest.approx(exact.evaluation.objective)
    states = m.decode_states([(k >> i) & 1 for i in range(m.num_qubits)])
    assert [level for level, _ in states] == exact.details["best_path"]
    assert [on for _, on in states] == exact.details["best_commits"]
    assert np.sum(np.isclose(e, e[k])) == 1


def test_path_table_carries_commitments(commit_models):
    m = commit_models["Q3U"]
    table = decoder.path_table(C, m)
    assert len(table) == 64
    best = min((i for i in table.values() if i.feasible), key=lambda i: i.objective)
    assert best.commits is not None and len(best.commits) == 3
    assert decoder.schedule_for(C, best).periods[0].gas_on == best.commits[0]


def test_legacy_tiers_are_refused_on_a_unit_commitment_scenario_and_vice_versa():
    with pytest.raises(ValueError, match="Q3U"):
        build_qubo(C, "Q3")
    with pytest.raises(ValueError, match="unit_commitment"):
        build_qubo(B, "Q3U")


# ---------- classical solvers on the extended model ----------

def test_milp_objective_matches_the_evaluator_and_beats_every_discrete_plan():
    lp = solve_lp(C)
    assert lp.details["model"] == "milp"
    assert lp.evaluation.objective == pytest.approx(lp.details["solver_objective"], abs=1e-4)
    assert lp.evaluation.feasible
    for tier in ("Q3U", "Q9U"):
        assert lp.evaluation.objective <= solve_exact(C, TIERS[tier], tier).evaluation.objective + 1e-6


@pytest.mark.parametrize("drop", ["unit_commitment", "uncertainty", "reserve"])
def test_extended_lp_matches_evaluator_with_each_feature_removed(drop):
    sc = C.model_copy(update={drop: None})
    lp = solve_lp(sc)
    assert lp.evaluation.objective == pytest.approx(lp.details["solver_objective"], abs=1e-4)


def test_commitment_aware_plan_beats_the_derived_commitment_baseline():
    """Choosing the gas commitment (and battery) beats a greedy 'on exactly when needed' rule."""
    exact = solve_exact(C, TIERS["Q3U"], "Q3U").evaluation.objective
    greedy = solve_no_battery(C).evaluation.objective
    assert exact < greedy


# ---------- API ----------

def test_api_runs_the_extended_scenario(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(tmp_path / "runs.sqlite")) as client:
        presets = {p["id"]: p for p in client.get("/api/scenarios/presets").json()}
        assert presets["scenario_c"]["scenario"]["unit_commitment"]["min_output"] == 40

        r = client.post("/api/runs/classical", json={"preset": "scenario_c"})
        assert r.status_code == 201
        results = r.json()["results"]
        assert {x["source"] for x in results} == {"classical_lp", "classical_no_battery", "classical_exact"}
        exact = [x for x in results if x["source"] == "classical_exact"]
        assert {x["details"]["tier"] for x in exact} == {"Q3U", "Q9U"}
        assert exact[0]["evaluation"]["startups"] == 1
        assert len(exact[0]["evaluation"]["cases"]) == 3

        preview = client.post("/api/qubo/preview", json={"preset": "scenario_c", "tier": "Q3U",
                                                          "include_circuit": False})
        assert preview.status_code == 200
        body = preview.json()
        assert body["num_qubits"] == 12 and body["unit_commitment"] is True
        assert body["ground_state"]["commits"] == [True, True, True]
        assert {v["gas_on"] for v in body["variables"]} == {True, False}

        bad = client.post("/api/qubo/preview", json={"preset": "scenario_c", "tier": "Q3"})
        assert bad.status_code == 422  # a unit-commitment scenario needs a U tier


def test_commitment_tiers_are_rejected_for_hardware(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(tmp_path / "runs.sqlite")) as client:
        r = client.post("/api/runs/quantum/ibm", json={"preset": "scenario_c", "tier": "Q3U", "backend": "FakeFez"})
        assert r.status_code == 422 and "simulator-only" in r.text
