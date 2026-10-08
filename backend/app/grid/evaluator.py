"""The ONE shared evaluator. Every solver (LP, exact, no-battery, QAOA sim, IBM hardware)
is scored by evaluate(), so their numbers are directly comparable.

It never fixes a schedule: anything outside the rules is reported as a violation.

Optional model features (all off unless the scenario sets them):
  unit commitment  gas unit on/off, minimum output, start-up cost
  uncertainty      forecast cases; objective = probability-weighted EXPECTED cost. The schedule's
                   battery flows and gas commitment are fixed first-stage decisions; solar, wind,
                   gas output and unserved energy are re-dispatched (merit order) for each case.
  reserve          spare capacity requirement, shortfall is penalised
"""

from app.grid.dispatch import dispatch_period
from app.models.evaluation import CaseOutcome, Evaluation, PeriodMetrics, Violation
from app.models.grid import CostWeights, Period, PeriodDispatch, Scenario, Schedule

TOL = 1e-6  # MW/MWh tolerance for floating-point comparisons

LEGACY_PARTS = ("gas_cost", "co2_cost", "curtailment_cost", "wear_cost", "unserved_cost")
EXTRA_PARTS = ("startup_cost", "reserve_cost")


def period_costs(costs: CostWeights, period: Period, x: PeriodDispatch) -> dict[str, float]:
    """$ cost parts of one period. The single cost formula, also used by the QUBO builder."""
    curtailment = (period.solar - x.solar) + (period.wind - x.wind)
    return dict(
        gas_cost=costs.gas_price * x.gas,
        co2_cost=costs.carbon_price * costs.emission_factor * x.gas,
        curtailment_cost=costs.curtailment_penalty * curtailment,
        wear_cost=costs.discharge_wear * x.discharge,
        unserved_cost=costs.unserved_penalty * x.unserved,
    )


def gas_is_on(scenario: Scenario, x: PeriodDispatch) -> bool:
    """Commitment of the gas unit in a dispatched period (always "available" without unit commitment)."""
    if scenario.unit_commitment is None:
        return True
    return x.gas_on if x.gas_on is not None else x.gas > TOL


def reserve_shortfall(scenario: Scenario, period: Period, x: PeriodDispatch, soc_end: float) -> float:
    """MW of reserve missing in this period (0 without a reserve requirement)."""
    rule = scenario.reserve
    if rule is None:
        return 0.0
    gas_headroom = (scenario.gas_max - x.gas) if gas_is_on(scenario, x) else 0.0
    battery_headroom = min(scenario.battery.max_rate, max(soc_end, 0.0))
    return max(rule.required_fraction * period.demand - gas_headroom - battery_headroom, 0.0)


def outcome_parts(scenario: Scenario, period: Period, x: PeriodDispatch, soc_end: float,
                  prev_on: bool) -> dict[str, float]:
    """All $ cost parts of one period, including start-up and reserve (+ the reserve shortfall in MW).
    Used by the evaluator AND by the QUBO builder, so QAOA's energy and the evaluator's objective
    are the same formula."""
    parts = period_costs(scenario.costs, period, x)
    unit = scenario.unit_commitment
    parts["startup_cost"] = unit.startup_cost if unit and gas_is_on(scenario, x) and not prev_on else 0.0
    shortfall = reserve_shortfall(scenario, period, x, soc_end)
    parts["reserve_cost"] = scenario.reserve.shortfall_penalty * shortfall if scenario.reserve else 0.0
    parts["reserve_shortfall_mw"] = shortfall
    return parts


def case_periods(scenario: Scenario) -> list[tuple[str, float, list[Period]]]:
    """(name, probability, periods with that case's renewable availability)."""
    if scenario.uncertainty is None:
        return [("forecast", 1.0, list(scenario.periods))]
    return [(c.name, c.probability,
             [p.model_copy(update={"solar": p.solar * c.solar_factor, "wind": p.wind * c.wind_factor})
              for p in scenario.periods])
            for c in scenario.uncertainty.cases]


