"""SQLite store for runs (classical, simulator, IBM hardware).

One row per run; results are stored as JSON lists of SolverResult. A new connection is opened per
operation, so the store is safe to use from the API threads and the background worker.
"""

import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from app.models.result import SolverResult
from app.provenance import utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    status        TEXT NOT NULL,
    progress      TEXT,
    scenario_name TEXT NOT NULL,
    request       TEXT NOT NULL,
    results       TEXT NOT NULL DEFAULT '[]',
    error         TEXT,
    job_id        TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
)
"""
UPDATABLE = {"status", "progress", "results", "error", "job_id"}


class RunStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as con:
            con.execute(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def create(self, kind: str, scenario_name: str, request: dict, status: str = "queued") -> str:
        run_id = uuid.uuid4().hex
        now = utc_now()
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO runs (run_id, kind, status, scenario_name, request, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, kind, status, scenario_name, json.dumps(request), now, now),
            )
        return run_id

    def update(self, run_id: str, **fields: Any) -> None:
        unknown = set(fields) - UPDATABLE
        if unknown:
            raise ValueError(f"cannot update {unknown}")
        if "results" in fields:
            fields["results"] = json.dumps([r.model_dump(mode="json") for r in fields["results"]])
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._lock, self._connect() as con:
            con.execute(f"UPDATE runs SET {cols}, updated_at = ? WHERE run_id = ?",
                        (*fields.values(), utc_now(), run_id))

    def get(self, run_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return None if row is None else self._decode(row)

    def list(self, limit: int = 50, kind: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM runs", []
        if kind:
            sql, args = sql + " WHERE kind = ?", [kind]
        sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        with self._connect() as con:
            rows = con.execute(sql, (*args, limit)).fetchall()
        return [self._decode(r) for r in rows]

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["request"] = json.loads(d["request"])
        d["results"] = [SolverResult.model_validate(r) for r in json.loads(d["results"])]
        return d
