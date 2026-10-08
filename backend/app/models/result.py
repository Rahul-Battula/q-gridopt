"""A solver result: the schedule, its score from the shared evaluator, and where it came from."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.evaluation import Evaluation
from app.models.grid import Schedule

Source = Literal[
    "classical_lp",
    "classical_exact",
    "classical_no_battery",
    "classical_annealing",
    "aer_statevector",
    "aer_noisy",
    "ibm_hardware",
]


class Provenance(BaseModel):
    method: str  # short human-readable description of how the schedule was produced
    backend: str | None = None  # e.g. "CBC (COIN_CMD)", "AerSimulator", "ibm_brisbane"
    job_id: str | None = None  # IBM job id for hardware runs
    shots: int | None = None
    timestamp: str  # UTC, ISO 8601
    solve_time_s: float | None = None
    library_versions: dict[str, str] = Field(default_factory=dict)


class SolverResult(BaseModel):
    source: Source
    scenario_name: str
    # None only when a sampling solver never produced a feasible schedule (reported, not repaired)
    schedule: Schedule | None
    evaluation: Evaluation | None  # ALWAYS produced by app.grid.evaluator.evaluate
    provenance: Provenance
    details: dict[str, Any] = Field(default_factory=dict)  # solver-specific extras
