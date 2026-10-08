# QISKIT INTEGRATION: builds the battery-scheduling QUBO and holds it in a
# qiskit_optimization.QuadraticProgram (the standard Qiskit container for binary optimisation).
"""Battery-path QUBO (state-path encoding).

Plain English: one yes/no variable per (hour, battery level) says "the battery ends this hour
at this level". The energy of a choice of variables is its $ cost (merit-order dispatch fills
in solar/wind/gas), plus a big penalty A if the choice is not a valid battery path.

    E(y) = sum_l F_1(l - SOC_0) y_{1,l}
         + sum_{t>=2} sum_{a,b} F_t(b - a) y_{t-1,a} y_{t,b}
         + A sum_t (1 - sum_l y_{t,l})^2                         (one-hot tiers only)

F_t(b) = $ cost of period t when the battery state of charge changes by b (shared evaluator
cost formula on the merit-order dispatch), + A if that period breaks a rule (rate limit, or
more discharge than demand).

Encodings:
    one-hot (Q9, Q18): variable k = t * L + i  <->  "period t ends at levels[i]"
    binary  (Q3)     : variable k = t          <->  1 means levels[1], 0 means levels[0];
                       always a valid path, so no one-hot penalty is needed.
    unit commitment (Q3U, Q9U): the per-period state is the PAIR (battery level, gas on/off),
                       one-hot over 2L states: variable k = t * 2L + 2*i + on. The start-up cost and
                       the gas on/off rule then depend only on two consecutive states, so the energy
                       stays quadratic (a separate on/off qubit would make it cubic).
Variable k is qubit k in the Ising operator (see ising.py).

Forecast uncertainty (scenario.uncertainty) enters F_t as a probability-weighted average over the
cases, and the reserve requirement as a shortfall penalty; both use the evaluator's own formula
(grid/evaluator.py: outcome_parts), so the QUBO energy equals the evaluator's objective.

Default A = 1.5 x the highest $ cost of any path in the tier. Every energy term is >= 0, so
any rule-breaking bitstring has energy >= A > every valid path's cost: the lowest-energy
state is always the cheapest valid path.
"""

import itertools
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from qiskit_optimization import QuadraticProgram

from app.grid.dispatch import battery_flows, dispatch_period
from app.grid.evaluator import TOL, case_periods, outcome_parts
from app.grid.tiers import TIERS, is_commit_tier
from app.models.grid import Scenario

PENALTY_FACTOR = 1.5

# A linear expression in binary variables: (constant, {variable index: coefficient})
LinExpr = tuple[float, dict[int, float]]
State = tuple[float, bool | None]  # (battery level, gas on/off; None without unit commitment)


