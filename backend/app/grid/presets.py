"""Preset scenarios stored as JSON in data/scenarios/ (preset id = file name without .json)."""

from pathlib import Path

from app.models.grid import Scenario

SCENARIO_DIR = Path(__file__).resolve().parents[3] / "data" / "scenarios"
DEFAULT_PRESET = "scenario_b"


def list_presets() -> dict[str, Scenario]:
    return {
        path.stem: Scenario.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(SCENARIO_DIR.glob("*.json"))
    }


def load_preset(preset_id: str = DEFAULT_PRESET) -> Scenario:
    path = SCENARIO_DIR / f"{preset_id}.json"
    if not path.is_file():
        raise KeyError(f"unknown preset '{preset_id}'")
    return Scenario.model_validate_json(path.read_text(encoding="utf-8"))
