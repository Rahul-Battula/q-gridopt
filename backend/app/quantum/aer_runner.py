# QISKIT INTEGRATION: runs trained QAOA circuits on qiskit_aer's AerSimulator: shot sampling with
# qiskit_aer.primitives.SamplerV2 and exact output probabilities from the saved statevector.
"""Simulation of a trained QAOA circuit: ideal (no noise) and noisy (IBM device noise model).

Bit order: Qiskit counts keys and statevector indices both read qubit i as bit i of the
integer (rightmost character of the key = qubit 0), so  index k = int(key, 2).
measure_all() is added BEFORE transpiling, so classical bit i always holds logical qubit i,
wherever the transpiler placed it on the chip.
"""

import numpy as np
from qiskit import QuantumCircuit
from qiskit.providers import BackendV2
from qiskit_aer import AerSimulator
from qiskit_aer.primitives import SamplerV2

from app.quantum.transpile import transpile_for_backend


def sample_ideal(circuit: QuantumCircuit, values: np.ndarray, shots: int, seed: int) -> dict[str, int]:
    measured = circuit.copy()
    measured.measure_all()
    sampler = SamplerV2(seed=seed, options={"backend_options": {"method": "statevector"}})
    result = sampler.run([(measured, values)], shots=shots).result()
    return result[0].data.meas.get_counts()


def transpile_measured(circuit: QuantumCircuit, backend: BackendV2, seed: int) -> QuantumCircuit:
    measured = circuit.copy()
    measured.measure_all()
    return transpile_for_backend(measured, backend, seed)


def sample_noisy(transpiled: QuantumCircuit, values: np.ndarray, backend: BackendV2,
                 shots: int, seed: int) -> dict[str, int]:
    """Sample an already-transpiled, measured circuit on Aer with the backend's noise model."""
    sampler = SamplerV2.from_backend(AerSimulator.from_backend(backend), seed=seed)
    result = sampler.run([(transpiled, values)], shots=shots).result()
    return result[0].data.meas.get_counts()


def sample_transpiled_ideal(transpiled: QuantumCircuit, values: np.ndarray, shots: int,
                            seed: int) -> dict[str, int]:
    """Same transpiled circuit, no noise. Isolates the effect of noise from that of transpiling."""
    sampler = SamplerV2(seed=seed)
    result = sampler.run([(transpiled, values)], shots=shots).result()
    return result[0].data.meas.get_counts()


def exact_probabilities(circuit: QuantumCircuit, values: np.ndarray) -> np.ndarray:
    """Probability of every basis state (length 2^n) with no shot noise."""
    bound = circuit.assign_parameters(values)
    bound.save_statevector()
    sv = AerSimulator(method="statevector").run(bound).result().get_statevector()
    return np.abs(np.asarray(sv)) ** 2
