"""Classical baseline 1: linear program on the continuous model, solved with PuLP + CBC.

This is the true optimum of the continuous problem (battery can take any value, not just
discrete levels), so no other solver can beat it on the same scenario.

Uses the PuLP 4 API: prob.add_variable(...), prob.solve(...) returns LpSolveStats,
CBC is provided by the pulp[cbc] extra and called through COIN_CMD.

With unit commitment, forecast uncertainty or a reserve requirement (scenario fields) the model is
extended and becomes a mixed-integer program (MILP, still CBC): binary gas on/off and start-up
variables for the commitment, one recourse copy of solar/wind/gas/unserved per forecast case (the
battery plan and the commitment are shared by all cases = first-stage decisions), and a reserve
shortfall variable. See _solve_extended.

Note: with charging efficiency < 1 the LP may charge and discharge in the same period to
absorb surplus if that is cheaper than curtailment. At the default efficiency of 1 this
never pays off (it only adds wear cost).
"""

import time

import pulp

from app.grid.dispatch import dispatch_period
from app.grid.evaluator import case_periods, evaluate
from app.models.grid import PeriodDispatch, Scenario, Schedule
from app.models.result import Provenance, SolverResult
from app.provenance import library_versions, utc_now

DECIMALS = 9  # strip floating-point noise from solver output (well below evaluator tolerance)


def solve_lp(scenario: Scenario) -> SolverResult:
    if scenario.unit_commitment or scenario.uncertainty or scenario.reserve:
        return _solve_extended(scenario)
    bat, costs = scenario.battery, scenario.costs
    prob = pulp.LpProblem("grid_dispatch", pulp.LpMinimize)

    rows, objective = [], []
    soc_prev = bat.initial_soc
    for t, p in enumerate(scenario.periods):
        v = {
            "solar": prob.add_variable(f"solar_{t}", lowBound=0, upBound=p.solar),
            "wind": prob.add_variable(f"wind_{t}", lowBound=0, upBound=p.wind),
            "gas": prob.add_variable(f"gas_{t}", lowBound=0, upBound=scenario.gas_max),
            "charge": prob.add_variable(f"charge_{t}", lowBound=0, upBound=bat.max_rate),
            "discharge": prob.add_variable(f"discharge_{t}", lowBound=0, upBound=bat.max_rate),
            "unserved": prob.add_variable(f"unserved_{t}", lowBound=0),
        }
        soc = prob.add_variable(f"soc_{t}", lowBound=0, upBound=bat.capacity)

        prob += (v["solar"] + v["wind"] + v["gas"] + v["discharge"] - v["charge"] + v["unserved"]
                 == p.demand), f"balance_{t}"
        prob += soc == soc_prev + bat.efficiency * v["charge"] - v["discharge"], f"soc_{t}"
        soc_prev = soc

        curtailment = (p.solar - v["solar"]) + (p.wind - v["wind"])
        objective += [
            costs.gas_price * v["gas"],
            costs.carbon_price * costs.emission_factor * v["gas"],
            costs.curtailment_penalty * curtailment,
            costs.discharge_wear * v["discharge"],
            costs.unserved_penalty * v["unserved"],
        ]
        rows.append(v)

    prob += pulp.lpSum(objective)

    start = time.perf_counter()
    stats = prob.solve(pulp.COIN_CMD(msg=False))
    elapsed = time.perf_counter() - start
    if stats.status != pulp.LpSolveStatus.Optimal:
        raise RuntimeError(f"LP not solved to optimality: {stats.status.name}")

    schedule = Schedule(periods=[
        PeriodDispatch(**{k: round(var.value() or 0.0, DECIMALS) + 0.0 for k, var in v.items()})
        for v in rows
    ])

    return SolverResult(
        source="classical_lp",
        scenario_name=scenario.name,
        schedule=schedule,
        evaluation=evaluate(scenario, schedule),
        provenance=Provenance(
            method="Linear program on the continuous model",
            backend="CBC via PuLP COIN_CMD",
            timestamp=utc_now(),
            solve_time_s=elapsed,
            library_versions=library_versions("pulp", "cbcbox"),
        ),
        details={"solver_status": stats.status.name, "solver_objective": pulp.value(prob.objective)},
    )


