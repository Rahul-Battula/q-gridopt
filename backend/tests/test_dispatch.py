import pytest

from app.grid.dispatch import (
    dispatch_from_flows,
    dispatch_from_soc_path,
    dispatch_no_battery,
    dispatch_period,
)
from app.grid.presets import load_preset
from app.models.grid import Battery, Period, Scenario


def test_deficit_uses_renewables_then_gas():
    x = dispatch_period(Period(name="t", demand=80, solar=30, wind=20), 100, 0, 0)
    assert (x.solar, x.wind, x.gas, x.unserved) == (30, 20, 30, 0)


def test_surplus_is_curtailed_solar_used_before_wind():
    x = dispatch_period(Period(name="t", demand=40, solar=30, wind=20), 100, 0, 0)
    assert (x.solar, x.wind, x.gas) == (30, 10, 0)


def test_gas_cap_leaves_unserved():
    x = dispatch_period(Period(name="t", demand=200, solar=10, wind=40), 100, 0, 0)
    assert (x.gas, x.unserved) == (100, 50)


def test_charge_absorbs_surplus():
    x = dispatch_period(Period(name="t", demand=120, solar=120, wind=20), 100, 20, 0)
    assert (x.solar, x.wind, x.gas, x.charge) == (120, 20, 0, 20)


def test_discharge_reduces_gas():
    x = dispatch_period(Period(name="t", demand=150, solar=10, wind=40), 100, 0, 20)
    assert (x.gas, x.discharge, x.unserved) == (80, 20, 0)


def test_soc_path_matches_expected_optimal_schedule():
    sched = dispatch_from_soc_path(load_preset("scenario_b"), [0, 20, 0])
    got = [(p.solar, p.wind, p.gas, p.charge, p.discharge, p.unserved) for p in sched.periods]
    assert got == [
        (30, 20, 30, 0, 0, 0),    # Morning
        (120, 20, 0, 20, 0, 0),   # Afternoon: 20 MW of solar into the battery
        (10, 40, 80, 0, 20, 0),   # Evening: battery covers 20 MW
    ]


def test_no_battery_schedule():
    sched = dispatch_no_battery(load_preset("scenario_b"))
    assert [p.gas for p in sched.periods] == [30, 0, 100]
    assert all(p.charge == 0 and p.discharge == 0 for p in sched.periods)


def test_efficiency_scales_charge_drawn_from_grid():
    base = load_preset("scenario_b")
    sc = base.model_copy(update={"battery": Battery(efficiency=0.8)})
    sched = dispatch_from_flows(sc, [0, 20, -20])
    assert sched.periods[1].charge == pytest.approx(25)  # 25 MWh in -> 20 MWh stored
    assert sched.periods[2].discharge == 20


def test_wrong_length_rejected():
    with pytest.raises(ValueError):
        dispatch_from_flows(load_preset("scenario_b"), [0, 0])


def test_scenario_validation():
    with pytest.raises(ValueError):
        Battery(capacity=10, initial_soc=20)
    with pytest.raises(ValueError):
        Scenario(name="x", periods=[])
