# QISKIT INTEGRATION: real IBM Quantum hardware through qiskit_ibm_runtime: QiskitRuntimeService
# (account + least_busy backend), the client-side executor_sampler.Sampler in job mode, dynamical
# decoupling + Pauli twirling options, and job usage (QPU seconds) / dry-run usage estimates.
"""Run trained QAOA circuits on IBM Quantum hardware (Stage 7).

Rules (CLAUDE.md):
- Angles are FIXED from ideal simulator training; nothing is trained on hardware.
- Nothing is submitted to a real QPU without confirm=True (the user's explicit approval).
- Open Plan: no sessions. One job (all depths p as separate pubs) in job mode.

API notes for qiskit-ibm-runtime 0.50.0:
- qiskit_ibm_runtime.SamplerV2 is DEPRECATED; executor_sampler.Sampler is the replacement with the
  same mode/options/run interface. Verified locally with fake backends.
- Sampler.run(..., dry_run=True) validates the job server-side and returns an estimated QPU time
  WITHOUT executing on a QPU (job.usage_estimation["quantum_seconds"]).
- With twirling on, IBM rounds shots up to fit the randomizations, so the shot count actually
  returned is read from the counts.

Local testing: passing a fake backend (e.g. FakeFez) runs the same code on the laptop. Those
results are labelled source="aer_noisy", never "ibm_hardware".
"""

import json
from dataclasses import asdict, dataclass

from qiskit.providers import BackendV2
from qiskit.providers.exceptions import QiskitBackendNotFoundError
from qiskit_ibm_runtime import QiskitRuntimeService
from qiskit_ibm_runtime.executor_sampler import Sampler
from qiskit_ibm_runtime.fake_provider.fake_backend import FakeBackendV2

from app.config import RUNS_DIR, IbmCredentials, load_ibm_credentials
from app.models.grid import Scenario
from app.models.result import Provenance, SolverResult
from app.provenance import library_versions, utc_now
from app.quantum import aer_runner, decoder
from app.quantum.qaoa import parameter_values, qaoa_circuit
from app.quantum.simulate import QISKIT_PACKAGES, build_sampled_result, cost_for
from app.quantum.transpile import circuit_stats

JOBS_FILE = RUNS_DIR / "ibm_jobs.json"


@dataclass(frozen=True)
class HardwareOptions:
    shots: int = 4096
    dynamical_decoupling: bool = True
    dd_sequence: str = "XpXm"
    twirl_gates: bool = True
    twirl_measure: bool = True
    seed_transpiler: int = 1234
    # Hard cap on QPU (system execution) seconds: IBM force-cancels the job beyond it, so this is the
    # worst-case usage. Open Plan allowance is 600 s / 28 days.
    max_execution_time: int = 60


class NotApproved(RuntimeError):
    pass


def is_fake(backend: BackendV2) -> bool:
    return isinstance(backend, FakeBackendV2)


def get_service(creds: IbmCredentials | None = None) -> QiskitRuntimeService:
    c = creds or load_ibm_credentials()
    return QiskitRuntimeService(channel=c.channel, token=c.token, instance=c.instance)


def select_backend(service: QiskitRuntimeService, min_qubits: int, name: str | None = None) -> BackendV2:
    if name:
        return service.backend(name)
    return service.least_busy(operational=True, simulator=False, min_num_qubits=min_qubits)


def prepare(scenario: Scenario, ideal_results: list[SolverResult], backend: BackendV2,
            opts: HardwareOptions) -> list[dict]:
    """Transpile each ideal result's circuit for the backend and bind its trained angles."""
    tiers = {r.details["tier"] for r in ideal_results}
    if len(tiers) != 1 or any(r.source != "aer_statevector" for r in ideal_results):
        raise ValueError("pass aer_statevector results for a single tier")
    pubs = []
    for r in ideal_results:
        d = r.details
        _, cost = cost_for(scenario, d["tier"], d["penalty"])
        transpiled = aer_runner.transpile_measured(qaoa_circuit(cost, d["reps"]), backend, opts.seed_transpiler)
        pubs.append({"ideal": r, "circuit": transpiled,
                     "values": parameter_values(transpiled, d["gammas"], d["betas"]),
                     "stats": circuit_stats(transpiled)})
    return pubs


def make_sampler(backend: BackendV2, opts: HardwareOptions) -> Sampler:
    sampler = Sampler(mode=backend)
    sampler.options.default_shots = opts.shots
    if not is_fake(backend):  # these options have no effect (and warn) in local testing mode
        sampler.options.max_execution_time = opts.max_execution_time
        sampler.options.dynamical_decoupling.enable = opts.dynamical_decoupling
        sampler.options.dynamical_decoupling.sequence_type = opts.dd_sequence
        sampler.options.twirling.enable_gates = opts.twirl_gates
        sampler.options.twirling.enable_measure = opts.twirl_measure
    return sampler


