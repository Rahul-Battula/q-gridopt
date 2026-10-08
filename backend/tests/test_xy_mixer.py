import numpy as np
import pytest
from qiskit.quantum_info import Statevector

from app.grid.presets import load_preset
from app.quantum import aer_runner, decoder
from app.quantum.qaoa import build_ansatz, parameter_values, xy_start_state
from app.quantum.simulate import cost_for, run_qaoa_simulation

SC = load_preset("scenario_b")


def test_w_start_state_is_uniform_over_one_hot_states():
    probs = Statevector(xy_start_state([[0, 1, 2], [3, 4, 5]], 6)).probabilities_dict()
    assert len(probs) == 9  # 3 x 3 valid combinations
    assert all(abs(p - 1 / 9) < 1e-9 for p in probs.values())
    for key in probs:  # exactly one 1 in each block
        assert key[3:].count("1") == 1 and key[:3].count("1") == 1


@pytest.mark.parametrize("gamma,beta", [(0.3, 0.4), (-1.1, 2.0)])
def test_xy_mixer_only_produces_valid_plans(gamma, beta):
    model, cost = cost_for(SC, "Q9", None, mixer="xy")
    circuit = build_ansatz(cost, 1)
    probs = aer_runner.exact_probabilities(circuit, parameter_values(circuit, [gamma], [beta]))
    table = decoder.path_table(SC, model)
    assert sum(probs[k] for k in table) == pytest.approx(1.0, abs=1e-9)


def test_xy_mixer_rejects_binary_tier_and_unknown_mixer():
    with pytest.raises(ValueError, match="one-hot"):
        cost_for(SC, "Q3", None, mixer="xy")
    with pytest.raises(ValueError, match="unknown mixer"):
        cost_for(SC, "Q9", None, mixer="zz")


def test_xy_simulation_is_all_valid_and_labelled():
    result, _ = run_qaoa_simulation(SC, "Q9", 1, shots=1024, mixer="xy")
    assert result.details["mixer"] == "xy"
    assert result.details["qaoa_exact"]["p_valid"] == pytest.approx(1.0, abs=1e-9)
    assert "XY mixer" in result.provenance.method
    # the default mixer is unchanged
    default, _ = run_qaoa_simulation(SC, "Q9", 1, shots=1024)
    assert default.details["mixer"] == "x"