def evaluate(scenario: Scenario, schedule: Schedule) -> Evaluation:
    if len(schedule.periods) != len(scenario.periods):
        raise ValueError(
            f"schedule has {len(schedule.periods)} periods, scenario has {len(scenario.periods)}"
        )

    bat, costs, unit = scenario.battery, scenario.costs, scenario.unit_commitment
    violations: list[Violation] = []

    def check_max(period: str, kind: str, value: float, limit: float, what: str) -> None:
        if value > limit + TOL:
            violations.append(
                Violation(period=period, kind=kind, amount=value - limit,
                          detail=f"{what} {value:g} exceeds limit {limit:g}")
            )

    soc = bat.initial_soc
    soc_trajectory: list[float] = []
    ons: list[bool] = []

    for p, x in zip(scenario.periods, schedule.periods):
        for field in ("solar", "wind", "gas", "charge", "discharge", "unserved"):
            value = getattr(x, field)
            if value < -TOL:
                violations.append(
                    Violation(period=p.name, kind="negative", amount=-value,
                              detail=f"{field} is negative ({value:g})")
                )
        check_max(p.name, "solar_available", x.solar, p.solar, "solar")
        check_max(p.name, "wind_available", x.wind, p.wind, "wind")
        check_max(p.name, "gas_max", x.gas, scenario.gas_max, "gas")
        check_max(p.name, "charge_rate", x.charge, bat.max_rate, "charge")
        check_max(p.name, "discharge_rate", x.discharge, bat.max_rate, "discharge")
        if unit is not None:
            on = gas_is_on(scenario, x)
            if not on and x.gas > TOL:
                violations.append(Violation(period=p.name, kind="gas_off", amount=x.gas,
                                            detail=f"gas {x.gas:g} produced while the unit is off"))
            if on and x.gas < unit.min_output - TOL:
                violations.append(Violation(period=p.name, kind="min_output", amount=unit.min_output - x.gas,
                                            detail=f"gas {x.gas:g} below minimum output {unit.min_output:g}"))
            ons.append(on)

        supply = x.solar + x.wind + x.gas + x.discharge - x.charge + x.unserved
        if abs(supply - p.demand) > TOL:
            violations.append(
                Violation(period=p.name, kind="balance", amount=abs(supply - p.demand),
                          detail=f"supply {supply:g} != demand {p.demand:g}")
            )

        soc = soc + bat.efficiency * x.charge - x.discharge
        if soc < -TOL:
            violations.append(
                Violation(period=p.name, kind="soc_min", amount=-soc,
                          detail=f"state of charge {soc:g} below 0")
            )
        check_max(p.name, "soc_max", soc, bat.capacity, "state of charge")
        soc_trajectory.append(soc)

    # One dispatch per forecast case. Without uncertainty the single case IS the given schedule.
    cases = case_periods(scenario)
    case_dispatches: list[list[PeriodDispatch]] = []
    for _, _, periods in cases:
        if scenario.uncertainty is None:
            case_dispatches.append(list(schedule.periods))
        else:
            case_dispatches.append([
                dispatch_period(cp, scenario.gas_max, x.charge, x.discharge, unit,
                                ons[t] if unit else None)
                for t, (cp, x) in enumerate(zip(periods, schedule.periods))
            ])

    metrics: list[PeriodMetrics] = []
    case_totals = [0.0] * len(cases)
    case_unserved = [0.0] * len(cases)
    case_curtail = [0.0] * len(cases)
    gas_mwh = unserved_mwh = available = used = 0.0
    for t, p in enumerate(scenario.periods):
        prev_on = (unit.initial_on if unit else True) if t == 0 else gas_is_on(scenario, schedule.periods[t - 1])
        acc = dict.fromkeys((*LEGACY_PARTS, *EXTRA_PARTS, "reserve_shortfall_mw", "curtailment", "co2"), 0.0)
        for ci, ((_, prob, periods), xs) in enumerate(zip(cases, case_dispatches)):
            cp, x = periods[t], xs[t]
            part = outcome_parts(scenario, cp, x, soc_trajectory[t], prev_on)
            curtailment = (cp.solar - x.solar) + (cp.wind - x.wind)
            for k, v in part.items():
                acc[k] += prob * v
            acc["curtailment"] += prob * curtailment
            acc["co2"] += prob * costs.emission_factor * x.gas
            case_totals[ci] += sum(part[k] for k in LEGACY_PARTS) + part["startup_cost"] + part["reserve_cost"]
            case_unserved[ci] += x.unserved
            case_curtail[ci] += curtailment
            gas_mwh += prob * x.gas
            unserved_mwh += prob * x.unserved
            available += prob * (cp.solar + cp.wind)
            used += prob * (x.solar + x.wind)
        total_cost = sum(acc[k] for k in LEGACY_PARTS) + acc["startup_cost"] + acc["reserve_cost"]
        metrics.append(PeriodMetrics(
            name=p.name, soc_end=soc_trajectory[t], curtailment=acc["curtailment"], co2_tonnes=acc["co2"],
            total_cost=total_cost, reserve_shortfall_mw=acc["reserve_shortfall_mw"],
            gas_on=ons[t] if unit else None,
            **{k: acc[k] for k in (*LEGACY_PARTS, *EXTRA_PARTS)}))

    def total(attr: str) -> float:
        return sum(getattr(m, attr) for m in metrics)

    startups = 0
    if unit:
        previous = unit.initial_on
        for on in ons:
            startups += int(on and not previous)
            previous = on
    outcomes = [CaseOutcome(name=name, probability=prob, objective=case_totals[i],
                            unserved_mwh=case_unserved[i], curtailment_mwh=case_curtail[i])
                for i, (name, prob, _) in enumerate(cases)] if scenario.uncertainty else []

    return Evaluation(
        objective=total("total_cost"),
        gas_cost=total("gas_cost"),
        co2_cost=total("co2_cost"),
        curtailment_cost=total("curtailment_cost"),
        wear_cost=total("wear_cost"),
        unserved_cost=total("unserved_cost"),
        startup_cost=total("startup_cost"),
        reserve_cost=total("reserve_cost"),
        gas_mwh=gas_mwh,
        co2_tonnes=total("co2_tonnes"),
        curtailment_mwh=total("curtailment"),
        unserved_mwh=unserved_mwh,
        renewable_available_mwh=available,
        renewable_used_mwh=used,
        renewable_utilization=used / available if available > 0 else 0.0,
        soc_trajectory=soc_trajectory,
        periods=metrics,
        violations=violations,
        reserve_shortfall_mwh=total("reserve_shortfall_mw"),
        startups=startups,
        cases=outcomes,
        worst_case_objective=max(case_totals) if scenario.uncertainty else None,
        feasible=not violations,
    )
