"""Stage 0 IBM Quantum account check (READ-ONLY: submits NO jobs, uses NO QPU time).

Run from the project root (cmd), after filling in backend\\.env:
    venv\\Scripts\\activate.bat
    python backend\\scripts\\check_ibm.py

Connects with the credentials in backend\\.env, lists the backends this account can use,
shows the least busy one and the account's usage. The API key is never printed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ENV_PATH, MissingCredentials, load_ibm_credentials  # noqa: E402


def main() -> int:
    try:
        creds = load_ibm_credentials()
    except MissingCredentials as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"Credentials loaded from {ENV_PATH}: {creds!r}")

    from qiskit_ibm_runtime import QiskitRuntimeService

    print(f"\n[1] Connecting (channel={creds.channel})")
    try:
        service = QiskitRuntimeService(channel=creds.channel, token=creds.token, instance=creds.instance)
    except Exception as exc:
        print(f"  FAIL: could not authenticate: {exc}")
        return 1
    print("  OK: authenticated")

    print("\n[2] Available backends")
    backends = service.backends()
    if not backends:
        print("  FAIL: no backends available to this account/instance")
        return 1
    for b in sorted(backends, key=lambda b: b.name):
        st = b.status()
        state = "online" if st.operational else "offline"
        print(f"  {b.name:<20} {b.num_qubits:>4} qubits  {state:<8} pending jobs: {st.pending_jobs}")

    print("\n[3] Least busy operational backend")
    try:
        lb = service.least_busy(operational=True, simulator=False)
        print(f"  {lb.name} ({lb.num_qubits} qubits, {lb.status().pending_jobs} pending jobs)")
    except Exception as exc:
        print(f"  WARN: least_busy failed: {exc}")

    print("\n[4] Account usage")
    try:
        for key, val in service.usage().items():
            if isinstance(val, str) and val.startswith("crn:"):
                val = val[:28] + "...(hidden)"  # account identifier: keep the output safe to share
            print(f"  {key}: {val}")
    except Exception as exc:
        print(f"  WARN: usage() unavailable: {exc}")

    print("\nIBM ACCOUNT CHECK PASSED (no jobs submitted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
