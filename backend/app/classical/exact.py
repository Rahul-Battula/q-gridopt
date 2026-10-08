"""Classical baseline 2: exact enumeration of the DISCRETE battery-path problem.

This is the same problem QAOA solves: pick a battery level (from a fixed list) at the end of
every period, then merit-order dispatch fills in the rest. Trying every path gives the true
best answer for that discrete problem, which is what QAOA results are graded against.

Paths that break a rule (e.g. battery change faster than max_rate) are scored but marked
infeasible and never chosen.

With unit commitment (tiers Q3U / Q9U) a "path" also fixes the gas unit's on/off state in every
period, so the enumeration covers (battery level, gas on/off) per period.
"""

import itertools
import time
from collections.abc import Sequence

from pydantic import BaseModel

from app.grid.dispatch import dispatch_from_soc_path
from app.grid.evaluator import evaluate
from app.grid.tiers import is_commit_tier
from app.models.grid import Scenario
from app.models.result import Provenance, SolverResult
from app.provenance import utc_now

TIE_TOL = 1e-6  # $; paths within this of the best are all counted as optimal


class PathScore(BaseModel):
    path: list[float]  # battery state of charge at the end of each period
    commits: list[bool] | None = None  # gas on/off per period (unit-commitment tiers only)
    objective: float
    feasible: bool
    violations: list[str]  # violation kinds, empty when feasible


def enumerate_paths(scenario: Scenario, levels: Sequence[float], commit: bool = False) -> list[PathScore]:
    """Score every path. Sorted: feasible first, then cheapest first. commit=True also enumerates
    the gas unit's on/off state in every period."""
    states = [(level, on) for level in levels for on in (False, True)] if commit else [(level, None) for level in levels]
    scores = []
    for chosen in itertools.product(states, repeat=len(scenario.periods)):
        path = [level for level, _ in chosen]
        commits = [on for _, on in chosen] if commit else None
        ev = evaluate(scenario, dispatch_from_soc_path(scenario, path, commits))
        scores.append(PathScore(path=path, commits=commits, objective=ev.objective, feasible=ev.feasible,
                                violations=sorted({v.kind for v in ev.violations})))
    scores.sort(key=lambda s: (not s.feasible, s.objective))
    return scores


def solve_exact(scenario: Scenario, levels: Sequence[float], tier: str | None = None) -> SolverResult:
    start = time.perf_counter()
    commit = is_commit_tier(tier)
    scores = enumerate_paths(scenario, levels, commit)
    elapsed = time.perf_counter() - start

    feasible = [s for s in scores if s.feasible]
    if not feasible:
        raise ValueError(f"no feasible battery path with levels {list(levels)}")
    best = feasible[0]
    optimal = [s.path for s in feasible if s.objective <= best.objective + TIE_TOL]
    schedule = dispatch_from_soc_path(scenario, best.path, best.commits)

    return SolverResult(
        source="classical_exact",
        scenario_name=scenario.name,
        schedule=schedule,
        evaluation=evaluate(scenario, schedule),
        provenance=Provenance(
            method=f"Exhaustive search over discrete battery paths, levels {list(levels)}",
            backend="python",
            timestamp=utc_now(),
            solve_time_s=elapsed,
        ),
        details={
            "tier": tier,
            "levels": list(levels),
            "best_path": best.path,
            "best_commits": best.commits,
            "optimal_paths": optimal,
            "n_paths": len(scores),
            "n_feasible": len(feasible),
            "worst_feasible_objective": feasible[-1].objective,
            "mean_feasible_objective": sum(s.objective for s in feasible) / len(feasible),
        },
    )
