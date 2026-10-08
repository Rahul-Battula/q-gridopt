"""API tests. Uses a temporary SQLite file; never contacts IBM."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import create_app


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.sqlite")) as c:
        yield c


def wait_for(client, run_id, timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("completed", "failed"):
            return run
        time.sleep(0.5)
    raise AssertionError(f"run {run_id} did not finish: {run}")


# ---------- info ----------

def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["default_preset"] == "scenario_b"
    assert "qiskit" in body["versions"] and isinstance(body["ibm_credentials_configured"], bool)


def test_root_redirects_to_docs(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/docs"
    assert client.get("/docs").status_code == 200


def test_grover_endpoint(client, monkeypatch, tmp_path):
    from app.api import routes

    monkeypatch.setattr(routes, "RESULTS_DIR", tmp_path)
    assert client.get("/api/benchmarks/grover").status_code == 404
    (tmp_path / "grover.json").write_text(json.dumps({"tiers": [1], "chain": [2]}), encoding="utf-8")
    assert client.get("/api/benchmarks/grover").json() == {"tiers": [1], "chain": [2]}


def test_benchmark_endpoint(client, monkeypatch, tmp_path):
    from app.api import routes

    monkeypatch.setattr(routes, "RESULTS_DIR", tmp_path)
    assert client.get("/api/benchmarks/latest").status_code == 404
    (tmp_path / "latest.json").write_text(json.dumps({"summary": [1], "rows": [2], "headline": []}),
                                          encoding="utf-8")
    assert client.get("/api/benchmarks/latest").json() == {"summary": [1], "headline": []}
    assert client.get("/api/benchmarks/latest?rows=true").json()["rows"] == [2]


def test_presets(client):
    presets = {p["id"]: p for p in client.get("/api/scenarios/presets").json()}
    assert set(presets) == {"scenario_a", "scenario_b", "scenario_c"}
    assert presets["scenario_b"]["default"] is True
    assert presets["scenario_a"]["scenario"]["periods"][1]["solar"] == 90


def test_cors_allows_vite_dev_server(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


# ---------- QUBO preview ----------

def test_qubo_preview_q3(client):
    body = client.post("/api/qubo/preview", json={"tier": "Q3"}).json()
    assert body["num_qubits"] == 3 and body["encoding"] == "binary"
    assert body["ground_state"]["path"] == [0, 20, 0]
    assert body["ground_state"]["energy"] == pytest.approx(9175)
    assert body["ground_state"]["bitstring"] == "010"  # Qiskit order: qubit 0 rightmost
    assert body["ising"]["num_terms"] == 5 and body["ising"]["num_zz"] == 2
    assert body["valid_bitstrings"] == 8
    assert body["circuit_svg"].lstrip().startswith("<?xml")
    assert body["circuit_stats"]["transpiled"]["two_qubit_gates"] == 4
    assert body["variables"][1] == {"index": 1, "name": "x_t1", "period": "Afternoon", "level": 20.0}


def test_qubo_preview_q18_has_no_drawing(client):
    body = client.post("/api/qubo/preview", json={"tier": "Q18", "include_circuit": True}).json()
    assert body["num_qubits"] == 18 and body["valid_bitstrings"] == 216
    assert body["circuit_svg"] is None  # too large to draw
    assert body["ground_state"]["path"] == [0, 20, 0]


def test_qubo_preview_custom_penalty_and_scenario(client):
    sc = client.get("/api/scenarios/presets").json()[0]["scenario"]  # scenario_a
    body = client.post("/api/qubo/preview", json={"scenario": sc, "tier": "Q9", "penalty": 123456,
                                                  "include_circuit": False}).json()
    assert body["penalty"] == 123456 and body["penalty_rule"] == "user supplied"
    assert body["ground_state"]["path"] == [0, 0, 0]


def test_bad_inputs(client):
    assert client.post("/api/qubo/preview", json={"preset": "nope"}).status_code == 422
    assert client.post("/api/qubo/preview", json={"preset": "scenario_a", "scenario": {}}).status_code == 422
    assert client.post("/api/qubo/preview", json={"tier": "Q5"}).status_code == 422
    sc = client.get("/api/scenarios/presets").json()[1]["scenario"]
    sc["battery"]["capacity"] = 30
    r = client.post("/api/qubo/preview", json={"scenario": sc, "tier": "Q9"})
    assert r.status_code == 422
    assert "must lie within 0..30" in r.json()["detail"]  # Q9 level 40 > capacity 30


# ---------- classical (synchronous) ----------

def test_classical_run(client):
    r = client.post("/api/runs/classical", json={"exact_tiers": ["Q3", "Q9"]})
    assert r.status_code == 201
    run = r.json()
    assert run["status"] == "completed" and run["kind"] == "classical"
    by_source = {}
    for res in run["results"]:
        by_source.setdefault(res["source"], []).append(res)
    assert by_source["classical_lp"][0]["evaluation"]["objective"] == pytest.approx(9175)
    assert by_source["classical_no_battery"][0]["evaluation"]["objective"] == pytest.approx(10925)
    assert [e["details"]["tier"] for e in by_source["classical_exact"]] == ["Q3", "Q9"]
    assert run["best_objective"] == pytest.approx(9175)
    # stored and listed
    assert client.get(f"/api/runs/{run['run_id']}").json()["results"] == run["results"]
    assert client.get("/api/runs").json()[0]["run_id"] == run["run_id"]


def test_unknown_run(client):
    assert client.get("/api/runs/does-not-exist").status_code == 404


# ---------- quantum simulator (async, 202) ----------

def test_simulator_run_async(client):
    r = client.post("/api/runs/quantum/simulator",
                    json={"tier": "Q3", "max_reps": 2, "shots": 1024, "noisy": True})
    assert r.status_code == 202
    accepted = r.json()
    assert accepted["status"] == "queued"
    run = wait_for(client, accepted["run_id"])
    assert run["status"] == "completed", run["error"]
    sources = [res["source"] for res in run["results"]]
    assert sources == ["aer_statevector", "aer_statevector", "aer_noisy", "aer_noisy"]
    assert [res["details"]["reps"] for res in run["results"]] == [1, 2, 1, 2]
    assert run["best_objective"] == pytest.approx(9175)
    assert run["progress"] is None


def test_simulator_rejects_unknown_noise_backend(client):
    r = client.post("/api/runs/quantum/simulator", json={"noise_backend": "ibm_imaginary"})
    assert r.status_code == 422


def test_runs_filter_by_kind(client):
    client.post("/api/runs/classical", json={"exact_tiers": ["Q3"]})
    assert client.get("/api/runs?kind=quantum_ibm").json() == []
    assert len(client.get("/api/runs?kind=classical").json()) == 1


# ---------- IBM endpoint (async, 202) ----------

def test_ibm_real_hardware_requires_confirmation(client):
    r = client.post("/api/runs/quantum/ibm", json={"tier": "Q3"})
    assert r.status_code == 400 and "confirm" in r.json()["detail"]


def test_ibm_real_hardware_requires_credentials(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "missing.env")
    r = client.post("/api/runs/quantum/ibm", json={"tier": "Q3", "confirm": True})
    assert r.status_code == 400 and "credentials" in r.json()["detail"]


class _FakeJob:
    def __init__(self, final, done, status="DONE"):
        self._final, self._done, self._status = final, done, status

    def in_final_state(self):
        return self._final

    def done(self):
        return self._done

    def status(self):
        return self._status


@pytest.mark.parametrize("job,expected", [
    (_FakeJob(final=False, done=False, status="QUEUED"), "submitted"),
    (_FakeJob(final=True, done=True), "completed"),
    (_FakeJob(final=True, done=False, status="CANCELLED"), "failed"),
])
def test_refresh_after_restart(tmp_path, monkeypatch, job, expected):
    """A hardware run left 'submitted' (server restarted) is collected from IBM when polled."""
    from app.api import jobs
    from app.classical.no_battery import solve_no_battery
    from app.grid.presets import load_preset
    from app.quantum import ibm_runner
    from app.store.db import RunStore

    store = RunStore(tmp_path / "s.sqlite")
    run_id = store.create("quantum_ibm", "Scenario B", {})
    store.update(run_id, status="submitted", job_id="JOB1")
    service = type("Svc", (), {"job": lambda self, jid: job})()
    monkeypatch.setattr(ibm_runner, "get_service", lambda: service)
    monkeypatch.setattr(ibm_runner, "collect_recorded",
                        lambda jid, svc: [solve_no_battery(load_preset("scenario_b"))])
    jobs.refresh_submitted(store, store.get(run_id))
    run = store.get(run_id)
    assert run["status"] == expected
    assert len(run["results"]) == (1 if expected == "completed" else 0)
    if expected == "failed":
        assert "CANCELLED" in run["error"]


def test_ibm_local_testing_mode(client):
    r = client.post("/api/runs/quantum/ibm", json={"tier": "Q3", "max_reps": 1, "shots": 1024,
                                                   "backend": "FakeFez"})
    assert r.status_code == 202
    run = wait_for(client, r.json()["run_id"])
    assert run["status"] == "completed", run["error"]
    [res] = run["results"]
    assert res["source"] == "aer_noisy"  # local testing is never labelled ibm_hardware
    assert "local testing mode" in res["provenance"]["backend"]
    assert run["job_id"] == res["provenance"]["job_id"]
