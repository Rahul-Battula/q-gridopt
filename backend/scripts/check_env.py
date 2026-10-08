"""Stage 0 environment check.

Run from the project root (cmd):
    venv\\Scripts\\activate.bat
    python backend\\scripts\\check_env.py

Prints installed library versions, runs a 2-qubit Bell circuit on AerSimulator,
and solves a tiny LP with PuLP/CBC. Exits with code 1 if any check fails.
"""

import sys
from importlib.metadata import PackageNotFoundError, version

PACKAGES = ["qiskit", "qiskit-aer", "qiskit-ibm-runtime", "qiskit-optimization", "pulp"]


def check_python() -> bool:
    print(f"Python {sys.version.split()[0]} ({sys.executable})")
    ok = sys.version_info[:2] == (3, 12)
    if not ok:
        print("  FAIL: Python 3.12 required")
    return ok


def check_versions() -> bool:
    print("\n[1] Installed versions")
    ok = True
    for pkg in PACKAGES:
        try:
            print(f"  {pkg:<22} {version(pkg)}")
        except PackageNotFoundError:
            print(f"  {pkg:<22} NOT INSTALLED")
            ok = False
    # Importing (not just metadata) catches broken installs / incompatible pairs.
    try:
        import qiskit_ibm_runtime  # noqa: F401
        import qiskit_optimization  # noqa: F401
    except Exception as exc:  # report any import failure, then continue
        print(f"  FAIL: import error: {exc!r}")
        ok = False
    return ok


def check_bell() -> bool:
    print("\n[2] Bell circuit on AerSimulator (1024 shots)")
    from qiskit import QuantumCircuit, transpile
    from qiskit_aer import AerSimulator

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    print(qc.draw(output="text"))

    sim = AerSimulator(seed_simulator=42)
    counts = sim.run(transpile(qc, sim), shots=1024).result().get_counts()
    print(f"  counts: {dict(sorted(counts.items()))}")

    # An ideal Bell state only ever yields 00 or 11, roughly 50/50.
    ok = set(counts) <= {"00", "11"} and all(abs(c / 1024 - 0.5) < 0.1 for c in counts.values())
    print("  OK: only 00/11, ~50/50" if ok else "  FAIL: unexpected Bell distribution")
    return ok


def check_lp() -> bool:
    print("\n[3] Tiny LP with PuLP (CBC)")
    import pulp

    # Meet demand 100 MW: solar (<= 60, $0/MWh) then gas ($60/MWh). Optimum: solar 60, gas 40, $2400.
    prob = pulp.LpProblem("tiny_dispatch", pulp.LpMinimize)
    solar = prob.add_variable("solar", lowBound=0, upBound=60)
    gas = prob.add_variable("gas", lowBound=0, upBound=100)
    prob += 0 * solar + 60 * gas
    prob += solar + gas == 100, "balance"
    stats = prob.solve(pulp.COIN_CMD(msg=False))

    status = stats.status.name
    obj = pulp.value(prob.objective)
    print(f"  status={status} solar={solar.value()} gas={gas.value()} objective=${obj:,.0f}")
    ok = stats.status == pulp.LpSolveStatus.Optimal and abs(obj - 2400) < 1e-6
    print("  OK: matches expected $2,400" if ok else "  FAIL: expected Optimal, $2,400")
    return ok


def main() -> int:
    results = [check_python(), check_versions(), check_bell(), check_lp()]
    print("\nALL CHECKS PASSED" if all(results) else "\nSOME CHECKS FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
