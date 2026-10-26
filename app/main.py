"""FastAPI application. Run with: .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, db, service
from .api import router

log = logging.getLogger("homeobd")

STATIC = Path(__file__).resolve().parent / "static"
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "homeobd.db"
TICK_SECONDS = 300


def _sync(path: str | Path) -> None:
    conn = db.connect(path)
    try:
        service.sync(conn, service.now())
    finally:
        conn.close()


async def _tick(path: str | Path) -> None:
    """Every few minutes: capture freeze frames and record today's health for streaks."""
    while True:
        await asyncio.sleep(TICK_SECONDS)
        try:
            await asyncio.to_thread(_sync, path)
        except Exception:
            log.exception("tick failed")


def create_app(db_path: str | Path | None = None, tick: bool = True) -> FastAPI:
    path = db_path or os.environ.get("HOMEOBD_DB") or DEFAULT_DB

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.init(path, service.now())
        await asyncio.to_thread(_sync, path)
        task = asyncio.create_task(_tick(path)) if tick else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title="homeOBD", version=__version__, lifespan=lifespan)
    app.state.db_path = path
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def scan_tool():
        return FileResponse(STATIC / "index.html")

    @app.get("/setup", include_in_schema=False)
    def setup():
        return FileResponse(STATIC / "setup.html")

    return app


app = create_app()
