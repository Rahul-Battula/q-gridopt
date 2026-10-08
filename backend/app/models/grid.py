"""Grid scenario and schedule models.

Units: every period is 1 hour, so MW == MWh. Money is in $, CO2 in tonnes.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Period(BaseModel):
    """One time step: demand and the renewable power AVAILABLE (not necessarily used)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    demand: float = Field(ge=0, description="MW to be served")
    solar: float = Field(ge=0, description="MW of solar available")
    wind: float = Field(ge=0, description="MW of wind available")


class Battery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capacity: float = Field(50, ge=0, description="MWh")
    max_rate: float = Field(30, ge=0, description="max charge or discharge per period, MW")
    initial_soc: float = Field(0, ge=0, description="state of charge before period 1, MWh")
    efficiency: float = Field(
        1.0, gt=0, le=1, description="charging efficiency: SOC rises by efficiency x charge"
    )

    @model_validator(mode="after")
    def _soc_fits(self) -> "Battery":
        if self.initial_soc > self.capacity:
            raise ValueError("initial_soc cannot exceed capacity")
        return self


class CostWeights(BaseModel):
    """Objective = gas_price*gas + carbon_price*emission_factor*gas
    + curtailment_penalty*curtailment + discharge_wear*discharge + unserved_penalty*unserved."""

    model_config = ConfigDict(extra="forbid")

    gas_price: float = Field(60, ge=0, description="$/MWh")
    carbon_price: float = Field(50, ge=0, description="$/tCO2")
    emission_factor: float = Field(0.45, ge=0, description="tCO2/MWh of gas")
    curtailment_penalty: float = Field(10, ge=0, description="$/MWh of renewables wasted")
    discharge_wear: float = Field(5, ge=0, description="$/MWh discharged")
    unserved_penalty: float = Field(1000, ge=0, description="$/MWh of demand not served")


class UnitCommitment(BaseModel):
    """Optional: the gas plant is a unit that must be switched ON to produce anything.

    While on it runs between min_output and gas_max; switching it on costs startup_cost. With this
    set, "gas_on" per period is a decision (QAOA, exact and LP all choose it)."""

    model_config = ConfigDict(extra="forbid")

    min_output: float = Field(0, ge=0, description="MW the unit must produce while on")
    startup_cost: float = Field(0, ge=0, description="$ each time the unit goes from off to on")
    initial_on: bool = Field(False, description="was the unit on before period 1?")


class ForecastCase(BaseModel):
    """One possible outcome of the solar/wind forecast (factors multiply the forecast)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    probability: float = Field(ge=0, le=1)
    solar_factor: float = Field(1.0, ge=0)
    wind_factor: float = Field(1.0, ge=0)


class Uncertainty(BaseModel):
    """Optional: renewable forecast uncertainty as a few weighted cases.

    The battery plan and the gas commitment are decided BEFORE the outcome is known; the rest of
    the dispatch (merit order) reacts to the case that happens. The objective becomes the
    probability-weighted EXPECTED cost."""

    model_config = ConfigDict(extra="forbid")

    cases: list[ForecastCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _probabilities_sum_to_one(self) -> "Uncertainty":
        if abs(sum(c.probability for c in self.cases) - 1.0) > 1e-6:
            raise ValueError("case probabilities must sum to 1")
        return self


class Reserve(BaseModel):
    """Optional grid-stability margin: spare capacity that could be called on within the hour.

    Spare = unused gas capacity (only while the unit is on) + battery discharge headroom
    min(max_rate, state of charge at the end of the period). Required = required_fraction x
    demand. Each MW short costs shortfall_penalty."""

    model_config = ConfigDict(extra="forbid")

    required_fraction: float = Field(0.1, ge=0, le=1, description="of the period's demand")
    shortfall_penalty: float = Field(50, ge=0, description="$ per MW of reserve missing")


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    periods: list[Period] = Field(min_length=1)
    gas_max: float = Field(100, ge=0, description="MW")
    battery: Battery = Battery()
    costs: CostWeights = CostWeights()
    unit_commitment: UnitCommitment | None = None
    uncertainty: Uncertainty | None = None
    reserve: Reserve | None = None

    @model_validator(mode="after")
    def _min_output_fits(self) -> "Scenario":
        if self.unit_commitment and self.unit_commitment.min_output > self.gas_max:
            raise ValueError("unit_commitment.min_output cannot exceed gas_max")
        return self


class PeriodDispatch(BaseModel):
    """What every resource does in one period. Values are NOT range-checked here on purpose:
    the evaluator reports out-of-range values as violations instead of rejecting them."""

    model_config = ConfigDict(extra="forbid")

    solar: float = 0
    wind: float = 0
    gas: float = 0
    charge: float = 0
    discharge: float = 0
    unserved: float = 0
    gas_on: bool | None = None  # commitment of the gas unit; None = not tracked (no unit commitment)


class Schedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    periods: list[PeriodDispatch]
