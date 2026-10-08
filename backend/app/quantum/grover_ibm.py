# QISKIT INTEGRATION: runs Grover amplitude-amplification circuits (DiagonalGate oracle + grover_operator)
# on IBM hardware through qiskit_ibm_runtime (executor_sampler.Sampler, job mode, dynamical decoupling,
# Pauli twirling) after transpiling with generate_preset_pass_manager; local testing on a fake backend.
"""Grover amplitude amplification on a real IBM QPU (Q3: 3 qubits, 8 battery plans).

What is run: the LAST stage of the adaptive search, when the threshold sits just above the optimum, so the
oracle marks exactly ONE plan, the cheapest. Circuits with j = 0, 1, 2 Grover rounds (j = 0 is plain uniform
guessing, 1/8 = 12.5%). Ideal success probability sin^2((2j+1) theta), sin(theta) = 1/sqrt(8): 12.5%, 78.1%, 94.5%.
The measured values show how much of that amplification survives hardware noise. This demonstrates the
amplification mechanism; it is NOT a speedup measurement (the search itself is classical-quantum, see grover.py).

Same rules as ibm_runner.py: a real submission needs confirm=True (the user's explicit approval); job mode,
no sessions; a hard max_execution_time caps worst-case QPU usage. Fake backends run locally and are labelled
"simulation", never "hardware".
"""

import json
import math
from dataclasses import asdict

import numpy as np
from qiskit import QuantumCircuit
from qiskit.providers import BackendV2

from app.config import RUNS_DIR
from app.grid.presets import load_preset
from app.provenance import library_versions, utc_now
from app.quantum import grover
from app.quantum.ibm_runner import HardwareOptions, NotApproved, is_fake, make_sampler
from app.quantum.qubo import build_qubo
from app.quantum.transpile import circuit_stats, transpile_for_backend

JOBS_FILE = RUNS_DIR / "ibm_grover_jobs.json"
ROUNDS = (0, 1, 2)
TIER = "Q3"


def experiment(preset: str = "scenario_b") -> dict:
    """The marked plan (the optimum) and the ideal success probabilities."""
    energies = build_qubo(load_preset(preset), TIER).energies_all()
    optimum = int(np.argmin(energies))
    return {"preset": preset, "tier": TIER, "energies": energies, "optimum_index": optimum,
            "ideal": [grover.marked_set_probability(len(energies), 1, j) for j in ROUNDS]}


def circuits(exp: dict) -> list[QuantumCircuit]:
    out = []
    for j in ROUNDS:
        qc = grover.grover_circuit(3, np.array([exp["optimum_index"]]), j)
        qc.measure_all()  # clbit i = qubit i, so counts key int(key, 2) = plan index
        out.append(qc)
    return out


def prepare(exp: dict, backend: BackendV2, opts: HardwareOptions) -> list[dict]:
    return [{"rounds": j, "circuit": transpile_for_backend(qc, backend, opts.seed_transpiler)}
            for j, qc in zip(ROUNDS, circuits(exp))]


def submit(pubs: list[dict], backend: BackendV2, opts: HardwareOptions, confirm: bool = False):
    if not is_fake(backend) and not confirm:
        raise NotApproved("hardware submission needs explicit user approval (confirm=True)")
    job = make_sampler(backend, opts).run([(p["circuit"],) for p in pubs])
    if not is_fake(backend):
        RUNS_DIR.mkdir(exist_ok=True)
        jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8")) if JOBS_FILE.exists() else []
        jobs.append({"job_id": job.job_id(), "backend": backend.name, "submitted_at": utc_now(),
                     "options": asdict(opts), "rounds": list(ROUNDS),
                     "circuit_stats": [circuit_stats(p["circuit"]) for p in pubs]})
        JOBS_FILE.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
    return job


def collect(exp: dict, pubs_stats: list[dict], job, backend_name: str, opts: HardwareOptions, fake: bool) -> dict:
    result = job.result()
    try:
        usage = job.usage()
    except Exception:
        usage = None
    rows = []
    for i, j in enumerate(ROUNDS):
        counts = result[i].data.meas.get_counts()
        shots = sum(counts.values())
        hits = sum(c for key, c in counts.items() if int(key, 2) == exp["optimum_index"])
        p = hits / shots
        se = math.sqrt(p * (1 - p) / shots)
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:4]
        rows.append({"rounds": j, "shots": shots, "p_optimum_measured": p, "std_error": se,
                     "p_optimum_ideal": exp["ideal"][i], "uniform_guess": 1 / 8,
                     "amplification_over_guessing": p / (1 / 8), "transpiled": pubs_stats[i],
                     "top_outcomes": [{"plan_index": int(k, 2), "bitstring": k, "count": c} for k, c in top]})
    return {
        "kind": "grover_hardware" if not fake else "grover_simulation",
        "backend": backend_name if not fake else f"{backend_name} (local noisy simulation)",
        "job_id": job.job_id(), "created_at": utc_now(), "preset": exp["preset"], "tier": exp["tier"],
        "marked": "the optimal plan only (late stage of the adaptive search)",
        "optimum_index": exp["optimum_index"], "rows": rows, "qpu_usage_seconds_whole_job": usage,
        "options": asdict(opts) if not fake else {"local_testing_mode": True},
        "versions": library_versions("qiskit", "qiskit-aer", "qiskit-ibm-runtime"),
    }


def collect_recorded(job_id: str, service) -> dict:
    jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8")) if JOBS_FILE.exists() else []
    rec = next((j for j in jobs if j["job_id"] == job_id), None)
    if rec is None:
        raise KeyError(f"job {job_id} not found in {JOBS_FILE}")
    exp = experiment()
    return collect(exp, rec["circuit_stats"], service.job(job_id), rec["backend"],
                   HardwareOptions(**rec["options"]), fake=False)
