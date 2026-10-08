"""Import a finished IBM hardware job (recorded in backend/runs/ibm_jobs.json) into the dashboard
database so it shows up on the Runs / Hardware pages.

Run from the project root (cmd):  python backend\\scripts\\import_ibm_job.py <job_id>

Only READS the job from IBM (no QPU time used, nothing is submitted). Safe to run twice: a job
that is already imported is skipped.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import RUNS_DIR  # noqa: E402
from app.quantum import ibm_runner as ibm  # noqa: E402
from app.store.db import RunStore  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python backend\\scripts\\import_ibm_job.py <job_id>")
    job_id = sys.argv[1]
    store = RunStore(Path(os.environ.get("QGRIDOPT_DB", RUNS_DIR / "qgridopt.sqlite")))

    if any(r["job_id"] == job_id for r in store.list(limit=500, kind="quantum_ibm")):
        print(f"job {job_id} is already in the dashboard database - nothing to do.")
        return

    rec = next((j for j in json.loads(ibm.JOBS_FILE.read_text(encoding="utf-8")) if j["job_id"] == job_id), None)
    if rec is None:
        sys.exit(f"job {job_id} not found in {ibm.JOBS_FILE}")

    print("Fetching results from IBM (read-only)...")
    results = ibm.collect_recorded(job_id)
    opts = rec["options"]
    request = {"scenario": rec["scenario"], "tier": results[0].details.get("tier", "Q3"),
               "max_reps": len(results), "shots": opts.get("shots", 4096), "backend": rec["backend"],
               "confirm": True, "imported_from": "backend/runs/ibm_jobs.json"}
    run_id = store.create("quantum_ibm", rec["scenario"]["name"], request, status="submitted")
    store.update(run_id, status="completed", progress=None, job_id=job_id, results=results)
    print(f"Imported as run {run_id} (source={results[0].source}, backend={rec['backend']}).")
    print("Start the dashboard and open the Runs page to see it.")


if __name__ == "__main__":
    main()
