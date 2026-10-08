"""Classical baseline 3: no battery, merit-order dispatch each period.

Without storage the periods are independent, and using the cheapest source first
(renewables, then gas) is optimal for each one, so this is the best possible no-battery cost.
"""

import time

from app.grid.dispatch import dispatch_no_battery
from app.grid.evaluator import evaluate
from app.models.grid import Scenario
from app.models.result import Provenance, SolverResult
from app.provenance import utc_now


def solve_no_battery(scenario: Scenario) -> SolverResult:
    start = time.perf_counter()
    schedule = dispatch_no_battery(scenario)
    elapsed = time.perf_counter() - start
    return SolverResult(
        source="classical_no_battery",
        scenario_name=scenario.name,
        schedule=schedule,
        evaluation=evaluate(scenario, schedule),
        provenance=Provenance(
            method="Greedy merit-order dispatch, battery idle",
            backend="python",
            timestamp=utc_now(),
            solve_time_s=elapsed,
        ),
    )