@dataclass
class QuboModel:
    tier: str
    levels: tuple[float, ...]
    one_hot: bool
    num_periods: int
    penalty: float
    constant: float
    linear: dict[int, float]
    quadratic: dict[tuple[int, int], float]
    variable_names: list[str]
    program: QuadraticProgram
    commit: bool = False  # unit-commitment tier: the per-period state is (level, gas on/off)

    @property
    def num_qubits(self) -> int:
        return len(self.variable_names)

    @property
    def states(self) -> list[State]:
        """The choices per period, in variable order: (battery level, gas on/off or None)."""
        if self.commit:
            return [(level, bool(on)) for level in self.levels for on in (0, 1)]
        return [(level, None) for level in self.levels]

    def energy(self, x: Sequence[int]) -> float:
        e = self.constant + sum(c * x[i] for i, c in self.linear.items())
        return e + sum(c * x[i] * x[j] for (i, j), c in self.quadratic.items())

    def energies_all(self) -> np.ndarray:
        """Energy of every bitstring; entry k is the state where variable i = bit i of k."""
        k = np.arange(2 ** self.num_qubits, dtype=np.int64)
        bits = [(k >> i) & 1 for i in range(self.num_qubits)]
        e = np.full(k.shape, self.constant, dtype=float)
        for i, c in self.linear.items():
            e += c * bits[i]
        for (i, j), c in self.quadratic.items():
            e += c * (bits[i] & bits[j])
        return e

    def encode(self, path: Sequence[float], commits: Sequence[bool] | None = None) -> list[int]:
        if self.commit:
            if commits is None:
                raise ValueError("a unit-commitment tier needs the gas commitment per period")
            states = self.states
            idx = [states.index((float(level), bool(on))) for level, on in zip(path, commits)]
        else:
            idx = [self.levels.index(level) for level in path]
        if not self.one_hot:
            return idx
        x = [0] * self.num_qubits
        for t, i in enumerate(idx):
            x[t * len(self.states) + i] = 1
        return x

    def decode_states(self, x: Sequence[int]) -> list[State] | None:
        """(level, gas on/off) per period for a bitstring, or None if some period has 0 or 2+
        states selected."""
        states = self.states
        if not self.one_hot:
            return [states[b] for b in x]
        width, result = len(states), []
        for t in range(self.num_periods):
            chosen = [i for i in range(width) if x[t * width + i]]
            if len(chosen) != 1:
                return None
            result.append(states[chosen[0]])
        return result

    def decode(self, x: Sequence[int]) -> list[float] | None:
        """Battery path for a bitstring, or None if some period has 0 or 2+ states selected."""
        chosen = self.decode_states(x)
        return None if chosen is None else [level for level, _ in chosen]


def period_energy(scenario: Scenario, t: int, soc_change: float, *, soc_end: float | None = None,
                  prev_on: bool = False, on: bool | None = None) -> tuple[float, bool]:
    """($ expected cost of period t for this battery change and gas commitment, whether the period
    breaks a rule). soc_end is needed only for a reserve requirement; prev_on / on only for unit
    commitment (on=None: no commitment decision, the dispatch derives it)."""
    p, bat, unit = scenario.periods[t], scenario.battery, scenario.unit_commitment
    if scenario.reserve is not None and soc_end is None:
        raise ValueError("soc_end is required when the scenario has a reserve requirement")
    charge, discharge = battery_flows(soc_change, bat.efficiency)
    cost = 0.0
    for _, prob, periods in case_periods(scenario):
        x = dispatch_period(periods[t], scenario.gas_max, charge, discharge, unit, on)
        parts = outcome_parts(scenario, periods[t], x, soc_end if soc_end is not None else 0.0, prev_on)
        cost += prob * sum(v for k, v in parts.items() if k != "reserve_shortfall_mw")
    too_fast = charge > bat.max_rate + TOL or discharge > bat.max_rate + TOL
    net_load = p.demand + charge - discharge
    oversupply = net_load < -TOL  # discharge exceeds demand: can't balance
    # an ON unit's minimum output exceeds the whole net load: nothing can absorb it
    gas_surplus = unit is not None and on is True and unit.min_output > max(net_load, 0.0) + TOL
    return cost, too_fast or oversupply or gas_surplus


def _indicators(width: int, periods: int, one_hot: bool) -> list[list[LinExpr]]:
    """ind[t][i] = expression that is 1 exactly when period t is in state i (width states)."""
    if one_hot:
        return [[(0.0, {t * width + i: 1.0}) for i in range(width)] for t in range(periods)]
    return [[(1.0, {t: -1.0}), (0.0, {t: 1.0})] for t in range(periods)]