def estimate_qpu_seconds(pubs: list[dict], backend: BackendV2, opts: HardwareOptions) -> float | None:
    """Server-side dry run: validates the job and estimates QPU time WITHOUT running on a QPU.

    Returns None when no estimate is available: local testing mode, or accounts without dry-run
    access (IBM needs a 'mock_<backend>' device for it; the Open Plan account tested on 2026-10-08
    did not have one). In that case the max_execution_time cap is the usage guarantee.
    """
    if is_fake(backend):
        return None
    try:
        job = make_sampler(backend, opts).run([(p["circuit"], p["values"]) for p in pubs], dry_run=True)
    except QiskitBackendNotFoundError:
        return None
    job.result()  # wait for the dry run to finish
    return job.usage_estimation.get("quantum_seconds")


def submit(scenario: Scenario, pubs: list[dict], backend: BackendV2, opts: HardwareOptions,
           confirm: bool = False):
    """Submit one job containing every depth. Real QPUs need confirm=True (user approval)."""
    if not is_fake(backend) and not confirm:
        raise NotApproved("hardware submission needs explicit user approval (confirm=True)")
    job = make_sampler(backend, opts).run([(p["circuit"], p["values"]) for p in pubs])
    if not is_fake(backend):
        _record(scenario, pubs, backend, opts, job.job_id())
    return job


def _record(scenario: Scenario, pubs: list[dict], backend: BackendV2, opts: HardwareOptions, job_id: str):
    RUNS_DIR.mkdir(exist_ok=True)
    jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8")) if JOBS_FILE.exists() else []
    jobs.append({
        "job_id": job_id, "backend": backend.name, "submitted_at": utc_now(),
        "scenario": scenario.model_dump(), "options": asdict(opts),
        "ideal_results": [p["ideal"].model_dump() for p in pubs],
        "circuit_stats": [p["stats"] for p in pubs],
    })
    JOBS_FILE.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def collect(scenario: Scenario, transpiled_stats: list[dict], ideal_results: list[SolverResult], job,
            backend_name: str, opts: HardwareOptions, fake: bool) -> list[SolverResult]:
    """Turn a finished job into one SolverResult per depth, scored by the shared evaluator."""
    result = job.result()
    try:
        usage = job.usage()
    except Exception:  # local jobs / usage not yet computed
        usage = None
    out = []
    for i, ideal in enumerate(ideal_results):
        d = ideal.details
        counts = result[i].data.meas.get_counts()
        model, _ = cost_for(scenario, d["tier"], d["penalty"])
        table = decoder.path_table(scenario, model)
        stats = transpiled_stats[i]
        details = {
            "tier": d["tier"], "reps": d["reps"], "num_qubits": model.num_qubits,
            "penalty": model.penalty, "seed": d["seed"], "gammas": d["gammas"], "betas": d["betas"],
            "pub_index": i, "ideal_exact": d["qaoa_exact"],
            "circuit": {"backend": backend_name, "logical": d["circuit"]["logical"], "transpiled": stats},
            "hardware_options": asdict(opts) if not fake else {"local_testing_mode": True},
            "qpu_usage_seconds_whole_job": usage,
        }
        provenance = Provenance(
            method=f"QAOA p={d['reps']} on {d['tier']}, fixed angles from ideal training",
            backend=backend_name if not fake else f"{backend_name} (qiskit-ibm-runtime local testing mode)",
            job_id=job.job_id(), shots=sum(counts.values()), timestamp=utc_now(),
            library_versions=library_versions(*QISKIT_PACKAGES),
        )
        source = "aer_noisy" if fake else "ibm_hardware"
        out.append(build_sampled_result(source, scenario, counts, table, provenance, details))
    return out


def collect_recorded(job_id: str, service: QiskitRuntimeService | None = None) -> list[SolverResult]:
    """Fetch a previously submitted hardware job by id (e.g. after it waited in the queue)."""
    jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8")) if JOBS_FILE.exists() else []
    rec = next((j for j in jobs if j["job_id"] == job_id), None)
    if rec is None:
        raise KeyError(f"job {job_id} not found in {JOBS_FILE}")
    service = service or get_service()
    scenario = Scenario.model_validate(rec["scenario"])
    ideal = [SolverResult.model_validate(r) for r in rec["ideal_results"]]
    return collect(scenario, rec["circuit_stats"], ideal, service.job(job_id), rec["backend"],
                   HardwareOptions(**rec["options"]), fake=False)
