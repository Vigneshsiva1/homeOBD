"""FastAPI application. Run with: .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, db, push, service
from .api import router

log = logging.getLogger("homeobd")

STATIC = Path(__file__).resolve().parent / "static"
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "homeobd.db"
TICK_SECONDS = 300


def _sync(path: str | Path, notify: bool = True) -> None:
    conn = db.connect(path)
    try:
        at = service.now()
        service.sync(conn, at)
        if notify:
            push.run_schedule(conn, at)
    finally:
        conn.close()


async def _tick(path: str | Path) -> None:
    """Every few minutes: capture freeze frames, record today's health for streaks, and send any
    notification slot that is due."""
    while True:
        await asyncio.sleep(TICK_SECONDS)
        try:
            await asyncio.to_thread(_sync, path)
        except Exception:
            log.exception("tick failed")


def create_app(db_path: str | Path | None = None, tick: bool = True) -> FastAPI:
    # tick=False (tests) also skips notifications, so tests never reach a real push service.
    path = db_path or os.environ.get("HOMEOBD_DB") or DEFAULT_DB

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.init(path, service.now())
        await asyncio.to_thread(_sync, path, tick)
        task = asyncio.create_task(_tick(path)) if tick else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title="homeOBD", version=__version__, lifespan=lifespan)
    app.state.db_path = path
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.middleware("http")
    async def revalidate_everything(request, call_next):
        # Without this, iOS guesses that pages and CSS are still fresh and keeps showing old
        # versions after a deploy. no-cache = always check with the Pi (a cheap 304 when unchanged).
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response

    @app.get("/", include_in_schema=False)
    def scan_tool():
        return FileResponse(STATIC / "index.html")

    @app.get("/setup", include_in_schema=False)
    def setup():
        return FileResponse(STATIC / "setup.html")

    # The manifest and service worker live at the root so their scope covers the whole app.
    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        return FileResponse(
            STATIC / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"}
        )

    return app


app = create_app()
