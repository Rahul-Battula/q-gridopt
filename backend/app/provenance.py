"""Helpers for recording where a result came from."""

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def library_versions(*packages: str) -> dict[str, str]:
    out = {}
    for pkg in packages:
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = "not installed"
    return out
