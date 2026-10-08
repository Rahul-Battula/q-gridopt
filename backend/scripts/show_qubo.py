"""Show the QUBO and Ising Hamiltonian for every tier.

Run from the project root (cmd):
    python backend\\scripts\\show_qubo.py [preset_id]      (default: scenario_b)
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.grid.presets import DEFAULT_PRESET, load_preset  # noqa: E402
from app.grid.tiers import TIERS  # noqa: E402
from app.quantum.ising import ising_energies, qubo_to_ising  # noqa: E402
from app.quantum.qubo import build_qubo  # noqa: E402

preset = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PRESET
sc = load_preset(preset)
print(f"===== {sc.name} ({preset}) =====")

for tier in TIERS:
    m = build_qubo(sc, tier)
    op, offset = qubo_to_ising(m)
    e = ising_energies(op, offset)
    k = int(np.argmin(e))
    x = [(k >> i) & 1 for i in range(m.num_qubits)]
    valid = sum(m.decode([(s >> i) & 1 for i in range(m.num_qubits)]) is not None for s in range(len(e)))
    zz = sum(1 for z in op.paulis.z if z.sum() == 2)

    print(f"\n[{tier}] {m.num_qubits} qubits | encoding: {'one-hot' if m.one_hot else 'binary (1 bit/hour)'}"
          f" | penalty A = ${m.penalty:,.0f}")
    print(f"  QUBO terms: {len(m.linear)} linear, {len(m.quadratic)} quadratic, constant {m.constant:,.1f}")
    print(f"  Ising: {len(op)} Pauli terms ({zz} ZZ couplings), offset {offset:,.1f}")
    print(f"  bitstrings: {len(e):,} total, {valid:,} valid (one level per hour)")
    print(f"  ground state x = {x} -> battery path {m.decode(x)} -> energy ${e[k]:,.0f}")

    if tier == "Q3":
        print("\n  Q3 QuadraticProgram (Qiskit Optimization):")
        for line in m.program.prettyprint().splitlines():
            print(f"    {line}")
        print("\n  Q3 cost Hamiltonian H (energy = <H> + offset):")
        for label, coef in sorted(zip(op.paulis.to_labels(), op.coeffs.real)):
            print(f"    {coef:>+12,.2f} * {label}")
