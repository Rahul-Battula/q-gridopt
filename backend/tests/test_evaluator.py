import pytest

from app.grid.dispatch import dispatch_from_soc_path, dispatch_no_battery
from app.grid.evaluator import evaluate
from app.grid.presets import DEFAULT_PRESET, list_presets, load_preset
from app.models.grid import PeriodDispatch, Schedule

# The optimal Scenario B schedule from CLAUDE.md, written out by hand (not produced by dispatch).
OPTIMAL_B = Schedule(periods=[
    PeriodDispatch(solar=30, wind=20, gas=30),
    PeriodDispatch(solar=120, wind=20, gas=0, charge=20),
    PeriodDispatch(solar=10, wind=40, gas=80, discharge=20),
])


def kinds(ev):
    return {v.kind for v in ev.violations}


# ---------- presets ----------

def test_presets_load():
    presets = list_presets()
    assert set(presets) == {"scenario_a", "scenario_b", "scenario_c"}
    assert DEFAULT_PRESET == "scenario_b"
    b = presets["scenario_b"]
    assert [(p.demand, p.solar, p.wind) for p in b.periods] == [(80, 30, 20), (120, 120, 20), (150, 10, 40)]
    assert presets["scenario_a"].periods[1].solar == 90
    assert (b.gas_max, b.battery.capacity, b.battery.max_rate, b.battery.initial_soc) == (100, 50, 30, 0)


def test_unknown_preset():
    with pytest.raises(KeyError):
        load_preset("nope")


# ---------- the two target numbers from CLAUDE.md ----------

def test_optimal_schedule_scenario_b_is_9175():
    ev = evaluate(load_preset("scenario_b"), OPTIMAL_B)
    assert ev.objective == pytest.approx(9175)
    assert ev.gas_cost == pytest.approx(6600)
    assert ev.co2_cost == pytest.approx(2475)
    assert ev.wear_cost == pytest.approx(100)
    assert ev.curtailment_cost == 0 and ev.unserved_cost == 0
    assert ev.co2_tonnes == pytest.approx(49.5)
    assert ev.curtailment_mwh == 0
    assert ev.renewable_utilization == pytest.approx(1.0)
    assert ev.soc_trajectory == [0, 20, 0]
    assert ev.feasible


def test_dispatch_of_battery_path_gives_same_9175():
    sc = load_preset("scenario_b")
    assert evaluate(sc, dispatch_from_soc_path(sc, [0, 20, 0])).objective == pytest.approx(9175)


def test_no_battery_scenario_b_is_10925():
    ev = evaluate(load_preset("scenario_b"), dispatch_no_battery(load_preset("scenario_b")))
    assert ev.objective == pytest.approx(10925)
    assert ev.gas_mwh == pytest.approx(130)
    assert ev.curtailment_mwh == pytest.approx(20)
    assert ev.curtailment_cost == pytest.approx(200)
    assert ev.renewable_available_mwh == pytest.approx(240)  # 50 + 140 + 50
    assert ev.renewable_utilization == pytest.approx(220 / 240)
    assert ev.feasible


# ---------- Scenario A: battery has nothing to store (derived by hand: gas 30+10+100) ----------

def test_scenario_a_no_battery_is_11550():
    sc = load_preset("scenario_a")
    ev = evaluate(sc, dispatch_no_battery(sc))
    assert ev.gas_mwh == pytest.approx(140)
    assert ev.objective == pytest.approx(140 * 60 + 140 * 0.45 * 50)  # 11,550


def test_scenario_a_battery_does_not_help():
    sc = load_preset("scenario_a")
    # Charging 20 in the afternoon now has to come from gas; it only adds wear cost.
    ev = evaluate(sc, dispatch_from_soc_path(sc, [0, 20, 0]))
    assert ev.objective == pytest.approx(11550 + 100)


# ---------- unserved demand is penalised, not a violation ----------

def test_unserved_cost():
    sc = load_preset("scenario_b")
    sc.periods[2].demand = 200  # gas cap 100 + renewables 50 -> 50 MW unserved
    ev = evaluate(sc, dispatch_no_battery(sc))
    assert ev.unserved_mwh == pytest.approx(50)
    assert ev.unserved_cost == pytest.approx(50_000)
    assert ev.feasible


# ---------- violations are reported, never silently fixed ----------

def test_violations_detected():
    sc = load_preset("scenario_b")
    bad = Schedule(periods=[
        PeriodDispatch(solar=40, wind=20, gas=20),                  # solar over available (30)
        PeriodDispatch(solar=120, wind=20, gas=0, charge=40),       # wrong balance + over rate
        PeriodDispatch(solar=10, wind=40, gas=130, discharge=-30),  # gas over max, negative
    ])
    ev = evaluate(sc, bad)
    assert not ev.feasible
    assert {"solar_available", "charge_rate", "balance", "gas_max", "negative"} <= kinds(ev)


def test_soc_limits():
    sc = load_preset("scenario_b")
    over = Schedule(periods=[PeriodDispatch(gas=50, charge=30, solar=30, wind=20, unserved=10)] * 2
                    + [PeriodDispatch(solar=10, wind=40, gas=100)])
    assert "soc_max" in kinds(evaluate(sc, over))  # 30 + 30 = 60 > 50

    under = Schedule(periods=[PeriodDispatch(solar=30, wind=20, gas=10, discharge=20)]
                     + [PeriodDispatch(solar=100, wind=20)] + [PeriodDispatch(solar=10, wind=40, gas=100)])
    assert "soc_min" in kinds(evaluate(sc, under))  # discharge from an empty battery


def test_wrong_length_raises():
    with pytest.raises(ValueError):
        evaluate(load_preset("scenario_b"), Schedule(periods=OPTIMAL_B.periods[:2]))


def test_costs_are_configurable():
    sc = load_preset("scenario_b")
    sc.costs.carbon_price = 100
    ev = evaluate(sc, OPTIMAL_B)
    assert ev.co2_cost == pytest.approx(4950)
    assert ev.objective == pytest.approx(9175 + 2475)
