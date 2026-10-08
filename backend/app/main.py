"""Q-GridOpt API.

Run from the project root (cmd):
    venv\\Scripts\\activate.bat
    cd backend
    uvicorn app.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.jobs import Worker
from app.api.routes import router
from app.config import RUNS_DIR
from app.store.db import RunStore

DEFAULT_DB = RUNS_DIR / "qgridopt.sqlite"
FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]  # Vite dev server


def create_app(db_path: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = RunStore(db_path or Path(os.environ.get("QGRIDOPT_DB", DEFAULT_DB)))
        app.state.worker = Worker(app.state.store)
        yield
        app.state.worker.shutdown()

    app = FastAPI(title="Q-GridOpt API", version="0.1.0", lifespan=lifespan,
                  description="Renewable-grid battery scheduling: classical solvers vs QAOA (Qiskit).\n\n"
                              "This is the backend API. **The dashboard runs separately at "
                              "[http://localhost:5173](http://localhost:5173)** (`cd frontend` then `npm run dev`).")
    app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_methods=["*"],
                       allow_headers=["*"])
    app.include_router(router)

    @app.get("/", include_in_schema=False)
    def root():
        """Opening the API address in a browser lands on the interactive docs, not a 404."""
        return RedirectResponse("/docs")

    return app


app = create_app()
