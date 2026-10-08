"""Output of the shared evaluator. Every solver's schedule is scored into this shape."""

from pydantic import BaseModel


class Violation(BaseModel):
    period: str | None  # None = whole-schedule issue
    kind: str  # e.g. "balance", "gas_max", "soc_max", "charge_rate"
    amount: float  # how far past the limit (MW or MWh)
    detail: str


class PeriodMetrics(BaseModel):
    name: str
    soc_end: float
    curtailment: float
    co2_tonnes: float
    gas_cost: float
    co2_cost: float
    curtailment_cost: float
    wear_cost: float
    unserved_cost: float
    total_cost: float
    startup_cost: float = 0.0
    reserve_cost: float = 0.0
    reserve_shortfall_mw: float = 0.0
    gas_on: bool | None = None


class CaseOutcome(BaseModel):
    """Cost of the schedule's first-stage decisions under one forecast case."""

    name: str
    probability: float
    objective: float
    unserved_mwh: float
    curtailment_mwh: float


class Evaluation(BaseModel):
    objective: float  # total $ = sum of the cost parts below (expected value if the scenario has forecast cases)
    gas_cost: float
    co2_cost: float
    curtailment_cost: float
    wear_cost: float
    unserved_cost: float
    startup_cost: float = 0.0  # unit commitment; 0 when not used
    reserve_cost: float = 0.0  # reserve shortfall penalty; 0 when not used

    gas_mwh: float
    co2_tonnes: float
    curtailment_mwh: float
    unserved_mwh: float
    renewable_available_mwh: float
    renewable_used_mwh: float
    renewable_utilization: float  # used / available, 0..1 (0 if nothing available)

    soc_trajectory: list[float]  # SOC at end of each period
    periods: list[PeriodMetrics]
    violations: list[Violation]
    reserve_shortfall_mwh: float = 0.0  # total reserve missing (0 if no reserve requirement)
    startups: int = 0  # number of gas start-ups
    cases: list[CaseOutcome] = []  # per forecast case; empty without uncertainty
    worst_case_objective: float | None = None  # highest case cost; None without uncertainty
    feasible: bool  # True when there are no violations (unserved demand is penalised, not a violation)