def build_qubo(scenario: Scenario, tier: str, penalty: float | None = None) -> QuboModel:
    levels = tuple(float(level) for level in TIERS[tier])
    commit = is_commit_tier(tier)
    one_hot = tier != "Q3"  # Q3 uses the 1-bit-per-period binary encoding
    if not one_hot and len(levels) != 2:
        raise ValueError("binary encoding needs exactly 2 levels")
    unit = scenario.unit_commitment
    if commit and unit is None:
        raise ValueError(f"tier {tier} needs a scenario with unit_commitment (gas on/off)")
    if unit is not None and not commit:
        raise ValueError("this scenario has unit commitment: use tier Q3U or Q9U")
    T = len(scenario.periods)
    bat = scenario.battery
    if any(level < 0 or level > bat.capacity + TOL for level in levels):
        raise ValueError(f"tier {tier} levels {list(levels)} must lie within 0..{bat.capacity:g} MWh")

    if commit:
        states: list[State] = [(level, bool(on)) for level in levels for on in (0, 1)]
    else:
        states = [(level, None) for level in levels]
    S = len(states)
    start_state: State = (bat.initial_soc, unit.initial_on if unit else None)

    # expected $ cost and rule check for every (period, from-state, to-state); period 0 starts at SOC_0
    def entry(t: int, a: State, b: State) -> tuple[float, bool]:
        return period_energy(scenario, t, b[0] - a[0], soc_end=b[0], prev_on=bool(a[1]), on=b[1])

    starts = lambda t: [start_state] if t == 0 else states  # noqa: E731
    table = {(t, a, b): entry(t, a, b) for t in range(T) for a in starts(t) for b in states}

    if penalty is None:
        worst = max(
            sum(table[(t, a, b)][0] for t, (a, b) in enumerate(zip([start_state, *path[:-1]], path)))
            for path in itertools.product(states, repeat=T)
        )
        penalty = max(PENALTY_FACTOR * worst, 1.0)

    def F(t: int, a: State, b: State) -> float:
        cost, broken = table[(t, a, b)]
        return cost + (penalty if broken else 0.0)

    constant = 0.0
    linear: dict[int, float] = defaultdict(float)
    quadratic: dict[tuple[int, int], float] = defaultdict(float)

    def add(coef: float, e1: LinExpr, e2: LinExpr | None = None) -> None:
        nonlocal constant
        c2, l2 = e2 if e2 is not None else (1.0, {})
        c1, l1 = e1
        constant += coef * c1 * c2
        for i, v in l1.items():
            linear[i] += coef * v * c2
        for j, w in l2.items():
            linear[j] += coef * c1 * w
        for i, v in l1.items():
            for j, w in l2.items():
                if i == j:
                    linear[i] += coef * v * w  # x^2 = x for binary x
                else:
                    quadratic[(min(i, j), max(i, j))] += coef * v * w

    ind = _indicators(S, T, one_hot)
    for i, b in enumerate(states):
        add(F(0, start_state, b), ind[0][i])
    for t in range(1, T):
        for i, a in enumerate(states):
            for j, b in enumerate(states):
                add(F(t, a, b), ind[t - 1][i], ind[t][j])

    if one_hot:  # A (1 - sum_s y)^2 = A (1 - sum_s y + 2 sum_{s<s'} y y')   using y^2 = y
        for t in range(T):
            constant += penalty
            for i in range(S):
                linear[t * S + i] -= penalty
                for j in range(i + 1, S):
                    quadratic[(t * S + i, t * S + j)] += 2 * penalty

    def label(level: float, on: bool | None) -> str:
        return f"soc{level:g}" if on is None else f"soc{level:g}_{'on' if on else 'off'}"

    names = ([f"y_t{t}_{label(*state)}" for t in range(T) for state in states] if one_hot
             else [f"x_t{t}" for t in range(T)])
    linear = {i: c for i, c in linear.items() if c != 0.0}
    quadratic = {k: c for k, c in quadratic.items() if c != 0.0}

    program = QuadraticProgram(f"battery_{tier}")
    for name in names:
        program.binary_var(name)
    program.minimize(constant=constant, linear=linear, quadratic=quadratic)

    return QuboModel(tier=tier, levels=levels, one_hot=one_hot, num_periods=T, penalty=penalty,
                     constant=constant, linear=linear, quadratic=quadratic,
                     variable_names=names, program=program, commit=commit)
