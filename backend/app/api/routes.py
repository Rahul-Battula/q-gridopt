"""HTTP endpoints. All optimisation happens here in the backend; the frontend only displays results."""

import json

import numpy as np
from fastapi import APIRouter, HTTPException, Request, status

from app.api import jobs
from app.benchmark.suite import RESULTS_DIR
from app.api.schemas import (
    ClassicalRequest,
    IbmRequest,
    PresetOut,
    QuboPreviewRequest,
    RunAccepted,
    RunOut,
    RunSummary,
    SimulatorRequest,
)
from app.classical.exact import solve_exact
from app.classical.lp import solve_lp
from app.classical.no_battery import solve_no_battery
from app.config import MissingCredentials, load_ibm_credentials
from app.grid.presets import DEFAULT_PRESET, list_presets
from app.grid.tiers import TIERS
from app.provenance import library_versions, utc_now
from app.quantum.draw import circuit_svg
from app.quantum.ising import ising_energies, qubo_to_ising
from app.quantum.qaoa import qaoa_circuit
from app.quantum.qubo import PENALTY_FACTOR
from app.quantum.simulate import circuit_report, cost_for
from app.quantum.transpile import fake_backend

router = APIRouter(prefix="/api")

PACKAGES = ("qiskit", "qiskit-aer", "qiskit-ibm-runtime", "qiskit-optimization", "pulp", "fastapi")


def _unprocessable(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc).strip("'\""))


def _resolve(req):
    try:
        return req.resolve()
    except KeyError as exc:
        raise _unprocessable(exc) from exc


def _ibm_configured() -> bool:
    try:
        load_ibm_credentials()
        return True
    except MissingCredentials:
        return False


def _summary(run: dict) -> dict:
    feasible = [r.evaluation.objective for r in run["results"] if r.evaluation is not None]
    return {**{k: run[k] for k in ("run_id", "kind", "status", "progress", "scenario_name",
                                   "created_at", "updated_at", "job_id")},
            "sources": sorted({r.source for r in run["results"]}),
            "best_objective": min(feasible) if feasible else None}


# ---------- info ----------

@router.get("/health")
def health():
    return {"status": "ok", "time": utc_now(), "default_preset": DEFAULT_PRESET,
            "ibm_credentials_configured": _ibm_configured(), "versions": library_versions(*PACKAGES)}


@router.get("/scenarios/presets", response_model=list[PresetOut])
def presets():
    return [PresetOut(id=pid, default=pid == DEFAULT_PRESET, scenario=sc) for pid, sc in list_presets().items()]


@router.post("/qubo/preview")
def qubo_preview(req: QuboPreviewRequest):
    sc = _resolve(req)
    try:
        model, cost = cost_for(sc, req.tier, req.penalty)
    except ValueError as exc:
        raise _unprocessable(exc) from exc
    op, offset = qubo_to_ising(model)
    energies = ising_energies(op, offset)
    k = int(np.argmin(energies))
    x = [(k >> i) & 1 for i in range(model.num_qubits)]
    states = model.states
    S = len(states)
    variables = [{"index": i, "name": name,
                  "period": sc.periods[i // S if model.one_hot else i].name,
                  "level": states[i % S][0] if model.one_hot else model.levels[1],
                  **({"gas_on": states[i % S][1]} if model.commit else {})}
                 for i, name in enumerate(model.variable_names)]
    valid = S ** model.num_periods  # one state per hour (binary Q3: every bitstring is valid)
    return {
        "tier": req.tier,
        "levels": list(model.levels),
        "encoding": "one-hot" if model.one_hot else "binary",
        "unit_commitment": model.commit,
        "num_qubits": model.num_qubits,
        "penalty": model.penalty,
        "penalty_rule": f"default A = {PENALTY_FACTOR} x the highest $ cost of any path" if req.penalty is None
        else "user supplied",
        "variables": variables,
        "qubo": {"constant": model.constant,
                 "linear": [{"i": i, "coef": c} for i, c in sorted(model.linear.items())],
                 "quadratic": [{"i": i, "j": j, "coef": c} for (i, j), c in sorted(model.quadratic.items())],
                 "text": model.program.prettyprint()},
        "ising": {"offset": offset, "num_terms": len(op),
                  "num_zz": int(sum(1 for z in op.paulis.z if z.sum() == 2)),
                  "terms": [{"pauli": label, "coef": float(c.real)}
                            for label, c in zip(op.paulis.to_labels(), op.coeffs)]},
        "bitstrings_total": 2 ** model.num_qubits,
        "valid_bitstrings": valid,
        "ground_state": {"bitstring": format(k, f"0{model.num_qubits}b"), "path": model.decode(x),
                         "commits": [on for _, on in model.decode_states(x)] if model.commit else None,
                         "energy": float(energies[k])},
        "circuit_svg": circuit_svg(qaoa_circuit(cost, req.reps).decompose()) if req.include_circuit else None,
        "circuit_stats": {"reps": req.reps, **circuit_report(cost, req.reps)},
    }


# ---------- benchmark ----------

@router.get("/benchmarks/latest")
def latest_benchmark(rows: bool = False):
    """Results of the last `python backend/scripts/run_benchmark.py` (per-row data only on request)."""
    path = RESULTS_DIR / "latest.json"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "no benchmark yet: run  python backend\\scripts\\run_benchmark.py")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not rows:
        data.pop("rows", None)
    return data


