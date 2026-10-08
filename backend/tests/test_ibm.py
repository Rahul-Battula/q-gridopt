"""Stage 7 tests. None of these contact IBM or use QPU time."""

import pytest
from qiskit.providers.fake_provider import GenericBackendV2

from app import config
from app.grid.presets import load_preset
from app.quantum import ibm_runner as ibm
from app.quantum.simulate import run_qaoa_simulation
from app.quantum.transpile import fake_backend


@pytest.fixture(scope="module")
def ideal_q3():
    result, _ = run_qaoa_simulation(load_preset("scenario_b"), "Q3", reps=1, shots=1024, seed=3)
    return result


# ---------- credentials ----------

def test_placeholder_credentials_rejected(tmp_path):
    env = tmp_path / ".env"
    env.write_text("IBM_QUANTUM_API_KEY=your-ibm-api-key-here\n"
                   "IBM_QUANTUM_INSTANCE_CRN=your-instance-crn-here\n", encoding="utf-8")
    with pytest.raises(config.MissingCredentials):
        config.load_ibm_credentials(env)


def test_missing_env_file_rejected(tmp_path):
    with pytest.raises(config.MissingCredentials):
        config.load_ibm_credentials(tmp_path / "nope.env")


def test_credentials_loaded_and_key_never_printed(tmp_path):
    env = tmp_path / ".env"
    env.write_text("IBM_QUANTUM_API_KEY=SECRET123456\nIBM_QUANTUM_INSTANCE_CRN=crn:v1:test\n", encoding="utf-8")
    creds = config.load_ibm_credentials(env)
    assert creds.token == "SECRET123456" and creds.channel == "ibm_quantum_platform"
    assert "SECRET" not in repr(creds) and "SECRET" not in str(creds)


# ---------- safety: nothing reaches a real QPU without approval ----------

def test_real_backend_requires_confirmation(ideal_q3):
    sc = load_preset("scenario_b")
    not_fake = GenericBackendV2(num_qubits=5, seed=1)  # stands in for a real IBM backend, offline
    assert not ibm.is_fake(not_fake)
    pubs = ibm.prepare(sc, [ideal_q3], not_fake, ibm.HardwareOptions())
    with pytest.raises(ibm.NotApproved):
        ibm.submit(sc, pubs, not_fake, ibm.HardwareOptions())


def test_prepare_rejects_wrong_inputs(ideal_q3):
    sc = load_preset("scenario_b")
    other, _ = run_qaoa_simulation(sc, "Q9", reps=1, shots=256, seed=3)
    with pytest.raises(ValueError):
        ibm.prepare(sc, [ideal_q3, other], fake_backend("FakeFez"), ibm.HardwareOptions())


def test_real_backend_sampler_has_qpu_time_cap():
    sampler = ibm.make_sampler(GenericBackendV2(num_qubits=5, seed=1), ibm.HardwareOptions())
    assert sampler.options.max_execution_time == 60
    assert sampler.options.dynamical_decoupling.enable is True


def test_estimate_without_dry_run_access_returns_none(ideal_q3, monkeypatch):
    """Accounts without IBM's mock backend: no estimate, no crash (the cap is the guarantee)."""
    from qiskit.providers.exceptions import QiskitBackendNotFoundError

    class NoDryRun:
        def run(self, *args, **kwargs):
            raise QiskitBackendNotFoundError("Unable to use `dry_run` mode: backend 'mock_x' was not found")

    backend = GenericBackendV2(num_qubits=5, seed=1)
    monkeypatch.setattr(ibm, "make_sampler", lambda b, o: NoDryRun())
    pubs = ibm.prepare(load_preset("scenario_b"), [ideal_q3], backend, ibm.HardwareOptions())
    assert ibm.estimate_qpu_seconds(pubs, backend, ibm.HardwareOptions()) is None


def test_estimate_is_none_locally(ideal_q3):
    backend = fake_backend("FakeFez")
    pubs = ibm.prepare(load_preset("scenario_b"), [ideal_q3], backend, ibm.HardwareOptions())
    assert ibm.estimate_qpu_seconds(pubs, backend, ibm.HardwareOptions()) is None


# ---------- full code path in qiskit-ibm-runtime local testing mode ----------

def test_local_mode_end_to_end(ideal_q3):
    sc = load_preset("scenario_b")
    backend = fake_backend("FakeFez")
    opts = ibm.HardwareOptions(shots=1024)
    pubs = ibm.prepare(sc, [ideal_q3], backend, opts)
    job = ibm.submit(sc, pubs, backend, opts)
    [r] = ibm.collect(sc, [p["stats"] for p in pubs], [ideal_q3], job, backend.name, opts, fake=True)
    assert r.source == "aer_noisy"  # a fake backend is NEVER labelled ibm_hardware
    assert "local testing mode" in r.provenance.backend
    assert r.provenance.job_id and r.provenance.shots == 1024
    assert r.details["gammas"] == ideal_q3.details["gammas"]  # fixed, simulator-trained angles
    assert r.details["qaoa_sampled"]["p_optimal"] > r.details["random_exact"]["p_optimal"]
    assert r.evaluation.objective == pytest.approx(r.details["best_found"]["objective"])
    assert not ibm.JOBS_FILE.exists() or job.job_id() not in ibm.JOBS_FILE.read_text()  # local jobs not recorded


def test_collect_unknown_job(tmp_path, monkeypatch):
    monkeypatch.setattr(ibm, "JOBS_FILE", tmp_path / "ibm_jobs.json")
    with pytest.raises(KeyError):
        ibm.collect_recorded("does-not-exist", service=object())