def _solve_extended(scenario: Scenario) -> SolverResult:
    """Two-stage stochastic MILP: first stage = battery flows + gas commitment, second stage =
    renewable / gas / unserved dispatch per forecast case. The objective is the expected cost."""
    bat, costs, unit, rule = scenario.battery, scenario.costs, scenario.unit_commitment, scenario.reserve
    gmax = scenario.gas_max
    prob = pulp.LpProblem("grid_dispatch_extended", pulp.LpMinimize)
    objective = []

    first = []  # first-stage variables per period
    soc_prev = bat.initial_soc
    on_prev = float(unit.initial_on) if unit else 1.0
    for t, p in enumerate(scenario.periods):
        v = {
            "charge": prob.add_variable(f"charge_{t}", lowBound=0, upBound=bat.max_rate),
            "discharge": prob.add_variable(f"discharge_{t}", lowBound=0, upBound=bat.max_rate),
            "soc": prob.add_variable(f"soc_{t}", lowBound=0, upBound=bat.capacity),
        }
        prob += v["soc"] == soc_prev + bat.efficiency * v["charge"] - v["discharge"], f"soc_{t}"
        soc_prev = v["soc"]
        objective.append(costs.discharge_wear * v["discharge"])
        if unit:
            v["on"] = prob.add_variable(f"on_{t}", cat="Binary")
            v["start"] = prob.add_variable(f"start_{t}", lowBound=0, upBound=1)
            prob += v["start"] >= v["on"] - on_prev, f"startup_{t}"
            on_prev = v["on"]
            objective.append(unit.startup_cost * v["start"])
        if rule:
            v["headroom"] = prob.add_variable(f"battery_headroom_{t}", lowBound=0, upBound=bat.max_rate)
            prob += v["headroom"] <= v["soc"], f"headroom_soc_{t}"
        first.append(v)

    gas_unit_cost = costs.gas_price + costs.carbon_price * costs.emission_factor
    for ci, (_, weight, periods) in enumerate(case_periods(scenario)):
        for t, p in enumerate(periods):
            v = first[t]
            solar = prob.add_variable(f"solar_{ci}_{t}", lowBound=0, upBound=p.solar)
            wind = prob.add_variable(f"wind_{ci}_{t}", lowBound=0, upBound=p.wind)
            gas = prob.add_variable(f"gas_{ci}_{t}", lowBound=0, upBound=gmax)
            unserved = prob.add_variable(f"unserved_{ci}_{t}", lowBound=0)
            prob += (solar + wind + gas + v["discharge"] - v["charge"] + unserved == p.demand), f"balance_{ci}_{t}"
            if unit:
                prob += gas <= gmax * v["on"], f"gas_cap_{ci}_{t}"
                prob += gas >= unit.min_output * v["on"], f"gas_min_{ci}_{t}"
            gas_headroom = (gmax * v["on"] if unit else gmax) - gas
            if rule:
                short = prob.add_variable(f"short_{ci}_{t}", lowBound=0)
                prob += short + gas_headroom + v["headroom"] >= rule.required_fraction * p.demand, f"reserve_{ci}_{t}"
                objective.append(weight * rule.shortfall_penalty * short)
            objective += [
                weight * gas_unit_cost * gas,
                weight * costs.curtailment_penalty * ((p.solar - solar) + (p.wind - wind)),
                weight * costs.unserved_penalty * unserved,
            ]
    prob += pulp.lpSum(objective)

    start = time.perf_counter()
    stats = prob.solve(pulp.COIN_CMD(msg=False, gapRel=1e-9, gapAbs=1e-6))  # no gap: the true optimum
    elapsed = time.perf_counter() - start
    # CBC reports "optimal within gap tolerance" as GapLimit; the tolerance above is ~0, so it is optimal
    if stats.status not in (pulp.LpSolveStatus.Optimal, pulp.LpSolveStatus.GapLimit):
        raise RuntimeError(f"MILP not solved to optimality: {stats.status.name}")

    # The schedule is the NOMINAL dispatch of the first-stage decisions (merit order).
    periods = []
    for p, v in zip(scenario.periods, first):
        charge, discharge = (round(v[k].value() or 0.0, DECIMALS) + 0.0 for k in ("charge", "discharge"))
        on = bool(round(v["on"].value())) if unit else None
        periods.append(dispatch_period(p, gmax, charge, discharge, unit, on))
    schedule = Schedule(periods=periods)

    features = [name for name, used in (("unit commitment", unit), ("forecast uncertainty", scenario.uncertainty),
                                        ("reserve requirement", rule)) if used]
    return SolverResult(
        source="classical_lp",
        scenario_name=scenario.name,
        schedule=schedule,
        evaluation=evaluate(scenario, schedule),
        provenance=Provenance(
            method=f"Mixed-integer program with {', '.join(features)}",
            backend="CBC via PuLP COIN_CMD",
            timestamp=utc_now(),
            solve_time_s=elapsed,
            library_versions=library_versions("pulp", "cbcbox"),
        ),
        details={"solver_status": stats.status.name, "solver_objective": pulp.value(prob.objective),
                 "model": "milp" if unit else "lp", "features": features},
    )
