"""Stage 7: QAOA (fixed, simulator-trained angles) on IBM Quantum hardware.

Run from the project root (cmd). Modes, in the order you would use them:

  python backend\\scripts\\run_ibm.py local [tier]
        Same code path on the laptop with the FakeFez model (qiskit-ibm-runtime local testing
        mode). No account, no QPU time. Results are labelled aer_noisy.

  python backend\\scripts\\run_ibm.py estimate [tier] [backend_name]
        Connects to IBM, picks the least busy backend (or the named one), transpiles, and does a
        server-side DRY RUN to estimate QPU seconds. Does NOT execute on a QPU.

  python backend\\scripts\\run_ibm.py submit --yes [tier] [backend_name]
        REAL hardware run. Uses QPU time. Requires --yes. Prints the job id and waits for results.

  python backend\\scripts\\run_ibm.py collect <job_id>
        Fetch a previously submitted job (e.g. after waiting in the queue).

Default tier: Q3 (p = 1..3, 4096 shots each, one job). Default scenario: scenario_b.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.grid.presets import load_preset  # noqa: E402
from app.quantum import ibm_runner as ibm  # noqa: E402
from app.quantum.simulate import run_depth_sweep  # noqa: E402
from app.quantum.transpile import fake_backend  # noqa: E402

PRESET = "scenario_b"


def pct(x):
    return f"{100 * x:5.1f}%"


def show(results):
    r0 = results[0]
    print(f"\nsource={r0.source} | backend={r0.provenance.backend} | job id={r0.provenance.job_id}")
    usage = r0.details.get("qpu_usage_seconds_whole_job")
    if usage is not None:
        print(f"QPU usage for the whole job: {usage} s")
    print(f"  {'p':>2} {'2q gates':>9} {'shots':>6} | {'P(opt) ideal':>12} {'P(opt) here':>12} |"
          f" {'AR ideal':>8} {'AR here':>8} | best found")
    for r in results:
        d = r.details
        bf = d["best_found"]
        best = f"{[int(v) for v in bf['path']]} ${bf['objective']:,.0f}" if bf else "none feasible"
        print(f"  {d['reps']:>2} {d['circuit']['transpiled']['two_qubit_gates']:>9} {r.provenance.shots:>6} |"
              f" {pct(d['ideal_exact']['p_optimal']):>12} {pct(d['qaoa_sampled']['p_optimal']):>12} |"
              f" {d['ideal_exact']['approximation_ratio']:8.3f} {d['qaoa_sampled']['approximation_ratio']:8.3f} | {best}")
    print(f"  uniform random: P(opt) {pct(r0.details['random_exact']['p_optimal'])}"
          f"  AR {r0.details['random_exact']['approximation_ratio']:.3f}")


def plan(tier, backend, opts):
    sc = load_preset(PRESET)
    print(f"Training {tier} on the ideal simulator (p = 1..3)...")
    ideal = run_depth_sweep(sc, tier, max_reps=3, shots=opts.shots)
    pubs = ibm.prepare(sc, ideal, backend, opts)
    print(f"Backend {backend.name}: {len(pubs)} circuits x {opts.shots} shots, one job")
    for p in pubs:
        s = p["stats"]
        print(f"  p={p['ideal'].details['reps']}: depth {s['depth']}, 2-qubit gates {s['two_qubit_gates']},"
              f" active qubits {s['active_qubits']}")
    return sc, ideal, pubs


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    mode, rest = argv[0], argv[1:]
    yes = "--yes" in rest
    rest = [a for a in rest if a != "--yes"]
    opts = ibm.HardwareOptions()

    if mode == "collect":
        show(ibm.collect_recorded(rest[0]))
        return 0

    tier = rest[0] if rest else "Q3"
    name = rest[1] if len(rest) > 1 else None

    if mode == "local":
        backend = fake_backend(name or "FakeFez")
        sc, ideal, pubs = plan(tier, backend, opts)
        job = ibm.submit(sc, pubs, backend, opts)
        show(ibm.collect(sc, [p["stats"] for p in pubs], ideal, job, backend.name, opts, fake=True))
        return 0

    if mode not in ("estimate", "submit"):
        print(f"unknown mode '{mode}'")
        return 1

    service = ibm.get_service()
    from app.quantum.qubo import build_qubo
    n = build_qubo(load_preset(PRESET), tier).num_qubits
    backend = ibm.select_backend(service, n, name)
    print(f"Selected backend: {backend.name} ({backend.num_qubits} qubits, "
          f"{backend.status().pending_jobs} pending jobs)")
    sc, ideal, pubs = plan(tier, backend, opts)

    remaining = service.usage().get("usage_remaining_seconds")
    print(f"QPU time remaining on this account: {remaining} s | this job is capped at "
          f"{opts.max_execution_time} s (IBM cancels it beyond that)")

    if mode == "estimate":
        secs = ibm.estimate_qpu_seconds(pubs, backend, opts)
        if secs is None:
            print("\nDRY RUN not available for this account (no QPU used). Worst case for a real run is the "
                  f"{opts.max_execution_time} s cap.")
        else:
            print(f"\nDRY RUN (no QPU used): estimated QPU time = {secs} s")
        print("To run for real:  python backend\\scripts\\run_ibm.py submit --yes "
              f"{tier} {backend.name}")
        return 0

    if not yes:
        print("\nNot submitted: add --yes to confirm a REAL hardware run (uses QPU time).")
        return 1
    job = ibm.submit(sc, pubs, backend, opts, confirm=True)
    print(f"\nSUBMITTED job {job.job_id()} to {backend.name} (QPU cap {opts.max_execution_time} s). "
          f"Recorded in {ibm.JOBS_FILE}.")
    print("Waiting for results (Ctrl+C is safe; fetch later with: "
          f"python backend\\scripts\\run_ibm.py collect {job.job_id()})")
    show(ibm.collect(sc, [p["stats"] for p in pubs], ideal, job, backend.name, opts, fake=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
