"""Configuration: IBM Quantum credentials from backend/.env (gitignored). Never hard-code secrets."""

from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_DIR / ".env"
RUNS_DIR = BACKEND_DIR / "runs"  # gitignored; local record of submitted IBM jobs
PLACEHOLDERS = {"", "your-ibm-api-key-here", "your-instance-crn-here"}


@dataclass(frozen=True)
class IbmCredentials:
    token: str
    instance: str
    channel: str = "ibm_quantum_platform"

    def __repr__(self) -> str:  # never print the key
        return f"IbmCredentials(token=<{len(self.token)} chars>, instance={self.instance[:24]}..., channel={self.channel})"


class MissingCredentials(RuntimeError):
    pass


def load_ibm_credentials(env_path: Path | None = None) -> IbmCredentials:
    env_path = env_path or ENV_PATH  # looked up at call time (tests can point it elsewhere)
    if not env_path.exists():
        raise MissingCredentials(f"{env_path} not found. Run: copy backend\\.env.example backend\\.env")
    env = dotenv_values(env_path)
    token = (env.get("IBM_QUANTUM_API_KEY") or "").strip()
    instance = (env.get("IBM_QUANTUM_INSTANCE_CRN") or "").strip()
    channel = (env.get("IBM_QUANTUM_CHANNEL") or "ibm_quantum_platform").strip()
    missing = [name for name, v in (("IBM_QUANTUM_API_KEY", token), ("IBM_QUANTUM_INSTANCE_CRN", instance))
               if v in PLACEHOLDERS]
    if missing:
        raise MissingCredentials(f"still a placeholder/empty in backend\\.env: {', '.join(missing)}")
    return IbmCredentials(token=token, instance=instance, channel=channel)
