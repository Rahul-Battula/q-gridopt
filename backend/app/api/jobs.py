"""Background execution of long runs (QAOA simulator and IBM hardware).

POST endpoints create a 'queued' run and hand it to a single worker thread (QAOA is CPU-heavy, so
runs execute one at a time). The worker writes progress, results and errors to the RunStore;
clients poll GET /api/runs/{run_id}.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from app.api.schemas import IbmRequest, SimulatorRequest
from app.quantum import ibm_runner as ibm
from app.quantum.simulate import run_noisy_simulation, run_qaoa_simulation
from app.quantum.transpile import fake_backend
from app.store.db import RunStore

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, store: RunStore):
        self.store = store
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qgridopt-run")
        self._active: set[str] = set()
        self._lock = threading.Lock()

    def submit(self, run_id: str, fn, *args) -> None:
        with self._lock:
            self._active.add(run_id)
        self._pool.submit(self._wrap, run_id, fn, *args)

    def is_active(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._active

    def _wrap(self, run_id: str, fn, *args) -> None:
        try:
            fn(self.store, run_id, *args)
        except Exception as exc:  # report every failure on the run instead of losing it
            log.exception("run %s failed", run_id)
            self.store.update(run_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        finally:
            with self._lock:
                self._active.discard(run_id)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


def run_simulator(store: RunStore, run_id: str, req: SimulatorRequest) -> None:
    sc = req.resolve()
    ideal, warm = [], None
    for reps in range(1, req.max_reps + 1):
        store.update(run_id, status="running", progress=f"training + ideal sampling p={reps} of {req.max_reps}")
        result, warm = run_qaoa_simulation(sc, req.tier, reps, shots=req.shots, seed=req.seed,
                                           warm_start=warm, penalty=req.penalty)
        ideal.append(result)
        store.update(run_id, results=ideal)
    results = list(ideal)
    if req.noisy:
        for r in ideal:
            store.update(run_id, progress=f"noisy simulation ({req.noise_backend}) p={r.details['reps']}")
            results.append(run_noisy_simulation(sc, r, backend_name=req.noise_backend))
            store.update(run_id, results=results)
    store.update(run_id, status="completed", progress=None, results=results)


def run_ibm(store: RunStore, run_id: str, req: IbmRequest) -> None:
    sc = req.resolve()
    opts = ibm.HardwareOptions(shots=req.shots, dynamical_decoupling=req.dynamical_decoupling,
                               twirl_gates=req.twirling, twirl_measure=req.twirling, seed_transpiler=req.seed)
    store.update(run_id, status="running", progress="training angles on the ideal simulator")
    ideal, warm = [], None
    for reps in range(1, req.max_reps + 1):
        result, warm = run_qaoa_simulation(sc, req.tier, reps, shots=req.shots, seed=req.seed, warm_start=warm)
        ideal.append(result)

    fake = req.backend is not None and req.backend.startswith("Fake")
    if fake:
        backend = fake_backend(req.backend)
    else:
        store.update(run_id, progress="connecting to IBM Quantum")
        service = ibm.get_service()
        backend = ibm.select_backend(service, ideal[0].details["num_qubits"], req.backend)

    store.update(run_id, progress=f"transpiling for {backend.name}")
    pubs = ibm.prepare(sc, ideal, backend, opts)
    job = ibm.submit(sc, pubs, backend, opts, confirm=req.confirm)
    if not fake:
        store.update(run_id, status="submitted", job_id=job.job_id(),
                     progress=f"waiting in the IBM queue on {backend.name}")
    results = ibm.collect(sc, [p["stats"] for p in pubs], ideal, job, backend.name, opts, fake=fake)
    store.update(run_id, status="completed", progress=None, job_id=job.job_id(), results=results)


def refresh_submitted(store: RunStore, run: dict) -> None:
    """A hardware run left 'submitted' (e.g. the server restarted while the job was queued):
    ask IBM whether the job finished and, if so, collect it. Never raises."""
    try:
        service = ibm.get_service()
        job = service.job(run["job_id"])
        if not job.in_final_state():
            return
        if job.done():
            store.update(run["run_id"], status="completed", progress=None,
                         results=ibm.collect_recorded(run["job_id"], service))
        else:
            store.update(run["run_id"], status="failed", progress=None,
                         error=f"IBM job ended without results: {job.status()}")
    except Exception as exc:
        log.warning("could not refresh run %s: %s", run["run_id"], exc)