@router.get("/benchmarks/grover")
def grover_benchmark():
    """Results of the last `python backend/scripts/run_grover.py` (Grover adaptive search query counts)."""
    path = RESULTS_DIR / "grover.json"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "no Grover results yet: run  python backend\scripts\run_grover.py")
    return json.loads(path.read_text(encoding="utf-8"))


# ---------- runs ----------

@router.post("/runs/classical", status_code=status.HTTP_201_CREATED, response_model=RunOut)
def run_classical(req: ClassicalRequest, request: Request):
    sc = _resolve(req)
    try:
        results = [solve_lp(sc), solve_no_battery(sc)]
        tiers = req.exact_tiers or (["Q3U", "Q9U"] if sc.unit_commitment else ["Q3", "Q9", "Q18"])
        results += [solve_exact(sc, TIERS[t], t) for t in tiers]
    except ValueError as exc:
        raise _unprocessable(exc) from exc
    store = request.app.state.store
    run_id = store.create("classical", sc.name, req.model_dump(mode="json"), status="completed")
    store.update(run_id, results=results)
    return _run_out(store.get(run_id))


@router.post("/runs/quantum/simulator", status_code=status.HTTP_202_ACCEPTED, response_model=RunAccepted)
def run_simulator(req: SimulatorRequest, request: Request):
    sc = _resolve(req)
    try:
        cost_for(sc, req.tier, req.penalty)  # validate before queueing (e.g. levels vs capacity)
        if req.noisy:
            fake_backend(req.noise_backend)
    except ValueError as exc:
        raise _unprocessable(exc) from exc
    store = request.app.state.store
    run_id = store.create("quantum_simulator", sc.name, req.model_dump(mode="json"))
    request.app.state.worker.submit(run_id, jobs.run_simulator, req)
    return RunAccepted(run_id=run_id, status="queued")


@router.post("/runs/quantum/ibm", status_code=status.HTTP_202_ACCEPTED, response_model=RunAccepted)
def run_ibm(req: IbmRequest, request: Request):
    sc = _resolve(req)
    fake = req.backend is not None and req.backend.startswith("Fake")
    try:
        cost_for(sc, req.tier, None)
        if fake:
            fake_backend(req.backend)
    except ValueError as exc:
        raise _unprocessable(exc) from exc
    if not fake:
        if not req.confirm:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "real hardware uses QPU time: set confirm=true to approve this run")
        if not _ibm_configured():
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "IBM credentials not configured in backend/.env")
    store = request.app.state.store
    run_id = store.create("quantum_ibm", sc.name, req.model_dump(mode="json"))
    request.app.state.worker.submit(run_id, jobs.run_ibm, req)
    return RunAccepted(run_id=run_id, status="queued")


@router.get("/runs", response_model=list[RunSummary])
def list_runs(request: Request, limit: int = 50, kind: str | None = None):
    return [_summary(r) for r in request.app.state.store.list(limit=min(limit, 500), kind=kind)]


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, request: Request):
    store, worker = request.app.state.store, request.app.state.worker
    run = store.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"run {run_id} not found")
    if run["kind"] == "quantum_ibm" and run["status"] == "submitted" and not worker.is_active(run_id):
        jobs.refresh_submitted(store, run)
        run = store.get(run_id)
    return _run_out(run)


def _run_out(run: dict) -> dict:
    return {**_summary(run), "request": run["request"], "error": run["error"], "results": run["results"]}
