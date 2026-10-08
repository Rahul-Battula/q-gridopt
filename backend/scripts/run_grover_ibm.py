r"""Grover amplitude amplification on IBM hardware (Q3, 3 qubits, circuits with 0, 1 and 2 Grover rounds).

Run from the project root (cmd). Modes, in the order you would use them:

  python backend\scripts\run_grover_ibm.py local [FakeBackend]
        Same code path on the laptop with the FakeFez noise model. No account, no QPU time.

  python backend\scripts\run_grover_ibm.py submit --yes [backend_name]
        REAL hardware run. Uses QPU time (3 circuits x 4096 shots, one job, capped at 60 s). Requires --yes.

  python backend\scripts\run_grover_ibm.py collect <job_id>
        Fetch a previously submitted job.

Results are written to data/benchmarks/grover_hardware.json (real hardware) or grover_local.json (simulation).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.quantum import grover_ibm as gi  # noqa: E402
from app.quantum import ibm_runner as ibm  # noqa: E402
from app.quantum.transpile import circuit_stats, fake_backend  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "benchmarks"


def pct(x):
    return f"{100 * x:5.1f}%"


def show_and_save(result: dict) -> None:
    print(f"\n{result['kind']} | backend={result['backend']} | job id={result['job_id']}")
    if result.get("qpu_usage_seconds_whole_job") is not None:
        print(f"QPU usage for the whole job: {result['qpu_usage_seconds_whole_job']} s")
    print(f"  {'rounds':>6} {'2q gates':>9} {'shots':>6} | {'ideal':>7} {'measured':>9} {'+/-':>6} | amplification over guessing")
    for r in result["rows"]:
        print(f"  {r['rounds']:>6} {r['transpiled']['two_qubit_gates']:>9} {r['shots']:>6} | {pct(r['p_optimum_ideal']):>7} "
              f"{pct(r['p_optimum_measured']):>9} {100 * r['std_error']:5.1f}% | {r['amplification_over_guessing']:.1f}x (uniform guess 12.5%)")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / ("grover_hardware.json" if result["kind"] == "grover_hardware" else "grover_local.json")
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"wrote {path}")


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    mode, rest = argv[0], argv[1:]
    yes = "--yes" in rest
    rest = [a for a in rest if a != "--yes"]
    opts = ibm.HardwareOptions()

    if mode == "collect":
        show_and_save(gi.collect_recorded(rest[0], ibm.get_service()))
        return 0

    exp = gi.experiment()
    print(f"Marked plan: index {exp['optimum_index']} (the cheapest). Ideal success: "
          + ", ".join(f"{r} rounds {pct(p)}" for r, p in zip(gi.ROUNDS, exp["ideal"])))

    if mode == "local":
        backend = fake_backend(rest[0] if rest else "FakeFez")
        pubs = gi.prepare(exp, backend, opts)
        stats = [circuit_stats(p["circuit"]) for p in pubs]
        job = gi.submit(pubs, backend, opts)
        show_and_save(gi.collect(exp, stats, job, backend.name, opts, fake=True))
        return 0

    if mode != "submit":
        print(f"unknown mode '{mode}'")
        return 1

    service = ibm.get_service()
    backend = ibm.select_backend(service, 3, rest[0] if rest else None)
    print(f"Selected backend: {backend.name} ({backend.num_qubits} qubits, {backend.status().pending_jobs} pending jobs)")
    pubs = gi.prepare(exp, backend, opts)
    stats = [circuit_stats(p["circuit"]) for p in pubs]
    for p, s in zip(pubs, stats):
        print(f"  {p['rounds']} rounds: depth {s['depth']}, 2-qubit gates {s['two_qubit_gates']}")
    print(f"QPU time remaining: {service.usage().get('usage_remaining_seconds')} s | job capped at {opts.max_execution_time} s")
    if not yes:
        print("\nNot submitted: add --yes to confirm a REAL hardware run (uses QPU time).")
        return 1
    job = gi.submit(pubs, backend, opts, confirm=True)
    print(f"\nSUBMITTED job {job.job_id()} to {backend.name}. Recorded in {gi.JOBS_FILE}.")
    print(f"Waiting for results (Ctrl+C is safe; fetch later with: python backend\\scripts\\run_grover_ibm.py collect {job.job_id()})")
    show_and_save(gi.collect(exp, stats, job, backend.name, opts, fake=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
