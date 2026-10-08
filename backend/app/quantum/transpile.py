# QISKIT INTEGRATION: fits QAOA circuits to an IBM chip with
# qiskit.transpiler.generate_preset_pass_manager, and loads IBM device models from
# qiskit_ibm_runtime.fake_provider (snapshots of real IBM backends incl. their noise).
"""Transpilation and circuit statistics.

Plain English: a real chip only has a few native gates (Heron: CZ, SX, RZ, X) and each qubit
talks only to its neighbours. Transpiling rewrites the QAOA circuit into those gates and
inserts SWAPs to move information between distant qubits. Every extra 2-qubit gate adds noise,
so we report the circuit size before and after.

"logical" stats  = the circuit in the chip's native gates, assuming every qubit can talk to
                   every other (no routing).
"transpiled" stats = the real mapping onto the chip's qubit layout (with routing).
"""

from qiskit import QuantumCircuit
from qiskit.providers import BackendV2
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_ibm_runtime import fake_provider

DEFAULT_FAKE_BACKEND = "FakeFez"  # IBM Heron r2, 156 qubits, CZ gates (Open Plan generation)
OPTIMIZATION_LEVEL = 3


def fake_backend(name: str = DEFAULT_FAKE_BACKEND) -> BackendV2:
    if not name.startswith("Fake") or not hasattr(fake_provider, name):
        raise ValueError(f"unknown fake backend '{name}'")
    return getattr(fake_provider, name)()


def transpile_for_backend(circuit: QuantumCircuit, backend: BackendV2, seed: int = 1) -> QuantumCircuit:
    pm = generate_preset_pass_manager(optimization_level=OPTIMIZATION_LEVEL, backend=backend,
                                      seed_transpiler=seed)
    return pm.run(circuit)


def logical_circuit(circuit: QuantumCircuit, backend: BackendV2, seed: int = 1) -> QuantumCircuit:
    """Native gates of the backend, but all-to-all connectivity (no routing)."""
    basis = [name for name in backend.target.operation_names
             if name not in ("delay", "for_loop", "if_else", "switch_case", "measure_2")]
    pm = generate_preset_pass_manager(optimization_level=OPTIMIZATION_LEVEL, basis_gates=basis,
                                      seed_transpiler=seed)
    return pm.run(circuit)


def circuit_stats(circuit: QuantumCircuit) -> dict:
    ops = circuit.count_ops()
    two_q = sum(1 for inst in circuit.data
                if inst.operation.num_qubits == 2 and inst.operation.name != "barrier")
    active = {circuit.find_bit(q).index for inst in circuit.data for q in inst.qubits
              if inst.operation.name != "barrier"}
    return {
        "depth": circuit.depth(),
        "two_qubit_gates": two_q,
        "two_qubit_depth": circuit.depth(lambda inst: inst.operation.num_qubits == 2),
        "total_gates": sum(v for k, v in ops.items() if k not in ("barrier", "measure")),
        "active_qubits": len(active),
        "ops": {k: int(v) for k, v in ops.items()},
    }
