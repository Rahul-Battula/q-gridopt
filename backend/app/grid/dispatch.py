"""Merit-order dispatch: given what the battery does, fill in every other resource.

Per period, with battery charge c and discharge d:
    net load = demand + c - d
    1. solar, then wind (both free) up to what is available
    2. gas up to gas_max
    3. anything still missing is unserved
    4. renewables not needed are curtailed
Solar is used before wind; both have zero cost, so the order changes only which one is
reported as curtailed, never the objective.

This rule is how QAOA results become full schedules: QAOA picks the battery path,
dispatch fills in the rest.

With unit commitment (scenario.unit_commitment) the gas unit must be ON to produce, and while on it
runs at least min_output. The commitment is either given (gas_on=True/False: QAOA, exact and LP
choose it) or, when not given, derived: on exactly when gas is needed. If the unit is on and its
minimum output exceeds what is needed, renewables are curtailed to make room; if even that cannot
balance (min output above the whole net load) the schedule has a balance violation.
"""

from collections.abc import Sequence

from app.models.grid import Period, PeriodDispatch, Scenario, Schedule, UnitCommitment

TOL = 1e-6


def dispatch_period(period: Period, gas_max: float, charge: float, discharge: float,
                    unit: UnitCommitment | None = None, gas_on: bool | None = None) -> PeriodDispatch:
    net_load = period.demand + charge - discharge
    remaining = max(net_load, 0.0)

    if unit is None:
        solar = min(period.solar, remaining)
        remaining -= solar
        wind = min(period.wind, remaining)
        remaining -= wind
        gas = min(gas_max, remaining)
        remaining -= gas
        return PeriodDispatch(
            solar=solar, wind=wind, gas=gas, charge=charge, discharge=discharge, unserved=remaining
        )

    needed = max(remaining - period.solar - period.wind, 0.0)  # gas needed after all renewables
    on = (needed > TOL) if gas_on is None else gas_on
    gas = min(gas_max, max(needed, unit.min_output)) if on else 0.0
    solar = min(period.solar, max(remaining - gas, 0.0))
    wind = min(period.wind, max(remaining - gas - solar, 0.0))
    unserved = max(remaining - gas - solar - wind, 0.0)
    return PeriodDispatch(solar=solar, wind=wind, gas=gas, charge=charge, discharge=discharge,
                          unserved=unserved, gas_on=on)


def battery_flows(soc_change: float, efficiency: float) -> tuple[float, float]:
    """(charge, discharge) drawn from / delivered to the grid for a given SOC change.
    Charging draws change/efficiency from the grid."""
    charge = soc_change / efficiency if soc_change > 0 else 0.0
    discharge = -soc_change if soc_change < 0 else 0.0
    return charge, discharge


def dispatch_from_flows(scenario: Scenario, soc_changes: Sequence[float],
                        commits: Sequence[bool] | None = None) -> Schedule:
    """soc_changes[t] = change in battery state of charge during period t (MWh).
    Positive = charging, negative = discharging. commits[t] = gas unit on in period t
    (only with unit commitment; omitted = derived from need)."""
    if len(soc_changes) != len(scenario.periods):
        raise ValueError(
            f"expected {len(scenario.periods)} battery changes, got {len(soc_changes)}"
        )
    if commits is not None and len(commits) != len(scenario.periods):
        raise ValueError(f"expected {len(scenario.periods)} commitments, got {len(commits)}")
    periods = []
    for t, (period, delta) in enumerate(zip(scenario.periods, soc_changes)):
        charge, discharge = battery_flows(delta, scenario.battery.efficiency)
        periods.append(dispatch_period(period, scenario.gas_max, charge, discharge,
                                       scenario.unit_commitment, None if commits is None else commits[t]))
    return Schedule(periods=periods)


def dispatch_from_soc_path(scenario: Scenario, soc_path: Sequence[float],
                           commits: Sequence[bool] | None = None) -> Schedule:
    """soc_path[t] = battery state of charge at the END of period t (MWh)."""
    previous = [scenario.battery.initial_soc, *soc_path[:-1]]
    return dispatch_from_flows(scenario, [b - a for a, b in zip(previous, soc_path)], commits)


def dispatch_no_battery(scenario: Scenario) -> Schedule:
    return dispatch_from_flows(scenario, [0.0] * len(scenario.periods))
