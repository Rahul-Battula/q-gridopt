"""Request / response models for the HTTP API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.grid.presets import DEFAULT_PRESET, load_preset
from app.models.grid import Scenario
from app.models.result import SolverResult

Tier = Literal["Q3", "Q9", "Q18", "Q3U", "Q9U"]
RunKind = Literal["classical", "quantum_simulator", "quantum_ibm"]
RunStatus = Literal["queued", "running", "submitted", "completed", "failed"]


class ScenarioInput(BaseModel):
    """Either a preset id or a full custom scenario (not both). Neither = default preset."""

    model_config = ConfigDict(extra="forbid")

    preset: str | None = None
    scenario: Scenario | None = None

    @model_validator(mode="after")
    def _one_source(self):
        if self.preset is not None and self.scenario is not None:
            raise ValueError("give either 'preset' or 'scenario', not both")
        return self

    def resolve(self) -> Scenario:
        if self.scenario is not None:
            return self.scenario
        return load_preset(self.preset or DEFAULT_PRESET)


class PresetOut(BaseModel):
    id: str
    default: bool
    scenario: Scenario


class QuboPreviewRequest(ScenarioInput):
    tier: Tier = "Q3"
    penalty: float | None = Field(None, gt=0, description="one-hot / rule penalty A; default 1.5 x max path cost")
    reps: int = Field(1, ge=1, le=3, description="QAOA depth for the circuit drawing and stats")
    include_circuit: bool = True


class ClassicalRequest(ScenarioInput):
    exact_tiers: list[Tier] | None = Field(
        None, description="default: Q3, Q9, Q18 (Q3U, Q9U when the scenario has unit commitment)")


class SimulatorRequest(ScenarioInput):
    tier: Tier = "Q3"
    max_reps: int = Field(3, ge=1, le=3)
    shots: int = Field(4096, ge=100, le=100_000)
    seed: int = 1234
    penalty: float | None = Field(None, gt=0)
    noisy: bool = True
    noise_backend: str = "FakeFez"


class IbmRequest(ScenarioInput):
    tier: Tier = "Q3"
    max_reps: int = Field(3, ge=1, le=3)
    shots: int = Field(4096, ge=100, le=100_000)
    seed: int = 1234
    backend: str | None = Field(None, description="IBM backend name; None = least busy; 'Fake*' = local test")
    confirm: bool = Field(False, description="REQUIRED for real hardware: the user approves using QPU time")
    dynamical_decoupling: bool = True
    twirling: bool = True

    @field_validator("tier")
    @classmethod
    def _no_commitment_tiers_on_hardware(cls, tier: str) -> str:
        if tier in ("Q3U", "Q9U"):
            raise ValueError("unit-commitment tiers (Q3U, Q9U) are simulator-only: their circuits need "
                             "hundreds of two-qubit gates, far too deep for today's hardware")
        return tier


class RunAccepted(BaseModel):
    run_id: str
    status: RunStatus


class RunSummary(BaseModel):
    run_id: str
    kind: RunKind
    status: RunStatus
    progress: str | None
    scenario_name: str
    created_at: str
    updated_at: str
    job_id: str | None
    sources: list[str]
    best_objective: float | None


class RunOut(RunSummary):
    request: dict
    error: str | None
    results: list[SolverResult]
