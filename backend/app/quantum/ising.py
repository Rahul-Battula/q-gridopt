# QISKIT INTEGRATION: converts the QUBO into a cost Hamiltonian as a
# qiskit.quantum_info.SparsePauliOp (the operator QAOA minimises), cross-checked against
# qiskit_optimization's own QuadraticProgram.to_ising().
"""QUBO -> Ising Hamiltonian.

Plain English: a quantum computer measures qubits as +1/-1 "spins" (Pauli Z), not 0/1.
Substituting x = (1 - Z) / 2 rewrites the $ cost as an energy operator whose lowest-energy
state is the cheapest battery path.

    c x_i        ->  c/2 - c/2 Z_i
    c x_i x_j    ->  c/4 (1 - Z_i - Z_j + Z_i Z_j)

Convention (same as qiskit_optimization): variable i <-> qubit i, and the constant is returned
separately as `offset`, so  QUBO energy = <H> + offset.
"""

import numpy as np
from qiskit.quantum_info import SparsePauliOp
from qiskit_optimization.translators import to_ising

from app.quantum.qubo import QuboModel


def qubo_to_ising(model: QuboModel) -> tuple[SparsePauliOp, float]:
    n = model.num_qubits
    offset = model.constant
    terms: list[tuple[str, list[int], float]] = []
    for i, c in model.linear.items():
        offset += c / 2
        terms.append(("Z", [i], -c / 2))
    for (i, j), c in model.quadratic.items():
        offset += c / 4
        terms += [("Z", [i], -c / 4), ("Z", [j], -c / 4), ("ZZ", [i, j], c / 4)]
    op = SparsePauliOp.from_sparse_list(terms, num_qubits=n).simplify()
    return op, offset


def qiskit_reference_ising(model: QuboModel) -> tuple[SparsePauliOp, float]:
    """Independent conversion by qiskit_optimization, used to cross-check qubo_to_ising."""
    return to_ising(model.program)


def ising_energies(op: SparsePauliOp, offset: float) -> np.ndarray:
    """<z|H|z> + offset for every computational basis state z (entry k: qubit i = bit i of k).
    Only valid for diagonal (all-Z) operators, which cost Hamiltonians are."""
    if op.paulis.x.any():
        raise ValueError("operator has X/Y terms; not a diagonal cost Hamiltonian")
    k = np.arange(2 ** op.num_qubits, dtype=np.uint64)
    energies = np.full(k.shape, offset, dtype=float)
    for z_mask, coef in zip(op.paulis.z, op.coeffs):
        mask = np.uint64(sum(1 << i for i in np.flatnonzero(z_mask)))
        parity = np.bitwise_count(k & mask) & 1
        energies += coef.real * (1 - 2 * parity.astype(float))
    return energies
